# Kora Repair Platform — Backend

Field service repair operations MVP backend. FastAPI + PostgreSQL + SQLAlchemy Async + Alembic + Pydantic v2, Router → Service → SQLAlchemy architecture.

Covers Milestones 0–19 of the implementation roadmap — the full backend MVP described in the Product Definition and Technical Blueprint: auth, org/user management, customers, equipment, the repair-job lifecycle (assignment, status transitions, timeline), photos/materials/additional work, payments, PDF documents, warranty logic, the owner dashboard, an optional AI-assist layer, and the hardening pass (rate limiting, centralized error handling, seed data) covered below. The run instructions haven't changed since Milestone 0.

## Project structure

```
app/
├── main.py          # App instantiation + /health (Milestone 0), now config-driven (Milestone 1)
├── config.py         # Centralized settings, pydantic-settings, fail-fast on missing required vars (Milestone 1)
├── models/           # SQLAlchemy ORM models (from Milestone 3)
├── schemas/          # Pydantic v2 request/response models (from Milestone 3)
├── routers/          # HTTP layer — thin, delegates to services (from Milestone 4)
├── services/         # Business logic (from Milestone 4)
├── storage/          # S3 client wrapper (from Milestone 10)
├── documents/         # PDF generation (from Milestone 14)
├── workers/          # Background task functions (from Milestone 14)
└── core/             # security.py, exceptions.py (from Milestone 4)

alembic/               # Migrations (from Milestone 2)
tests/                 # Test suite
```

Empty package directories are scaffolded now, per the Technical Blueprint, and filled in as their corresponding milestone is implemented.

## Option A — Run with Docker Compose (recommended)

Requires Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

Then check:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"connected"}
```

Postgres data persists in the `kora_postgres_data` volume across restarts. To reset it: `docker compose down -v`.

## Option B — Run locally without Docker (Windows / PowerShell)

Requires Python 3.13 and a local PostgreSQL instance.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env: set DATABASE_URL to point at your local Postgres instance,
# e.g. postgresql+asyncpg://kora:kora_dev_password@localhost:5432/kora_repair
# (create the `kora_repair` database and `kora` user yourself if running
# Postgres natively rather than via docker-compose's db service)

uvicorn app.main:app --reload
```

Then check `http://localhost:8000/health` in a browser or via `Invoke-RestMethod`:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

## Running tests

```bash
pytest
```

Tests mock the database connection (see `tests/test_health.py`) so they run without a live Postgres instance. This is intentional — fast, no-infra unit tests stay mocked; real DB connectivity is proven separately via the docker-compose smoke test above.

## Seed / demo data

```bash
python -m app.seed_demo_data
```

Requires a running, migrated Postgres and (for the one document it generates) a running MinIO — the same stack `docker-compose up` provides. Creates one demonstration organization — an owner, a dispatcher, two technicians, three customers with equipment, and five jobs spanning the full lifecycle (new, mid-flight with a pending additional-work decision, completed with a paid invoice and a generated PDF report, a same-equipment follow-up that auto-flags as a warranty claim, and a cancelled job) — by calling the real service-layer functions rather than raw inserts, so running it also doubles as an end-to-end smoke test of every primary workflow in the Product Definition's Section 7. Prints login credentials and the resulting dashboard numbers at the end. Not idempotent — every run creates a fresh organization; running it twice just leaves two demo orgs behind, which is harmless.

## Rate limiting

`POST /auth/login` is rate-limited: 5 attempts per 60-second window, keyed by client IP (`app/core/rate_limit.py`). In-memory and in-process — no Redis, consistent with the background-tasks decision below — so limits reset on restart and aren't shared across multiple worker processes; fine for the MVP's single-process deployment, revisit if that ever changes. Register and refresh aren't rate-limited; only login is a credential-guessing surface.

## Error responses

Every error response across the API — including a raised `HTTPException`, a Pydantic request-validation failure, and a genuinely unhandled exception (a bug) — has the same `{"detail": "<string>"}` shape (`app/core/exceptions.py`). Validation failures previously returned a list of structured error objects under `detail`; unhandled exceptions previously returned a bare-text, non-JSON 500. An unhandled exception's real error and traceback are logged server-side; the client only ever sees a generic "An unexpected error occurred" message.

## Background tasks

`app/workers/` holds two background tasks, both run via FastAPI's
`BackgroundTasks` (or, for the warranty check, directly — see below), per
the Technical Blueprint's frozen decision for the MVP: no Redis, no
separate worker process.

- `document_tasks.generate_document` — triggered by `POST
  /jobs/{id}/documents`, scheduled via `BackgroundTasks.add_task(...)`.
  Opens its own DB session, renders the PDF, uploads it to S3, and
  persists a `Document` row + timeline entry in one commit — or none of
  it, on failure (rolled back, logged, request/response cycle
  unaffected). A failed run simply leaves no `Document` row behind; that
  absence *is* the status signal, so no separate status column exists.
