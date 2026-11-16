# Datacom Peer-to-Peer Kudos System

Internal employee portal feature built using **Spec-Driven Development** for Task 2 of the **Datacom — Automation AI Accelerator: From Co-pilot to Autonomous Agent** simulation.

## Key Files

- [`SPECIFICATION.md`](./SPECIFICATION.md) — Approved functional requirements, user stories (including admin content moderation), SQL schema (`users` & `kudos`), REST API specification, frontend component hierarchy, and implementation plan.
- [`kudos_app.py`](./kudos_app.py) — Python standard-library backend + SQLite persistence, input validation, XSS escaping, duplicate cooldown, rate limiting, and RBAC moderation (`hide` / `restore` / `delete`).
- [`index.html`](./index.html) — Responsive single-page dashboard UI (`KudosForm`, `KudosPublicFeed`, `AdminModerationModal`).
- [`test_kudos.py`](./test_kudos.py) — Automated `unittest` suite covering all 5 user stories, schema audit columns, validation rules, RBAC, and end-to-end HTTP endpoints.

## Running Locally

```bash
python kudos_app.py
```

Open `http://127.0.0.1:8000` in your browser.

## Running Tests

```bash
python -m unittest test_kudos.py -v
```
