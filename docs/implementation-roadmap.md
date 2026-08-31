# Backend Implementation Roadmap
## Field Service Repair Operations Platform — MVP

Companion document to the Product Definition and Technical Blueprint. This roadmap breaks backend implementation into small, independently testable milestones, each sized for a single focused development session (roughly half a day to a full day). No architecture decisions are revisited here — this is execution planning only.

**Stack constant across all milestones:** FastAPI, PostgreSQL, SQLAlchemy Async, Alembic, Pydantic v2, JWT. Architecture: Router → Service → SQLAlchemy.

---

## Milestone 0 — Project Bootstrap

**Goal:** a running FastAPI app with the folder structure from the Technical Blueprint in place, deployable locally.

**Components implemented:**
- Repo structure (`app/`, `alembic/`, `tests/`)
- `main.py` with app instantiation
- Basic `/health` endpoint
- Dockerfile + docker-compose (app + Postgres) for local dev
- `.env.example`, dependency management (requirements.txt / poetry / uv)

**Dependencies:** none — this is the starting point.

**Database changes:** none yet (Postgres container running, empty).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Confirms app + DB connectivity |

**Business logic:** none.

**Validation rules:** none.

**Testing checklist:**
- [ ] App starts locally via `uvicorn`
- [ ] App starts via docker-compose
- [ ] `/health` returns 200 and confirms DB connection
- [ ] Repo structure matches the blueprint's package layout

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low — mostly mechanical. Only risk is under/over-engineering the folder structure this early; stick to the blueprint's structure exactly.
**Prerequisites:** none.

---

## Milestone 1 — Configuration

**Goal:** centralized, environment-driven configuration with no hardcoded secrets or values anywhere in the app.

**Components implemented:**
- `config.py` using `pydantic-settings`
- Settings for: DB URL, JWT secret/algorithm/expiry, S3 credentials/bucket/endpoint, Anthropic API key, environment name (dev/prod)
- Settings loaded once via a cached dependency (`lru_cache` or module-level singleton)

**Dependencies:** Milestone 0.

**Database changes:** none.

**API endpoints:** none new.

