#!/usr/bin/env python3
"""
Internal Employee Portal — Peer-to-Peer Kudos System.

Implements the approved Task 2 specification (`SPECIFICATION.md`):
- SQLite persistence with `users` and `kudos` tables (including moderation audit columns)
- Input validation, XSS escaping, self-kudos guard, duplicate cooldown, and rate limiting
- Role-based access control (employee vs. admin) for feed visibility and moderation
- REST JSON API + responsive HTML dashboard served via Python's standard library
"""

import html
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("kudos_app")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kudos.db")
INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

MAX_MESSAGE_LENGTH = 500
MAX_REASON_LENGTH = 500
DEFAULT_FEED_LIMIT = 20
MAX_FEED_LIMIT = 50
DEFAULT_DUPLICATE_WINDOW_SECONDS = 300
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_RATE_LIMIT_MAX_KUDOS = 10

BLOCKED_TERMS: Tuple[str, ...] = (
    "spamlink",
    "phishing-scam",
    "abuseword",
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT 'General',
    role TEXT NOT NULL DEFAULT 'employee' CHECK (role IN ('employee', 'admin')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL CHECK (length(trim(message)) BETWEEN 1 AND 500),
    is_visible INTEGER NOT NULL DEFAULT 1 CHECK (is_visible IN (0, 1)),
    moderated_by INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    moderated_at TEXT NULL,
    reason_for_moderation TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (sender_id <> recipient_id)
);

CREATE INDEX IF NOT EXISTS idx_kudos_public_feed
    ON kudos (is_visible, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_kudos_duplicate_check
    ON kudos (sender_id, recipient_id, created_at DESC);
"""


class AppError(Exception):
    """Base application error carrying HTTP status code and structured error code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ValidationError(AppError):
    def __init__(self, message: str, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(HTTPStatus.BAD_REQUEST, code, message)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(HTTPStatus.UNAUTHORIZED, "UNAUTHORIZED", message)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(HTTPStatus.FORBIDDEN, "FORBIDDEN", message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(HTTPStatus.NOT_FOUND, "NOT_FOUND", message)


class ConflictError(AppError):
    def __init__(self, message: str = "Duplicate kudos submission detected") -> None:
        super().__init__(HTTPStatus.CONFLICT, "DUPLICATE_KUDOS", message)


class RateLimitError(AppError):
    def __init__(
        self, message: str = "Rate limit exceeded; please try again shortly"
    ) -> None:
        super().__init__(HTTPStatus.TOO_MANY_REQUESTS, "RATE_LIMITED", message)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class KudosService:
    """Business logic and SQLite persistence layer for the Kudos system."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        duplicate_window_seconds: int = DEFAULT_DUPLICATE_WINDOW_SECONDS,
        rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
        rate_limit_max_kudos: int = DEFAULT_RATE_LIMIT_MAX_KUDOS,
    ) -> None:
        self.db_path = db_path
        self.duplicate_window_seconds = duplicate_window_seconds
        self.rate_limit_window_seconds = rate_limit_window_seconds
        self.rate_limit_max_kudos = rate_limit_max_kudos
        self.init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create schema tables and indexes if they do not already exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    def seed_default_users(self) -> None:
        """Populate initial demo users when the users table is empty."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count > 0:
                return
            now = utc_now_iso()
            sample_users = [
                ("alice.silva@datacom.example", "Alice Silva", "Engineering", "employee", 1, now),
                ("bob.santos@datacom.example", "Bob Santos", "Automation", "employee", 1, now),
                ("carol.costa@datacom.example", "Carol Costa", "Product", "employee", 1, now),
                ("daniel.rocha@datacom.example", "Daniel Rocha", "People & Culture", "admin", 1, now),
            ]
            conn.executemany(
                """
                INSERT INTO users (email, full_name, department, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                sample_users,
            )
            logger.info("Seeded %d default users", len(sample_users))

    def create_user(
        self,
        email: str,
        full_name: str,
        department: str = "General",
        role: str = "employee",
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """Create a user record (used for administration and tests)."""
        if role not in ("employee", "admin"):
            raise ValidationError("Role must be 'employee' or 'admin'")
        clean_email = email.strip().lower()
        clean_name = full_name.strip()
        if not clean_email or not clean_name:
            raise ValidationError("Email and full_name are required")

        now = utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (email, full_name, department, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_email, clean_name, department.strip() or "General", role, int(is_active), now),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return self._serialize_user(row)

    @staticmethod
    def _serialize_user(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"],
            "department": row["department"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _serialize_kudos(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "sender_id": row["sender_id"],
            "sender_name": row["sender_name"],
            "recipient_id": row["recipient_id"],
            "recipient_name": row["recipient_name"],
            "message": row["message"],
            "is_visible": bool(row["is_visible"]),
            "moderated_by": row["moderated_by"],
            "moderator_name": row["moderator_name"],
            "moderated_at": row["moderated_at"],
            "reason_for_moderation": row["reason_for_moderation"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """Fetch an active user by ID or raise UnauthorizedError."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
            ).fetchone()
            if row is None:
                raise UnauthorizedError("Authenticated user not found or inactive")
            return self._serialize_user(row)

    def list_colleagues(
        self, requester_id: int, include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """List active users sorted alphabetically, excluding the requester by default."""
        self.get_user(requester_id)
        with self._connect() as conn:
            if include_self:
                rows = conn.execute(
                    """
                    SELECT * FROM users
                    WHERE is_active = 1
                    ORDER BY full_name COLLATE NOCASE ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM users
                    WHERE is_active = 1 AND id <> ?
                    ORDER BY full_name COLLATE NOCASE ASC
                    """,
                    (requester_id,),
                ).fetchall()
            return [self._serialize_user(r) for r in rows]

    @staticmethod
    def _sanitize_and_validate_message(raw_message: Any) -> str:
        """Trim, validate bounds/policy, and HTML-escape a kudos message."""
        if not isinstance(raw_message, str):
            raise ValidationError("Message must be a text string")

        trimmed = raw_message.strip()
        if not trimmed:
            raise ValidationError("Message cannot be empty")
        if len(trimmed) > MAX_MESSAGE_LENGTH:
            raise ValidationError(
                f"Message cannot exceed {MAX_MESSAGE_LENGTH} characters"
            )

        lower_msg = trimmed.lower()
        for term in BLOCKED_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", lower_msg):
                raise ValidationError(
                    "Message violates workplace content policy",
                    code="INAPPROPRIATE_CONTENT",
                )

        return html.escape(trimmed, quote=False)

    def create_kudos(
        self, sender_id: int, recipient_id: Any, message: Any
    ) -> Dict[str, Any]:
        """Validate, screen, and persist a new peer-to-peer kudos entry."""
        self.get_user(sender_id)

        try:
            clean_recipient_id = int(recipient_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError("A valid recipient_id is required") from exc

        if clean_recipient_id == sender_id:
            raise ValidationError(
                "Cannot send kudos to yourself", code="SELF_KUDOS_NOT_ALLOWED"
            )

        sanitized_message = self._sanitize_and_validate_message(message)

        with self._connect() as conn:
            recipient = conn.execute(
                "SELECT id FROM users WHERE id = ? AND is_active = 1",
                (clean_recipient_id,),
            ).fetchone()
            if recipient is None:
                raise NotFoundError("Selected colleague was not found or is inactive")

            now_dt = datetime.now(timezone.utc)
            now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            # Rate-limiting check
            rate_cutoff = (
                now_dt - timedelta(seconds=self.rate_limit_window_seconds)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            recent_count = conn.execute(
                """
                SELECT COUNT(*) FROM kudos
                WHERE sender_id = ? AND created_at >= ?
                """,
                (sender_id, rate_cutoff),
            ).fetchone()[0]
            if recent_count >= self.rate_limit_max_kudos:
                logger.warning("Rate limit triggered for user_id=%s", sender_id)
                raise RateLimitError()

            # Duplicate submission cooldown check
            dup_cutoff = (
                now_dt - timedelta(seconds=self.duplicate_window_seconds)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            recent_messages = conn.execute(
                """
                SELECT message FROM kudos
                WHERE sender_id = ? AND recipient_id = ? AND created_at >= ?
                """,
                (sender_id, clean_recipient_id, dup_cutoff),
            ).fetchall()
            normalized_candidate = sanitized_message.lower()
            for row in recent_messages:
                if row["message"].strip().lower() == normalized_candidate:
                    raise ConflictError(
                        "Duplicate kudos detected for this colleague within cooldown window"
                    )

            cur = conn.execute(
                """
                INSERT INTO kudos (
                    sender_id, recipient_id, message, is_visible,
                    moderated_by, moderated_at, reason_for_moderation,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, 1, NULL, NULL, NULL, ?, ?)
                """,
                (sender_id, clean_recipient_id, sanitized_message, now_iso, now_iso),
            )
            kudos_id = cur.lastrowid

        logger.info(
            "Kudos created id=%s sender_id=%s recipient_id=%s",
            kudos_id,
            sender_id,
            clean_recipient_id,
        )
        return self._get_kudos_by_id(kudos_id)

    def _get_kudos_by_id(self, kudos_id: int) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    k.*,
                    s.full_name AS sender_name,
                    r.full_name AS recipient_name,
                    m.full_name AS moderator_name
                FROM kudos k
                JOIN users s ON s.id = k.sender_id
                JOIN users r ON r.id = k.recipient_id
                LEFT JOIN users m ON m.id = k.moderated_by
                WHERE k.id = ?
                """,
                (kudos_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Kudos {kudos_id} not found")
            return self._serialize_kudos(row)

    def get_feed(
        self,
        requester_id: int,
        limit: int = DEFAULT_FEED_LIMIT,
        offset: int = 0,
        include_hidden: bool = False,
    ) -> Dict[str, Any]:
        """Return paginated kudos feed sorted newest-first."""
        requester = self.get_user(requester_id)
        if include_hidden and requester["role"] != "admin":
            raise ForbiddenError("Only administrators can view hidden kudos")

        if limit < 1 or limit > MAX_FEED_LIMIT:
            raise ValidationError(f"limit must be between 1 and {MAX_FEED_LIMIT}")
        if offset < 0:
            raise ValidationError("offset must be >= 0")

        where_clause = "" if include_hidden else "WHERE k.is_visible = 1"
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM kudos k {where_clause}"
            ).fetchone()[0]

            rows = conn.execute(
                f"""
                SELECT
                    k.*,
                    s.full_name AS sender_name,
                    r.full_name AS recipient_name,
                    m.full_name AS moderator_name
                FROM kudos k
                JOIN users s ON s.id = k.sender_id
                JOIN users r ON r.id = k.recipient_id
                LEFT JOIN users m ON m.id = k.moderated_by
                {where_clause}
                ORDER BY k.created_at DESC, k.id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()

        items = [self._serialize_kudos(r) for r in rows]
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(items)) < total,
        }

    def moderate_kudos(
        self, admin_id: int, kudos_id: int, action: str, reason: Any
    ) -> Dict[str, Any]:
        """Hide or restore a kudos entry with full moderation audit metadata."""
        actor = self.get_user(admin_id)
        if actor["role"] != "admin":
            raise ForbiddenError("Administrator privileges required to moderate kudos")

        clean_action = str(action).strip().lower()
        if clean_action not in ("hide", "restore"):
            raise ValidationError("Moderation action must be 'hide' or 'restore'")

        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("A non-empty reason_for_moderation is required")
        clean_reason = html.escape(reason.strip(), quote=False)
        if len(clean_reason) > MAX_REASON_LENGTH:
            raise ValidationError(
                f"Moderation reason cannot exceed {MAX_REASON_LENGTH} characters"
            )

        new_visibility = 0 if clean_action == "hide" else 1
        now_iso = utc_now_iso()

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM kudos WHERE id = ?", (kudos_id,)
            ).fetchone()
            if existing is None:
                raise NotFoundError(f"Kudos {kudos_id} not found")

            conn.execute(
                """
                UPDATE kudos
                SET is_visible = ?,
                    moderated_by = ?,
                    moderated_at = ?,
                    reason_for_moderation = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (new_visibility, admin_id, now_iso, clean_reason, now_iso, kudos_id),
            )

        logger.info(
            "AUDIT moderation action=%s kudos_id=%s admin_id=%s reason=%r",
            clean_action,
            kudos_id,
            admin_id,
            clean_reason,
        )
        return self._get_kudos_by_id(kudos_id)

    def delete_kudos(self, admin_id: int, kudos_id: int) -> Dict[str, Any]:
        """Permanently delete a kudos entry (admin only)."""
        actor = self.get_user(admin_id)
        if actor["role"] != "admin":
            raise ForbiddenError("Administrator privileges required to delete kudos")

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, sender_id, recipient_id FROM kudos WHERE id = ?",
                (kudos_id,),
            ).fetchone()
            if existing is None:
                raise NotFoundError(f"Kudos {kudos_id} not found")

            conn.execute("DELETE FROM kudos WHERE id = ?", (kudos_id,))

        logger.info(
            "AUDIT delete kudos_id=%s admin_id=%s original_sender=%s original_recipient=%s",
            kudos_id,
            admin_id,
            existing["sender_id"],
            existing["recipient_id"],
        )
        return {"deleted": True, "id": kudos_id}


def make_handler(service: KudosService):
    """Build an HTTP request handler bound to the provided KudosService."""

    class KudosRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("HTTP %s", format % args)

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, err: AppError) -> None:
            self._send_json(
                err.status_code,
                {"error": {"code": err.code, "message": err.message}},
            )

        def _read_json_body(self) -> Dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValidationError("Invalid Content-Length header") from exc
            if length <= 0:
                raise ValidationError("JSON request body is required")
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationError("Malformed JSON payload") from exc
            if not isinstance(data, dict):
                raise ValidationError("JSON body must be an object")
            return data

        def _get_requester_id(self) -> int:
            raw_uid = self.headers.get("X-User-Id", "").strip()
            if not raw_uid:
                raise UnauthorizedError("Missing X-User-Id header")
            try:
                return int(raw_uid)
            except ValueError as exc:
                raise UnauthorizedError("Invalid X-User-Id header") from exc

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path in ("/", "/index.html"):
                    with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
                        content = f.read().encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

                requester_id = self._get_requester_id()
                query = parse_qs(parsed.query)

                if parsed.path == "/api/users":
                    include_self = query.get("include_self", ["false"])[0].lower() == "true"
                    users = service.list_colleagues(requester_id, include_self=include_self)
                    self._send_json(HTTPStatus.OK, {"users": users})
                    return

                if parsed.path == "/api/kudos":
                    try:
                        limit = int(query.get("limit", [str(DEFAULT_FEED_LIMIT)])[0])
                        offset = int(query.get("offset", ["0"])[0])
                    except ValueError as exc:
                        raise ValidationError("limit and offset must be integers") from exc
                    include_hidden = (
                        query.get("include_hidden", ["false"])[0].lower() == "true"
                    )
                    feed = service.get_feed(
                        requester_id,
                        limit=limit,
                        offset=offset,
                        include_hidden=include_hidden,
                    )
                    self._send_json(HTTPStatus.OK, feed)
                    return

                raise NotFoundError("Endpoint not found")
            except AppError as err:
                self._send_error_json(err)
            except Exception as exc:  # pragma: no cover
                logger.exception("Unhandled GET error: %s", exc)
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
                )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                requester_id = self._get_requester_id()
                if parsed.path == "/api/kudos":
                    body = self._read_json_body()
                    kudos = service.create_kudos(
                        sender_id=requester_id,
                        recipient_id=body.get("recipient_id"),
                        message=body.get("message"),
                    )
                    self._send_json(HTTPStatus.CREATED, {"kudos": kudos})
                    return
                raise NotFoundError("Endpoint not found")
            except AppError as err:
                self._send_error_json(err)
            except Exception as exc:  # pragma: no cover
                logger.exception("Unhandled POST error: %s", exc)
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
                )

        def do_PATCH(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                requester_id = self._get_requester_id()
                match = re.fullmatch(r"/api/kudos/(\d+)/moderate", parsed.path)
                if match:
                    kudos_id = int(match.group(1))
                    body = self._read_json_body()
                    kudos = service.moderate_kudos(
                        admin_id=requester_id,
                        kudos_id=kudos_id,
                        action=body.get("action", ""),
                        reason=body.get("reason", ""),
                    )
                    self._send_json(HTTPStatus.OK, {"kudos": kudos})
                    return
                raise NotFoundError("Endpoint not found")
            except AppError as err:
                self._send_error_json(err)
            except Exception as exc:  # pragma: no cover
                logger.exception("Unhandled PATCH error: %s", exc)
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
                )

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                requester_id = self._get_requester_id()
                match = re.fullmatch(r"/api/kudos/(\d+)", parsed.path)
                if match:
                    kudos_id = int(match.group(1))
                    result = service.delete_kudos(admin_id=requester_id, kudos_id=kudos_id)
                    self._send_json(HTTPStatus.OK, result)
                    return
                raise NotFoundError("Endpoint not found")
            except AppError as err:
                self._send_error_json(err)
            except Exception as exc:  # pragma: no cover
                logger.exception("Unhandled DELETE error: %s", exc)
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
                )

    return KudosRequestHandler


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    service: Optional[KudosService] = None,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer instance."""
    svc = service or KudosService()
    svc.seed_default_users()
    return ThreadingHTTPServer((host, port), make_handler(svc))


if __name__ == "__main__":
    host = os.environ.get("KUDOS_HOST", "127.0.0.1")
    port = int(os.environ.get("KUDOS_PORT", "8000"))
    server = create_server(host=host, port=port)
    logger.info("Kudos System running at http://%s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Kudos System")
        server.server_close()