- `warranty_check_task.run_warranty_check` — a standalone, directly-
  callable function (see its own module docstring for why no startup-loop
  or cron wiring exists yet). Read-only: logs jobs whose warranty is at
  or approaching expiry, writes nothing to the database.

Both wrap their work in try/except + log (Milestone 17's hardening pass —
before that, only `document_tasks` had this; `warranty_check_task` was
brought in line with it) — this is the ceiling of "retry" that
`BackgroundTasks` can meaningfully offer: it runs a task exactly once,
so there's no retry loop to add, only making sure a failure is visible
(a log line, an absent row) instead of silently disappearing.

**Migrate to arq + Redis when:** per the Technical Blueprint's Section 9,
this becomes worth the added operational cost once either becomes true —

1. Real users depend on a background task (document generation, and
   later AI processing) not silently failing, and need actual retry
   guarantees rather than "check the logs, try again manually."
2. The warranty check needs guaranteed daily execution rather than
   "runs if a process happens to invoke it" — i.e., once it's actually
   wired to a scheduler and that scheduler's reliability starts to matter.

Until then, `BackgroundTasks` plus the try/except+log pattern above is
the deliberate choice — not a placeholder waiting to be replaced on a
timeline, but the right tool for pre-production volume.

## Milestone 0 checklist status

- [x] App starts locally via `uvicorn`
- [x] App starts via docker-compose
- [x] `/health` returns 200 and confirms DB connection (and 503 with a clear reason if not)
- [x] Repo structure matches the blueprint's package layout

## Milestone 1 checklist status

- [x] App refuses to start with missing required env vars (`DATABASE_URL`, `JWT_SECRET`), with a clear error message — proven in `tests/test_config.py` via a real subprocess import, not just a mock
- [x] Settings correctly load from `.env` in dev and from real env vars in prod-like mode (pydantic-settings' `env_file` support)
- [x] No secret values appear in logs or version control (`.env` is gitignored; `.env.example` has no real secrets)

## Milestone 19 checklist status

- [x] Centralized exception handlers producing a consistent `{"detail": "<string>"}` shape across every router, including validation errors and unhandled exceptions (`app/core/exceptions.py`, `tests/test_error_handling.py`)
- [x] Basic rate limiting on `/auth/login` — confirmed via 5-attempts-per-window throttling in `tests/test_rate_limit.py`
- [x] Seed/demo data script (`python -m app.seed_demo_data`) runs cleanly against a fresh migrated database — run for real against the local docker-compose stack (Postgres + MinIO), not just written; produced a demo-ready dataset and a real, downloadable generated PDF
- [x] Full smoke test of every primary workflow from Product Definition Section 7 — end to end, via the seed script's real service-layer calls (intake → assignment → on-site execution → additional-work approval/billing → completion/documents → payment → warranty), plus the full automated test suite (see below)
- [x] No secrets/PII beyond ordinary business data appear in logs — audited every `logger.*` call site and every place a `Settings` secret field (`jwt_secret`, `database_url`, `s3_secret_key`, `anthropic_api_key`) is used; none are ever logged or printed, and `asyncpg`'s own connection-failure messages were verified empirically (not assumed) to never echo back the DSN's password

## What's NOT in this MVP

Explicitly out of scope per the Product Definition's Section 10 — not gaps, deliberate exclusions: full accounting/invoicing, warehouse/inventory tracking, payroll, multi-branch/multi-location support, a native mobile app, a customer self-service portal, SLA/contract management, and complex third-party integrations (accounting software, payment gateways, telephony).

Genuinely deferred, with a documented trigger for when to build it:

- **No frontend** — this repo is backend-only, per its own name; the Next.js app referenced in the Technical Blueprint is a separate project.
- **No arq/Redis migration** — `BackgroundTasks` remains the task-execution mechanism for document generation and the (optional, disabled-by-default) AI layer; see the "Background tasks" section above for the specific triggers that justify migrating.
- **The warranty-check scheduled task has no production wiring** (no startup sleep-loop, no cron-triggered endpoint) — `workers/warranty_check_task.run_warranty_check()` is implemented and tested as a standalone function; wiring it to an actual scheduler is a deployment-time decision, deliberately left out since Milestone 15's own scope explicitly excludes new API endpoints for it.
- **Rate limiting is single-process and in-memory** — see the "Rate limiting" section above for when a shared store (Redis, or similar) becomes worth the added infrastructure.
- **AI is disabled by default and off the request path** (`AI_ENABLED=false` — the `/ai/*` routes aren't even registered when off; enabling requires `ANTHROPIC_API_KEY`). When on, every `/ai/*` call creates a `pending` row and processes it via the same `BackgroundTasks` mechanism as document generation — see "Background tasks" above.
