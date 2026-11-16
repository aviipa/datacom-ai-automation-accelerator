#!/usr/bin/env python3
"""
Automated test suite for Task 2: Spec-Driven Kudos System.

Tests both the service/persistence layer (`KudosService`) and live HTTP JSON API
against every user story, schema addition, validation rule, and moderation flow
defined in `SPECIFICATION.md`.
"""

import json
import os
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kudos_app import (
    ConflictError,
    ForbiddenError,
    KudosService,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
    ValidationError,
    create_server,
)


class TestKudosService(unittest.TestCase):
    """Service-level and database schema tests for the Kudos system."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_kudos.db")
        self.service = KudosService(
            db_path=self.db_path,
            duplicate_window_seconds=300,
            rate_limit_window_seconds=60,
            rate_limit_max_kudos=5,
        )
        self.alice = self.service.create_user(
            "alice@datacom.example", "Alice Silva", "Engineering", "employee"
        )
        self.bob = self.service.create_user(
            "bob@datacom.example", "Bob Santos", "Automation", "employee"
        )
        self.carol = self.service.create_user(
            "carol@datacom.example", "Carol Costa", "Product", "employee"
        )
        self.admin = self.service.create_user(
            "admin@datacom.example", "Daniel Rocha", "People & Culture", "admin"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_database_schema_includes_moderation_columns(self) -> None:
        """Verify `kudos` table contains all required moderation audit columns."""
        conn = sqlite3.connect(self.db_path)
        try:
            cols = {
                row[1]: row for row in conn.execute("PRAGMA table_info(kudos)").fetchall()
            }
        finally:
            conn.close()
        for col in (
            "is_visible",
            "moderated_by",
            "moderated_at",
            "reason_for_moderation",
        ):
            self.assertIn(col, cols, f"Missing column {col} in kudos schema")
        # is_visible default is 1 (True)
        self.assertEqual(str(cols["is_visible"][4]), "1")

    def test_us01_colleague_list_excludes_self_and_is_sorted(self) -> None:
        """US-01: Colleague selector lists active colleagues alphabetically excluding self."""
        colleagues = self.service.list_colleagues(self.bob["id"])
        names = [c["full_name"] for c in colleagues]
        self.assertEqual(names, ["Alice Silva", "Carol Costa", "Daniel Rocha"])
        self.assertNotIn(self.bob["id"], [c["id"] for c in colleagues])

    def test_us02_us03_create_kudos_validation_and_xss_escaping(self) -> None:
        """US-02 & US-03: Validations (self-kudos, bounds, policy, XSS escaping)."""
        # Self-kudos rejected
        with self.assertRaises(ValidationError):
            self.service.create_kudos(self.alice["id"], self.alice["id"], "Nice job me")

        # Empty / whitespace rejected
        with self.assertRaises(ValidationError):
            self.service.create_kudos(self.alice["id"], self.bob["id"], "   ")

        # > 500 characters rejected
        with self.assertRaises(ValidationError):
            self.service.create_kudos(self.alice["id"], self.bob["id"], "A" * 501)

        # Exactly 500 characters accepted
        kudos_500 = self.service.create_kudos(
            self.alice["id"], self.bob["id"], "B" * 500
        )
        self.assertEqual(len(kudos_500["message"]), 500)
        self.assertTrue(kudos_500["is_visible"])

        # Blocked inappropriate word rejected
        with self.assertRaises(ValidationError):
            self.service.create_kudos(
                self.alice["id"], self.bob["id"], "Check out this spamlink now!"
            )

        # XSS payload escaped safely
        xss_kudos = self.service.create_kudos(
            self.alice["id"], self.carol["id"], "Great job <script>alert(1)</script>!"
        )
        self.assertNotIn("<script>", xss_kudos["message"])
        self.assertIn("&lt;script&gt;", xss_kudos["message"])

    def test_duplicate_cooldown_and_rate_limiting(self) -> None:
        """Edge cases: duplicate submission returns ConflictError; burst returns RateLimitError."""
        self.service.create_kudos(self.alice["id"], self.bob["id"], "Awesome sprint!")
        with self.assertRaises(ConflictError):
            self.service.create_kudos(
                self.alice["id"], self.bob["id"], "  awesome sprint! "
            )

        # Remaining 4 allowed (limit configured to 5 in setUp); 6th triggers RateLimitError
        for idx in range(4):
            self.service.create_kudos(
                self.alice["id"], self.carol["id"], f"Kudos number {idx}"
            )
        with self.assertRaises(RateLimitError):
            self.service.create_kudos(self.alice["id"], self.carol["id"], "6th burst")

    def test_us04_public_feed_order_and_pagination(self) -> None:
        """US-04: Public feed returns newest visible kudos first with accurate pagination."""
        created_ids = []
        for idx in range(5):
            item = self.service.create_kudos(
                self.alice["id"], self.bob["id"], f"Appreciation #{idx}"
            )
            created_ids.append(item["id"])

        page1 = self.service.get_feed(self.carol["id"], limit=2, offset=0)
        page2 = self.service.get_feed(self.carol["id"], limit=2, offset=2)
        page3 = self.service.get_feed(self.carol["id"], limit=2, offset=4)

        self.assertEqual(page1["total"], 5)
        self.assertTrue(page1["has_more"])
        self.assertEqual([i["id"] for i in page1["items"]], [created_ids[4], created_ids[3]])
        self.assertEqual([i["id"] for i in page2["items"]], [created_ids[2], created_ids[1]])
        self.assertFalse(page3["has_more"])
        self.assertEqual([i["id"] for i in page3["items"]], [created_ids[0]])

    def test_us05_moderation_hide_restore_delete_and_rbac(self) -> None:
        """US-05: Admin can hide/restore/delete with audit trail; non-admin gets ForbiddenError."""
        kudos = self.service.create_kudos(
            self.alice["id"], self.bob["id"], "Thank you for mentoring!"
        )

        # Non-admin cannot hide, delete, or view hidden items
        with self.assertRaises(ForbiddenError):
            self.service.moderate_kudos(
                self.alice["id"], kudos["id"], "hide", "Unauthorized attempt"
            )
        with self.assertRaises(ForbiddenError):
            self.service.delete_kudos(self.bob["id"], kudos["id"])
        with self.assertRaises(ForbiddenError):
            self.service.get_feed(self.alice["id"], include_hidden=True)

        # Admin must provide non-empty reason
        with self.assertRaises(ValidationError):
            self.service.moderate_kudos(self.admin["id"], kudos["id"], "hide", "   ")

        # Admin hides kudos -> disappears from public feed, audit trail populated
        moderated = self.service.moderate_kudos(
            self.admin["id"], kudos["id"], "hide", "Off-topic solicitation"
        )
        self.assertFalse(moderated["is_visible"])
        self.assertEqual(moderated["moderated_by"], self.admin["id"])
        self.assertIsNotNone(moderated["moderated_at"])
        self.assertEqual(moderated["reason_for_moderation"], "Off-topic solicitation")

        public_feed = self.service.get_feed(self.bob["id"])
        self.assertEqual(public_feed["total"], 0)

        admin_feed = self.service.get_feed(self.admin["id"], include_hidden=True)
        self.assertEqual(admin_feed["total"], 1)
        self.assertFalse(admin_feed["items"][0]["is_visible"])

        # Admin restores kudos -> visible again
        restored = self.service.moderate_kudos(
            self.admin["id"], kudos["id"], "restore", "Reviewed and approved"
        )
        self.assertTrue(restored["is_visible"])
        self.assertEqual(self.service.get_feed(self.bob["id"])["total"], 1)

        # Admin deletes kudos permanently
        deleted = self.service.delete_kudos(self.admin["id"], kudos["id"])
        self.assertTrue(deleted["deleted"])
        self.assertEqual(
            self.service.get_feed(self.admin["id"], include_hidden=True)["total"], 0
        )
        with self.assertRaises(NotFoundError):
            self.service.delete_kudos(self.admin["id"], kudos["id"])


class TestKudosHTTPAPI(unittest.TestCase):
    """End-to-end HTTP API tests against an ephemeral ThreadingHTTPServer."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "http_kudos.db")
        self.service = KudosService(db_path=self.db_path)
        self.service.seed_default_users()
        self.server = create_server(host="127.0.0.1", port=0, service=self.service)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def _request(
        self,
        method: str,
        path: str,
        user_id: int = 1,
        body: dict = None,
    ):
        url = f"http://127.0.0.1:{self.port}{path}"
        headers = {"X-User-Id": str(user_id)} if user_id is not None else {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw.startswith("{") else raw
        except HTTPError as err:
            try:
                raw = err.read().decode("utf-8")
                return err.code, json.loads(raw)
            finally:
                err.close()

    def test_end_to_end_http_workflow(self) -> None:
        """Verify UI delivery, colleague listing, kudos lifecycle, RBAC, and moderation via HTTP."""
        # Dashboard HTML loads
        with urlopen(f"http://127.0.0.1:{self.port}/", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("Datacom Employee Portal", resp.read().decode("utf-8"))

        # Unauthenticated API call returns 401
        status, _ = self._request("GET", "/api/users", user_id=None)
        self.assertEqual(status, 401)

        # Employee lists colleagues (Alice id=1 -> excludes Alice)
        status, users_data = self._request("GET", "/api/users", user_id=1)
        self.assertEqual(status, 200)
        self.assertEqual(len(users_data["users"]), 3)

        # Employee creates kudos for Bob (id=2)
        status, created = self._request(
            "POST",
            "/api/kudos",
            user_id=1,
            body={"recipient_id": 2, "message": "Great automation script!"},
        )
        self.assertEqual(status, 201)
        kudos_id = created["kudos"]["id"]

        # Duplicate returns 409
        status, _ = self._request(
            "POST",
            "/api/kudos",
            user_id=1,
            body={"recipient_id": 2, "message": "Great automation script!"},
        )
        self.assertEqual(status, 409)

        # Employee attempting moderation returns 403
        status, _ = self._request(
            "PATCH",
            f"/api/kudos/{kudos_id}/moderate",
            user_id=1,
            body={"action": "hide", "reason": "Not allowed"},
        )
        self.assertEqual(status, 403)

        # Admin (id=4) hides kudos -> disappears from public feed
        status, mod_resp = self._request(
            "PATCH",
            f"/api/kudos/{kudos_id}/moderate",
            user_id=4,
            body={"action": "hide", "reason": "Policy test"},
        )
        self.assertEqual(status, 200)
        self.assertFalse(mod_resp["kudos"]["is_visible"])

        status, feed_resp = self._request("GET", "/api/kudos", user_id=2)
        self.assertEqual(status, 200)
        self.assertEqual(feed_resp["total"], 0)

        # Admin deletes kudos permanently -> 200
        status, del_resp = self._request("DELETE", f"/api/kudos/{kudos_id}", user_id=4)
        self.assertEqual(status, 200)
        self.assertTrue(del_resp["deleted"])


if __name__ == "__main__":
    unittest.main()