**Business logic:** fail fast on startup if required env vars are missing (don't discover a missing `JWT_SECRET` at request time in production).

**Validation rules:** Pydantic settings validation (types, required fields).

**Testing checklist:**
- [ ] App refuses to start with missing required env vars, with a clear error message
- [ ] Settings correctly load from `.env` in dev and from real env vars in prod-like mode
- [ ] No secret values appear in logs or version control

**Complexity:** Low
**Estimated time:** 0.25 day
**Risks:** Low.
**Prerequisites:** Milestone 0.

---

## Milestone 2 — Database Infrastructure

**Goal:** async SQLAlchemy engine/session wiring and Alembic configured and producing working migrations.

**Components implemented:**
- `database.py`: async engine, `AsyncSession` factory, declarative `Base`
- `get_db` FastAPI dependency (yields a session per request, commits/rolls back correctly)
- Alembic initialized, configured for async (using `run_sync` pattern), pointed at `Base.metadata`
- Base model mixin: `id` (UUID default), `created_at`, `updated_at` (server-side timestamps)

**Dependencies:** Milestones 0–1.

**Database changes:** Alembic environment created; no domain tables yet (first real migration happens in Milestone 3).

**API endpoints:** none new (though `/health` now genuinely checks DB connectivity through this layer).

**Business logic:** consistent transaction handling pattern — session per request, commit on success, rollback on exception, always closed.

**Validation rules:** none yet (this is infrastructure).

**Testing checklist:**
- [ ] `alembic upgrade head` and `alembic downgrade base` both run cleanly against a fresh DB
- [ ] A session obtained via `get_db` correctly commits on success and rolls back on an unhandled exception
- [ ] UUID + timestamp mixin behaves correctly (auto-generated on insert, `updated_at` refreshes on update)

**Complexity:** Medium (async Alembic setup has a few known gotchas)
**Estimated time:** 0.5–1 day
**Risks:** Medium — async Alembic configuration is the one part of this milestone that's easy to get subtly wrong (sync vs async engine mismatches). Budget extra time if this is your first async Alembic setup.
**Prerequisites:** Milestones 0–1.

---

## Milestone 3 — Organizations & Users (Models Only)

**Goal:** the two foundational tenancy tables exist and are migrated, with no API yet — this milestone is purely data-layer.

**Components implemented:**
- `models/organization.py`, `models/user.py`
- `schemas/organization.py`, `schemas/user.py` (basic shapes, refined further once auth needs them)
- First real Alembic migration

**Dependencies:** Milestone 2.

**Database changes:**
- `organizations` table (id, name, created_at)
- `users` table (id, organization_id FK, email, hashed_password, full_name, role enum, is_active, created_at) with unique constraint on `(organization_id, email)`
- `UserRole` Python enum (`owner`, `dispatcher`, `technician`), enforced via SQLAlchemy `Enum(native_enum=False)` per the frozen architecture

**API endpoints:** none yet.

**Business logic:** none yet (data layer only).

**Validation rules:** `role` must be one of the enum values (enforced at DB + Pydantic layer).

**Testing checklist:**
- [ ] Migration creates both tables with correct columns/constraints
- [ ] Attempting to insert a duplicate `(organization_id, email)` fails at the DB level
- [ ] Attempting to insert an invalid `role` value fails at the DB level (CHECK constraint)

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low.
**Prerequisites:** Milestone 2.

---

## Milestone 4 — Authentication

**Goal:** a user can register an organization + owner account, log in, and receive a working JWT.

**Components implemented:**
- `core/security.py`: password hashing (bcrypt/passlib), JWT encode/decode helpers
- `services/auth_service.py`: register, login, refresh logic
- `routers/auth.py`
- `dependencies.py`: `get_current_user` (decodes JWT, loads user, raises 401 if invalid/expired)

**Dependencies:** Milestone 3.

**Database changes:** none beyond Milestone 3 (uses existing `users`/`organizations` tables).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register` | Create organization + owner user |
| POST | `/auth/login` | Authenticate, return access + refresh token |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| GET | `/auth/me` | Return current user profile |

**Business logic:**
- Registration creates an `organizations` row and a `users` row with `role=owner` in a single transaction — if either fails, neither is persisted.
- JWT payload includes `user_id`, `organization_id`, `role` (per frozen architecture — avoids extra DB lookups for tenant scoping downstream).
- Access token short-lived (~30–60 min), refresh token longer-lived (~7–30 days).

**Validation rules:**
- Email format validated, must be unique within the organization at registration.
- Password minimum length/complexity (keep this simple — e.g., min 8 characters, no exotic rules for MVP).
- Login rejects inactive users (`is_active=false`).

**Testing checklist:**
- [ ] Register creates both org and user, returns usable tokens
- [ ] Login with correct credentials succeeds; wrong password fails with 401
- [ ] Expired access token is rejected by `get_current_user`
- [ ] Refresh token correctly issues a new access token
- [ ] Duplicate email within the same org is rejected; same email in a *different* org is allowed
- [ ] Inactive user cannot log in

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Medium — JWT expiry/refresh logic and password hashing are security-sensitive; worth extra test coverage here rather than rushing.
**Prerequisites:** Milestone 3.

---

## Milestone 5 — Authorization (Roles & Tenant Scoping)

**Goal:** every subsequent endpoint can be protected by role, and every query is automatically scoped to the caller's organization.

**Components implemented:**
- `require_role(*roles)` dependency
- A documented convention (used from here on in every service method): all queries filter by `organization_id` taken from `current_user`, never from client input
- `routers/users.py` (basic CRUD, gated by role) — this is the first real test of the role/tenant pattern

**Dependencies:** Milestone 4.

**Database changes:** none new.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/users` | List users in organization (owner/dispatcher) |
| POST | `/users` | Create a user (owner only) |
| GET | `/users/{id}` | Get user detail |
| PATCH | `/users/{id}` | Update role/active status (owner only) |
| DELETE | `/users/{id}` | Deactivate user (owner only) |

**Business logic:**
- Owner can manage all users in their org; dispatcher can view but not create/edit users; technician has no access to this module at all.
- A user can never modify their own role (prevents accidental lockout) — service-layer check.

**Validation rules:**
- Cannot deactivate the last remaining `owner` in an organization (prevents orphaned orgs).
- Role changes restricted to the three defined enum values.

**Testing checklist:**
- [ ] Technician gets 403 on all `/users` routes
- [ ] Dispatcher can list/view but gets 403 on create/edit/delete
- [ ] Owner can perform full CRUD
- [ ] A user from Organization A cannot see or modify a user from Organization B (critical tenant-isolation test — repeat this pattern for every module going forward)
- [ ] Attempting to deactivate the sole owner is rejected

**Complexity:** Medium
**Estimated time:** 0.75 day
**Risks:** Medium — this milestone establishes the tenant-isolation pattern every later module depends on. Getting the cross-org test right here (and treating it as a template) is the highest-leverage testing investment in the whole roadmap.
**Prerequisites:** Milestone 4.

---

## Milestone 6 — Customers

**Goal:** dispatcher/owner can create and manage customer records.

**Components implemented:**
- `models/customer.py`, `schemas/customer.py`, `services/customer_service.py`, `routers/customers.py`

**Dependencies:** Milestone 5 (reuses role/tenant-scoping pattern).

**Database changes:**
- `customers` table (id, organization_id FK, full_name, phone, notes, created_at), indexed on `(organization_id, phone)` for lookup/dedup.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/customers` | List/search customers (by name/phone) |
| POST | `/customers` | Create customer |
| GET | `/customers/{id}` | Customer detail |
| PATCH | `/customers/{id}` | Update customer |
| DELETE | `/customers/{id}` | Archive customer (soft delete via `is_active` or similar — no hard deletes of customers given job history depends on them) |

**Business logic:**
- Search is a simple `ILIKE` on name/phone — no need for full-text search infrastructure at this volume.
- Soft delete only — a customer with existing jobs must never be hard-deleted (referential integrity + audit trail).

**Validation rules:**
- Phone number format (basic — don't over-engineer international formats given the CIS-focused market).
- `full_name` required, non-empty.

**Testing checklist:**
- [ ] CRUD works within an organization
- [ ] Cross-org isolation holds (repeat the Milestone 5 pattern)
- [ ] Search by partial name and partial phone both return expected matches
- [ ] Deleting a customer with existing jobs is blocked or soft-deletes without breaking job references (decide and test explicitly)

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low.
**Prerequisites:** Milestone 5.

---

## Milestone 7 — Equipment

**Goal:** equipment records exist, linked to customers, carrying the `installation_address` per the frozen address model.

**Components implemented:**
- `models/equipment.py`, `schemas/equipment.py`, `services/equipment_service.py`, `routers/equipment.py`

**Dependencies:** Milestone 6.

**Database changes:**
- `equipment` table (id, organization_id FK, customer_id FK, type, brand, model, serial_number, installation_address, install_date, warranty_until), indexed on `customer_id`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/equipment` | List equipment for a customer |
| POST | `/customers/{customer_id}/equipment` | Add equipment |
| GET | `/equipment/{id}` | Equipment detail + repair history (jobs referencing this equipment) |
| PATCH | `/equipment/{id}` | Update equipment (including `installation_address`) |

**Business logic:**
- "Repair history" on equipment detail is a read-through query joining `jobs` — no denormalized copy.
- Updating `installation_address` never retroactively changes `jobs.address_snapshot` on past jobs — this is the core guarantee of the frozen address model, and it should have an explicit test.

**Validation rules:**
- `customer_id` must belong to the same organization as the equipment being created (reject cross-org references even within a single org's request).
- `serial_number` optional, but if provided, no uniqueness constraint enforced at this stage (some businesses won't have reliable serials — don't block on it).

**Testing checklist:**
- [ ] CRUD + cross-org isolation
- [ ] Equipment detail correctly aggregates job history
- [ ] Updating `installation_address` does not alter `address_snapshot` on any existing job (explicit regression test — this is the address model's key invariant)
- [ ] Creating equipment under a customer from a different organization is rejected

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low — the one thing to be careful about is the address-snapshot invariant; write that test before moving on.
**Prerequisites:** Milestone 6.

---

## Milestone 8 — Repair Jobs (Core Creation)

**Goal:** a job can be created, capturing the address snapshot, and appears correctly scoped and listed.

**Components implemented:**
- `models/job.py` (Job only — status history comes in Milestone 9)
- `schemas/job.py`, `services/job_service.py`, `routers/jobs.py`
- `JobStatus` Python enum

**Dependencies:** Milestone 7.

**Database changes:**
- `jobs` table per the frozen schema: organization_id, customer_id, equipment_id (nullable), assigned_technician_id (nullable), created_by_id, status (enum, `native_enum=False`), reported_issue, address_snapshot, scheduled_at, completed_at, is_warranty_claim, origin_job_id (self-FK), warranty_expires_at.
- Indexes: `(organization_id, status)`, `(organization_id, assigned_technician_id)`, `(equipment_id)`, `(scheduled_at)`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/jobs` | List jobs, filterable by status/technician/date range |
| POST | `/jobs` | Create job |
| GET | `/jobs/{id}` | Job detail (aggregate view — sub-resources added in later milestones will populate this) |
| PATCH | `/jobs/{id}` | Update editable fields (issue, address, schedule — not status, which is Milestone 9) |
| DELETE | `/jobs/{id}` | Cancel job (soft — sets status to `cancelled`, does not hard-delete) |

**Business logic:**
- On creation: `address_snapshot` is copied from `equipment.installation_address` if equipment is provided, otherwise taken directly from request input (job can exist without pre-registered equipment, per the domain model).
- Initial status is always `new`.
- `created_by_id` set from `current_user`, never from client input.

**Validation rules:**
- `customer_id` (and `equipment_id`, if provided) must belong to the caller's organization.
- `reported_issue` required, non-empty.
- Role restriction: technicians cannot create jobs (dispatcher/owner only) — first place the "technician sees only their own jobs" rule needs partial enforcement (full enforcement lands in Milestone 9 alongside status transitions).

**Testing checklist:**
- [ ] Job creation with equipment correctly snapshots the address
- [ ] Job creation without equipment accepts a manually entered address
- [ ] Cross-org isolation on customer/equipment references
- [ ] List endpoint filters correctly by status, technician, date range
- [ ] Technician role blocked from job creation

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Medium — this is the central entity; take the extra time to get the list/filter query right since the dashboard (Milestone 15) will build on the same query patterns.
**Prerequisites:** Milestone 7.

---

## Milestone 9 — Job Status Transitions & Timeline

**Goal:** job status changes are validated against allowed transitions and every change is recorded in an append-only timeline; technician-level "own jobs only" scoping is fully enforced.

**Components implemented:**
- `models/job_status_history.py`
- Status transition validation logic in `job_service.py`
- `routers/jobs.py` additions: assign + status-change + timeline endpoints

**Dependencies:** Milestone 8.

**Database changes:**
- `job_status_history` table (id, job_id FK, actor_id FK nullable, event_type, from_status, to_status, note, created_at), indexed on `job_id`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/assign` | Assign technician |
| POST | `/jobs/{id}/status` | Transition status (validated) |
| GET | `/jobs/{id}/timeline` | Full activity timeline |

**Business logic:**
- Allowed transitions (explicit state machine in the service layer, not enforced by DB):
  `new → assigned → en_route → in_progress → awaiting_parts → in_progress → awaiting_approval → completed`, with `cancelled` reachable from any non-terminal state.
- Every status change writes a `job_status_history` row (`event_type=status_changed`, `from_status`, `to_status`, `actor_id=current_user.id`).
- Assignment also writes a timeline entry (`event_type=assigned`, note contains technician name/id).
- `completed_at` is set only when status becomes `completed`; `warranty_expires_at` is computed here too (org-level default warranty period — hardcode a sensible default like 30/90 days for MVP, revisit configurability later).
- Technician role: can only view/act on jobs where `assigned_technician_id == current_user.id`; dispatcher/owner see all.

**Validation rules:**
- Reject status transitions not in the allowed-transitions map (400, not 500).
- Reject assignment to a user who isn't an active `technician` in the same organization.
- Reject status/assignment actions from a technician on a job not assigned to them (403).

**Testing checklist:**
- [ ] Every valid transition succeeds and writes a timeline entry
- [ ] Every invalid transition (e.g., `new → completed` directly) is rejected with a clear error
- [ ] `cancelled` is reachable from any non-terminal state
- [ ] `completed_at` and `warranty_expires_at` are set correctly on completion
- [ ] Technician can act only on their own assigned jobs; attempting another technician's job returns 403
- [ ] Timeline endpoint returns entries in correct chronological order

**Complexity:** Medium-High (the state machine + role scoping is the most business-logic-dense milestone so far)
**Estimated time:** 1–1.5 days
**Risks:** Medium — the transition rules are worth writing down as a literal lookup table in code (not scattered `if` statements) so they're easy to audit and extend.
**Prerequisites:** Milestone 8.

---

## Milestone 10 — Photos (Field Capture, Part 1)

**Goal:** technicians can attach photos to a job via S3 presigned uploads.

**Components implemented:**
- `models/photo.py`, `schemas/photo.py`
- `storage/s3_client.py` (presigned URL generation)
- `services/job_items_service.py` (photo methods)
- `routers/job_items.py` (photo routes)

**Dependencies:** Milestone 9 (needs job + role scoping in place).

**Database changes:**
- `photos` table (id, job_id FK, uploaded_by_id FK, s3_key, tag enum nullable, created_at), indexed on `job_id`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/photos/upload-url` | Get a presigned upload URL |
| POST | `/jobs/{id}/photos` | Confirm upload, persist metadata |
| GET | `/jobs/{id}/photos` | List photos for a job |

**Business logic:**
- Upload flow strictly follows the two-step pattern from the Technical Blueprint: get presigned URL → client uploads directly to S3 → confirm with metadata call.
- Bucket key convention: `{organization_id}/jobs/{job_id}/photos/{uuid}.{ext}`.
- Timeline entry written on photo add (`event_type=photo_added`).

**Validation rules:**
- Only the assigned technician (or dispatcher/owner) can add photos to a job.
- Content-type restricted to image types at presigned-URL generation time.
- `tag` if provided must be one of `before`/`after`/`general`.

**Testing checklist:**
- [ ] Presigned URL generation succeeds and is time-limited
- [ ] Metadata confirmation correctly persists `s3_key` and associates with the right job
- [ ] Cross-org / cross-technician access is blocked
- [ ] Listing photos returns them in upload order

**Complexity:** Medium (first milestone touching external infrastructure — S3)
**Estimated time:** 1 day
**Risks:** Medium — S3-compatible storage configuration (endpoint, region, path-style vs virtual-hosted addressing) varies by provider; budget time for provider-specific quirks if not using AWS directly (e.g., Yandex Object Storage).
**Prerequisites:** Milestone 9.

---

## Milestone 11 — Materials (Field Capture, Part 2)

**Goal:** technicians can log materials used on a job.

**Components implemented:**
- `models/material_item.py`, extends `job_items_service.py` / `routers/job_items.py`

**Dependencies:** Milestone 10 (same access-control pattern, simpler data).

**Database changes:**
- `material_items` table (id, job_id FK, name, quantity, unit_cost nullable, created_at), indexed on `job_id`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/materials` | Add material line item |
| GET | `/jobs/{id}/materials` | List materials for a job |
| PATCH | `/jobs/{id}/materials/{item_id}` | Edit a line item (typo correction, quantity fix) |
| DELETE | `/jobs/{id}/materials/{item_id}` | Remove a line item |

**Business logic:**
- No stock/inventory linkage — purely a flat log, per the frozen architecture.
- Timeline entry on add (`event_type=material_added`) — edits/deletes optionally logged too, but keep this lightweight (a single generic `note` entry is enough, not a full audit diff).

**Validation rules:**
- `quantity` must be positive.
- Same technician/role access rules as photos.

**Testing checklist:**
- [ ] CRUD works and is correctly scoped to job/organization/technician
- [ ] Negative or zero quantity rejected
- [ ] Editing/removing an item doesn't corrupt the timeline

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low.
**Prerequisites:** Milestone 10.

---

## Milestone 12 — Additional Work & Approval

**Goal:** technicians can flag additional work; owner/dispatcher can approve/reject/mark billed.

**Components implemented:**
- `models/additional_work_item.py`, extends `job_items_service.py` / `routers/job_items.py`

**Dependencies:** Milestone 11.

**Database changes:**
- `additional_work_items` table (id, job_id FK, description, price, status enum, created_by_id FK, created_at), indexed on `job_id` and on `(organization_id, status)` for the "unbilled additional work" dashboard metric (organization_id reachable via join, or consider denormalizing it onto this table directly for query simplicity — worth deciding here rather than in the dashboard milestone).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/additional-work` | Flag additional work (technician) |
| GET | `/jobs/{id}/additional-work` | List additional work items for a job |
| PATCH | `/jobs/{id}/additional-work/{item_id}` | Change status: approve/reject/mark billed (owner/dispatcher only) |

**Business logic:**
- Status flow: `pending → approved → billed`, or `pending → rejected` (terminal). No other transitions allowed.
- Timeline entries on flag and on each status change (`event_type=additional_work_flagged`, `additional_work_approved`, etc.).
- This table directly powers the "% of jobs with additional work" and "% billed vs unbilled" success metrics — worth keeping the query path in mind now even though the dashboard itself is a later milestone.

**Validation rules:**
- `price` must be positive.
- Technician can create but not approve/reject/bill (role check).
- Status transitions restricted to the flow above (reject invalid jumps, e.g. `rejected → billed`).

**Testing checklist:**
- [ ] Technician can flag; cannot approve/reject/bill (403)
- [ ] Owner/dispatcher can approve/reject/bill; cannot flag on behalf of a technician in a way that breaks `created_by_id` attribution
- [ ] Invalid status transitions rejected
- [ ] Cross-org isolation holds

**Complexity:** Medium
**Estimated time:** 0.75 day
**Risks:** Low-Medium.
**Prerequisites:** Milestone 11.

---

## Milestone 13 — Payments

**Goal:** simple payment status tracking per job.

**Components implemented:**
- `models/payment.py`, `schemas/payment.py`, `services/payment_service.py`, `routers/payments.py`

**Dependencies:** Milestone 12 (not technically dependent, but logically follows — sits alongside additional work as the other financial input to the dashboard).

**Database changes:**
- `payments` table (id, job_id FK unique, amount, method enum, status enum, paid_at nullable).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/jobs/{id}/payment` | Get payment status |
| PUT | `/jobs/{id}/payment` | Set/update payment (upsert — one-to-one relationship) |

**Business logic:**
- Upsert semantics: `PUT` creates if absent, updates if present (simplifies the frontend — no separate create/update calls needed for a one-to-one resource).
- Setting `status=paid` without `paid_at` auto-sets `paid_at=now()`.

**Validation rules:**
- `amount` must be positive.
- Only owner/dispatcher can set payment status (technicians don't touch financials, per the role table).

**Testing checklist:**
- [ ] Upsert creates on first call, updates on subsequent calls
- [ ] `paid_at` auto-populates correctly
- [ ] Technician blocked from this endpoint entirely
- [ ] Cross-org isolation holds

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low.
**Prerequisites:** Milestone 12.

---

## Milestone 14 — Documents (PDF Generation)

**Goal:** a job report / repair certificate PDF can be generated and stored, first synchronously (to prove correctness) and then wired through `BackgroundTasks`.

**Components implemented:**
- `documents/job_report.py` (PDF rendering logic — a simple library like `reportlab` or `weasyprint` from an HTML template)
- `models/document.py`, extends `job_items_service.py` / `routers/job_items.py`
- First real use of `workers/document_tasks.py` invoked via FastAPI `BackgroundTasks`

**Dependencies:** Milestone 13, plus Milestone 10's S3 client.

**Database changes:**
- `documents` table (id, job_id FK, type enum, s3_key, generated_at), indexed on `job_id`.

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/documents` | Trigger document generation (returns immediately, generation happens in background) |
| GET | `/jobs/{id}/documents` | List generated documents |

**Business logic:**
- Endpoint validates the job exists and is in a state where generation makes sense (e.g., allow for any job, but the natural trigger is `completed`); actual PDF rendering + S3 upload happens in a `BackgroundTasks`-scheduled function so the request returns immediately.
- PDF content: reported issue, work done (from timeline/notes), materials used, technician name, warranty terms — pulled directly from the job aggregate, no separate data entry.
- Timeline entry on generation (`event_type=document_generated`).

**Validation rules:**
- Only one "in-flight" generation per job at a time is a nice-to-have, not required for MVP — acceptable to allow concurrent triggers and just produce multiple documents if it happens.

**Testing checklist:**
- [ ] Manually calling the rendering function (outside the background task) produces a correct, readable PDF from sample job data
- [ ] Endpoint returns immediately; document appears in S3 + `documents` table shortly after
- [ ] Generated PDF content matches the job's actual data (issue, materials, technician, warranty)
- [ ] Listing documents for a job returns correct records

**Complexity:** Medium-High (first milestone combining background execution + file generation + S3 + real content assembly)
**Estimated time:** 1–1.5 days
**Risks:** Medium — PDF template/rendering library setup can eat time; keep the template intentionally plain for MVP (no need for polished design work here).
**Prerequisites:** Milestones 10, 13.

---

## Milestone 15 — Warranty Logic

**Goal:** completed jobs carry a warranty period, and new jobs on the same equipment within that window are auto-flagged as warranty claims.

**Components implemented:**
- Warranty-flagging logic added to `job_service.py` (both at job creation and at completion)
- `workers/warranty_check_task.py` — the first scheduled background task (per the frozen Background Jobs decision: invoked via a simple startup loop or external cron hitting an internal endpoint for MVP)

**Dependencies:** Milestone 9 (status transitions) and Milestone 14 (background task pattern established).

**Database changes:** none new — `is_warranty_claim`, `origin_job_id`, `warranty_expires_at` already exist on `jobs` from Milestone 8; this milestone is pure business logic.

**API endpoints:** none new (warranty flag surfaces through existing `GET /jobs/{id}` and `GET /jobs`).

**Business logic:**
- On job creation: if `equipment_id` is provided, check for a prior `completed` job on the same equipment where `warranty_expires_at >= today`. If found, auto-set `is_warranty_claim=true` and `origin_job_id` to that prior job.
- Scheduled task (daily): scans jobs approaching/at warranty expiry for reporting purposes (e.g., a future notification feature) — for MVP, this can simply update a computed flag or write a log/timeline note; keep the actual "notify someone" behavior out of scope unless the Product Definition calls for it explicitly.

**Validation rules:**
- Warranty auto-flagging is a suggestion the dispatcher can override (allow manually toggling `is_warranty_claim` on job creation/edit) — never fully lock the field.

**Testing checklist:**
- [ ] Creating a job on equipment with a recent completed job within warranty auto-flags correctly and links `origin_job_id`
- [ ] Creating a job on equipment past its warranty window does not auto-flag
- [ ] Manual override of the warranty flag works
- [ ] Scheduled task runs without error against a realistic dataset

**Complexity:** Medium
**Estimated time:** 0.75 day
**Risks:** Low-Medium — mostly a date-comparison logic correctness question; write the boundary-condition tests carefully (exactly on the expiry date, one day after, etc.).
**Prerequisites:** Milestones 9, 14.

---

## Milestone 16 — Dashboard & Metrics

**Goal:** the owner-facing dashboard endpoints return accurate, reasonably performant aggregates.

**Components implemented:**
- `services/dashboard_service.py` (this is the milestone most likely to need direct SQL/window functions rather than pure ORM queries, per the Technical Blueprint's note)
- `routers/dashboard.py`

**Dependencies:** Milestones 8–13 (needs jobs, additional work, and payments populated to compute anything meaningful).

**Database changes:** none new — possibly add supporting indexes if a specific aggregate query proves slow in testing (e.g., a composite index for the completion-time calculation).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| GET | `/dashboard/summary` | Active/delayed/completed counts, unbilled additional work count |
| GET | `/dashboard/metrics` | Avg completion time, revenue per technician, average order value, repeat-customer rate, warranty case count |

**Business logic:**
- "Delayed" = `scheduled_at < now()` and status not in (`completed`, `cancelled`).
- Revenue per technician = sum of `payments.amount` (where `status=paid`) for jobs grouped by `assigned_technician_id`.
- Repeat-customer rate = customers with more than one job / total customers with at least one job, within a period.
- All metrics scoped to organization and accept an optional date-range filter.

**Validation rules:** role-gated to owner/dispatcher only (technicians don't see the dashboard, per the role table).

**Testing checklist:**
- [ ] Each metric independently verified against a hand-computed expected value on seeded test data
- [ ] Date-range filtering works correctly
- [ ] Technician role blocked from dashboard endpoints
- [ ] Query performance sanity-checked against a moderately sized seed dataset (hundreds of jobs) — this is the one area worth a basic performance pass even at MVP stage, since it's the screen the owner opens most often

**Complexity:** Medium-High (aggregate query correctness is easy to get subtly wrong)
**Estimated time:** 1–1.5 days
**Risks:** Medium — the main risk is metrics that are subtly wrong (off-by-one in date ranges, double-counting), not that the feature is hard to build. Budget real time for verifying each number against manually computed expectations.
**Prerequisites:** Milestones 8–13.

---

## Milestone 17 — Background Task Infrastructure Review

**Goal:** consolidate and harden the `BackgroundTasks` usage introduced piecemeal in Milestones 14–15, and document the trigger point for the future arq migration.

**Components implemented:**
- Review/refactor of `workers/` package for consistency (naming, error handling, logging)
- Basic retry-on-failure handling where feasible within `BackgroundTasks`' limitations (e.g., a simple try/except + status field update, since `BackgroundTasks` has no built-in retry)
- A short internal note (can live in the codebase README) documenting: "migrate to arq+Redis when X happens" (per the frozen decision — first production users needing reliable retries/scheduling)

**Dependencies:** Milestones 14, 15.

**Database changes:** none.

**API endpoints:** none new.

**Business logic:** ensure every background task updates a persisted status field (e.g., `documents` implicitly via existence, `ai_tasks` explicitly in Milestone 18) so a failed task is visible/debuggable rather than silently disappearing.

**Validation rules:** none new.

**Testing checklist:**
- [ ] Simulated failure in a background task (e.g., S3 upload failure) is logged and doesn't crash the request/response cycle
- [ ] No background task silently fails without some observable trace (log line at minimum)

**Complexity:** Low-Medium
**Estimated time:** 0.5 day
**Risks:** Low — this is a cleanup/hardening pass, not new feature work.
**Prerequisites:** Milestones 14, 15.

---

## Milestone 18 — AI Integration

**Goal:** the optional AI layer is implemented, fully isolated, and the app remains 100% functional with it disabled.

**Components implemented:**
- `models/ai_task.py`, `schemas/ai_task.py`
- `services/ai_service.py` (calls Anthropic API)
- `routers/ai.py`
- `workers/ai_tasks.py` (background execution per the frozen async-only rule for AI)

**Dependencies:** Milestones 9 (job data to summarize/query), 17 (background task pattern).

**Database changes:**
- `ai_tasks` table (id, organization_id FK, job_id FK nullable, task_type enum, status enum, input_ref, output, error, created_at, completed_at).

**API endpoints:**
| Method | Route | Purpose |
|---|---|---|
| POST | `/ai/voice-note` | Submit voice note for transcription → structured note |
| POST | `/ai/jobs/{id}/summary` | Request repair history summary |
| POST | `/ai/jobs/{id}/suggest-additional-work` | Suggest additional work from technician notes |
| POST | `/ai/query` | Natural-language Q&A over job history |
| GET | `/ai/tasks/{id}` | Poll AI task status/result |

**Business logic:**
- Every `/ai/*` call creates a `pending` `ai_tasks` row and returns immediately; the actual Anthropic API call happens in a background task, writing `done`/`failed` + output back.
- AI never writes directly to job/additional-work/payment state — outputs are always surfaced as suggestions the frontend presents for human action (e.g., "suggested additional work" shown next to the manual add-item form, not auto-inserted).
- A feature flag (env-driven, e.g., `AI_ENABLED`) gates whether `/ai/*` routes are even registered — proves the "fully optional" requirement concretely rather than just by convention.

**Validation rules:**
- `job_id`, when provided, must belong to the caller's organization.
- Reasonable input size limits on voice notes / free-text queries to avoid runaway API costs.

**Testing checklist:**
- [ ] With `AI_ENABLED=false`, `/ai/*` routes return 404 (not registered) and the rest of the app is unaffected
- [ ] With AI enabled, a task is created as `pending`, transitions to `done` with a plausible output, or `failed` with a captured error, on a real (or mocked) Anthropic API call
- [ ] Frontend polling pattern works (repeated `GET /ai/tasks/{id}` reflects state changes)
- [ ] AI output never mutates job/additional-work/payment records directly — verified by inspecting DB state after an AI call

**Complexity:** Medium-High
**Estimated time:** 1–1.5 days
**Risks:** Medium — the main risk is scope creep (making AI feel too "smart"/autonomous). Keep strictly to suggestion-only outputs per the Product Definition's hard rule.
**Prerequisites:** Milestones 9, 17.

---

## Milestone 19 — Final Cleanup & Hardening

**Goal:** production-readiness pass across the whole backend before handing off to frontend integration / pilot users.

**Components implemented:**
- Centralized exception handlers (`core/exceptions.py`) producing consistent error response shapes across all routers
- Basic rate limiting on `/auth/*` endpoints (login especially)
- Request/response logging (without leaking secrets or PII into logs)
- Seed/demo data script (creates a sample organization with customers, equipment, jobs across various statuses — useful for demos and for the dashboard's realistic-volume testing)
- Full manual smoke test of every primary workflow from the Product Definition, end to end, using the seed data

**Dependencies:** all previous milestones.

**Database changes:** none, unless smoke testing surfaces a missing index or constraint (treat any such finding as a small follow-up migration, not a redesign).

**API endpoints:** none new.

**Business logic:** none new — this milestone is about correctness and robustness of what already exists.

**Validation rules:** review all prior milestones' validation rules for consistency (e.g., consistent error message format, consistent 4xx vs 5xx usage).

**Testing checklist:**
- [ ] Every workflow from Product Definition Section 7 (intake → assignment → execution → additional work → completion/documents → payment → warranty) walked through manually end to end
- [ ] Auth rate limiting confirmed (repeated failed logins throttled)
- [ ] Error responses consistent in shape across all modules
- [ ] Seed script runs cleanly on a fresh database and produces a demo-ready dataset
- [ ] No secrets/PII appear in logs

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Low-Medium — mostly about discipline in actually walking every workflow rather than assuming individual milestone tests add up to end-to-end correctness.
**Prerequisites:** all previous milestones.

---

## Summary Table

| # | Milestone | Complexity | Est. Time | Prerequisites |
|---|---|---|---|---|
| 0 | Project Bootstrap | Low | 0.5 day | — |
| 1 | Configuration | Low | 0.25 day | 0 |
| 2 | Database Infrastructure | Medium | 0.5–1 day | 0–1 |
| 3 | Organizations & Users (models) | Low | 0.5 day | 2 |
| 4 | Authentication | Medium | 1 day | 3 |
| 5 | Authorization & Tenant Scoping | Medium | 0.75 day | 4 |
| 6 | Customers | Low | 0.5 day | 5 |
| 7 | Equipment | Low | 0.5 day | 6 |
| 8 | Repair Jobs (core) | Medium | 1 day | 7 |
| 9 | Job Status & Timeline | Medium-High | 1–1.5 days | 8 |
| 10 | Photos | Medium | 1 day | 9 |
| 11 | Materials | Low | 0.5 day | 10 |
| 12 | Additional Work & Approval | Medium | 0.75 day | 11 |
| 13 | Payments | Low | 0.5 day | 12 |
| 14 | Documents (PDF) | Medium-High | 1–1.5 days | 10, 13 |
| 15 | Warranty Logic | Medium | 0.75 day | 9, 14 |
| 16 | Dashboard & Metrics | Medium-High | 1–1.5 days | 8–13 |
| 17 | Background Task Hardening | Low-Medium | 0.5 day | 14, 15 |
| 18 | AI Integration | Medium-High | 1–1.5 days | 9, 17 |
| 19 | Final Cleanup & Hardening | Medium | 1 day | all |

**Total estimated time:** ~16.5–20.75 days of focused solo work — comfortably fits a 6-week (30 working day) timeline with meaningful buffer for the inevitable slippage, review cycles, and frontend integration touchpoints.

---

## Recommended Implementation Order

The order above **is** the recommended order — it was structured so each milestone's dependencies are always fully satisfied by what precedes it, and so the riskiest/most novel technical pieces (async Alembic, S3 presigned uploads, background PDF generation, aggregate dashboard queries) are each encountered once, deliberately, rather than discovered mid-flow inside a bigger milestone.

**Which milestone should be implemented first:** **Milestone 0 (Project Bootstrap)** — no ambiguity here; everything depends on it.

**MVP checkpoint:** **Milestone 16 (Dashboard & Metrics)**. By this point, every primary workflow in the Product Definition is fully implemented and testable end to end: intake, assignment, field execution, additional work approval, documents, warranty, and the owner's operational visibility — which is the product's entire reason for existing. If you can demo Milestones 0–16 working together, you have a real MVP a pilot customer could use. Milestones 17–19 make it production-grade and add the AI layer, but the core product claim is fully proven at Milestone 16.

**Features that can safely be postponed if time runs out** (in order of how safely they can be cut, safest first):

1. **Milestone 18 (AI Integration)** — explicitly optional per the Product Definition; the product is complete and sellable without it. Cut first if the schedule slips.
2. **Milestone 17 (Background Task Hardening)** — the basic `BackgroundTasks` usage from Milestones 14–15 already works; this milestone is polish, not new capability. Can be trimmed to "just make sure nothing crashes" if needed.
3. **Milestone 15 (Warranty Logic)** — genuinely useful but not blocking for a first pilot; a company can track warranty manually for a few more weeks while this catches up, if absolutely necessary. Postpone only as a last resort, since it's one of the Product Definition's named problems.
4. **Parts of Milestone 16 (Dashboard)** — if time is extremely tight, ship `/dashboard/summary` (the operational counts) and defer the more complex `/dashboard/metrics` aggregates (revenue per technician, repeat-customer rate) to a fast-follow — but do not cut the dashboard entirely, since owner visibility is the core value proposition.

**What should never be cut, even under time pressure:** Milestones 0–13 (everything through Payments) — this is the operational backbone the entire Product Definition is built around. If forced to choose between finishing Milestone 13 properly versus starting Milestone 14 early, finish 13 first.
