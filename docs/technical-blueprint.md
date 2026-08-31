# Technical Blueprint
## Field Service Repair Operations Platform — MVP

Companion document to the Product Definition. This translates the approved product scope into a concrete, boring, buildable architecture for a solo developer over ~6 weeks.

---

## 1. High-Level Architecture

A single monolithic backend service, a single frontend application, one database, one object storage bucket. No microservices, no message broker beyond what's needed for background jobs, no separate services for AI.

```
┌─────────────────┐        ┌──────────────────────────┐
│   Next.js App    │  HTTP  │      FastAPI Backend      │
│  (React + TS)    │◄──────►│  Router → Service → ORM   │
└─────────────────┘  JSON  └───────────┬──────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
              ┌─────▼─────┐     ┌───────▼───────┐   ┌───────▼───────┐
              │ PostgreSQL │     │  S3-compatible │   │  Background   │
              │ (primary   │     │  Object Store  │   │  Tasks         │
              │  data)     │     │  (photos, PDFs)│   │  (in-process   │
              └───────────┘     └───────────────┘   │  for MVP;      │
                                                     │  arq+Redis     │
                                                     │  post-MVP)     │
                                                     └───────┬───────┘
                                                             │
                                                     ┌───────▼───────┐
                                                     │  Anthropic API │
                                                     │  (AI features) │
                                                     └───────────────┘
```

**Components:**
- **FastAPI backend** — single deployable service, exposes REST API, owns all business logic
- **PostgreSQL** — single database, single schema, multi-tenant via `organization_id` on every row (row-level tenancy, not schema-per-tenant — simplest option that scales to hundreds of orgs)
- **Object storage (S3-compatible)** — binary files only (photos, generated PDFs); metadata lives in Postgres
- **Background tasks** — FastAPI `BackgroundTasks` for the MVP (no extra infrastructure), for anything that shouldn't block a request: document generation, AI calls, scheduled warranty checks. Migrates to arq with Redis post-MVP once retry/scheduling guarantees are needed — see Section 9.
- **Next.js frontend** — talks to the backend over REST/JSON, no server-side business logic duplicated

**Deployment shape (MVP-appropriate):** one backend container, one frontend container (or Vercel), one managed Postgres instance, one S3-compatible bucket (e.g., Yandex Object Storage / AWS S3 / MinIO). No Redis and no separate worker process needed for the MVP, since `BackgroundTasks` runs in-process — Redis is added only at the post-MVP arq migration point. No Kubernetes — a single VM or basic container hosting (Railway, Render, Yandex Cloud, etc.) is sufficient.

---

## 2. Domain Model

### Organization
**Purpose:** tenant boundary — every other entity belongs to exactly one organization.
**Responsibilities:** holds company name, contact info, settings.
**Relationships:** has many Users, Customers, Jobs, Technicians (Users with technician role).

### User
**Purpose:** any human who logs in — owner, dispatcher, or technician.
**Responsibilities:** authentication identity, role, profile info.
**Relationships:** belongs to one Organization; a Job references a User as `assigned_technician`; a Job references a User as `created_by`.

### Customer
**Purpose:** the person/business being served.
**Responsibilities:** contact info, notes, addresses.
**Relationships:** belongs to one Organization; has many Equipment records; has many Jobs.

### Equipment
**Purpose:** the physical unit being repaired (AC unit, fridge, boiler, etc.) — and, in the MVP address model, the owner of the current installation address.
**Responsibilities:** type, brand, model, serial number, install date, installation address, warranty terms if known.
**Relationships:** belongs to one Customer; has many Jobs (repair history). No separate Address entity — see "Address Model" in Section 3 for how `installation_address` and `jobs.address_snapshot` work together.

### Job (Repair Job) — the central entity
**Purpose:** represents one repair engagement from intake to close.
**Responsibilities:** status, scheduling, technician assignment, reported issue, links to all sub-records (photos, materials, additional work, payment, documents), warranty flag.
**Relationships:** belongs to Organization, Customer, Equipment; assigned to one User (technician); has many JobStatusHistory entries, Photos, MaterialItems, AdditionalWorkItems, Documents; has zero-or-one Payment; optionally references an originating Job (for warranty claims).

### JobStatusHistory (Activity Timeline)
**Purpose:** append-only audit trail of everything that happened on a job.
**Responsibilities:** records status transitions and key events (assigned, note added, additional work flagged, etc.) with timestamp and actor.
**Relationships:** belongs to one Job.

### Photo
**Purpose:** field evidence.
**Responsibilities:** stores S3 object key, uploaded_by, timestamp, optional caption/tag (before/after).
**Relationships:** belongs to one Job.

### MaterialItem
**Purpose:** a part/material used on the job (not stock-tracked — just a line item).
**Responsibilities:** name, quantity, unit cost, total.
**Relationships:** belongs to one Job.

### AdditionalWorkItem
**Purpose:** extra work discovered on-site that needs approval and billing.
**Responsibilities:** description, price, status (pending/approved/rejected/billed).
**Relationships:** belongs to one Job.

### Payment
**Purpose:** lightweight tracking of what's owed/paid on a job.
**Responsibilities:** amount, method, status (unpaid/paid), paid_at.
**Relationships:** belongs to one Job (one-to-one is sufficient for MVP; model as one-to-many only if partial payments become a real need).

### Document
**Purpose:** generated PDF (job report / repair certificate) tied to a job.
**Responsibilities:** S3 object key, document type, generated_at.
**Relationships:** belongs to one Job.

### AITask (optional/AI-support entity)
**Purpose:** tracks an async AI job (e.g., "summarize this job," "transcribe this voice note") so the frontend can poll status.
**Responsibilities:** input reference, status (pending/done/failed), output/result, timestamps.
**Relationships:** belongs to one Job; belongs to one Organization.

---

## 3. Database Design

All tables include `id` (UUID, primary key), `created_at`, `updated_at` unless noted. Multi-tenancy: every table (except a few global lookup tables, if any) carries `organization_id` with an index and a foreign key to `organizations`.

### organizations
- `id` (PK)
- `name`
- `created_at`

### users
- `id` (PK)
- `organization_id` (FK → organizations, indexed)
- `email` (unique per organization — unique constraint on `(organization_id, email)`)
- `hashed_password`
- `full_name`
- `role` (enum: `owner`, `dispatcher`, `technician`)
- `is_active`
- `created_at`

### customers
- `id` (PK)
- `organization_id` (FK, indexed)
- `full_name`
- `phone` (indexed — used for lookup/dedup)
- `notes` (text, nullable)
- `created_at`

### equipment
- `id` (PK)
- `organization_id` (FK, indexed)
- `customer_id` (FK → customers, indexed)
- `type` (e.g., "AC", "refrigerator")
- `brand`, `model`, `serial_number` (nullable)
- `installation_address` (text — the address where this specific unit is installed; kept as a plain field, not a separate normalized table, since MVP doesn't need multi-address geocoding. See "Address Model" note below.)
- `install_date` (nullable)
- `warranty_until` (date, nullable — known manufacturer warranty if applicable)

### jobs
- `id` (PK)
- `organization_id` (FK, indexed)
- `customer_id` (FK → customers, indexed)
- `equipment_id` (FK → equipment, indexed, nullable — a job could theoretically exist without a pre-registered equipment record, created inline)
- `assigned_technician_id` (FK → users, indexed, nullable until assigned)
- `created_by_id` (FK → users)
- `status` (`JobStatus` enum — see "Status Fields" below: `new`, `assigned`, `en_route`, `in_progress`, `awaiting_parts`, `awaiting_approval`, `completed`, `cancelled`)
- `reported_issue` (text)
- `address_snapshot` (text — copied from `equipment.installation_address` at job creation time; preserves historical accuracy even if the customer's or equipment's address later changes. See "Address Model" note below.)
- `scheduled_at` (timestamp, nullable)
- `completed_at` (timestamp, nullable)
- `is_warranty_claim` (boolean, default false)
- `origin_job_id` (FK → jobs, nullable, self-referencing — the job this warranty claim originated from)
- `warranty_expires_at` (date, nullable — set on completion based on org's default warranty period)
- **Indexes:** `(organization_id, status)`, `(organization_id, assigned_technician_id)`, `(equipment_id)`, `(scheduled_at)` for delayed-job queries.
- **Constraint:** `completed_at` should only be set when `status = 'completed'` (enforced in service layer, not DB constraint, to keep migrations simple).

### job_status_history
- `id` (PK)
- `job_id` (FK → jobs, indexed)
- `actor_id` (FK → users, nullable — system-generated entries have null actor)
- `event_type` (e.g., `status_changed`, `note_added`, `additional_work_flagged`)
- `from_status`, `to_status` (nullable, only for status_changed events)
- `note` (text, nullable)
- `created_at`

### photos
- `id` (PK)
- `job_id` (FK → jobs, indexed)
- `uploaded_by_id` (FK → users)
- `s3_key`
- `tag` (nullable enum: `before`, `after`, `general`)
- `created_at`

### material_items
- `id` (PK)
- `job_id` (FK → jobs, indexed)
- `name`
- `quantity` (numeric)
- `unit_cost` (numeric, nullable)
- `created_at`

### additional_work_items
- `id` (PK)
- `job_id` (FK → jobs, indexed)
- `description`
- `price` (numeric)
- `status` (enum: `pending`, `approved`, `rejected`, `billed`)
- `created_by_id` (FK → users)
- `created_at`

### payments
- `id` (PK)
- `job_id` (FK → jobs, unique — one-to-one for MVP)
- `amount` (numeric)
- `method` (enum: `cash`, `card`, `bank_transfer`, `other`)
- `status` (enum: `unpaid`, `paid`)
- `paid_at` (timestamp, nullable)

### documents
- `id` (PK)
- `job_id` (FK → jobs, indexed)
- `type` (enum: `job_report`, `repair_certificate`)
- `s3_key`
- `generated_at`

### ai_tasks
- `id` (PK)
- `organization_id` (FK, indexed)
- `job_id` (FK → jobs, indexed, nullable)
- `task_type` (enum: `voice_transcription`, `summary`, `additional_work_suggestion`, `qa_query`)
- `status` (enum: `pending`, `processing`, `done`, `failed`)
- `input_ref` (text — e.g., S3 key of a voice note, or a query string)
- `output` (text/jsonb, nullable)
- `error` (text, nullable)
- `created_at`, `completed_at`

**Address Model:**

No separate `Address` entity in the MVP. Instead, address data lives at exactly two points, each with a clear purpose:

- **`equipment.installation_address`** — the current, canonical address of where that unit is installed. This is what dispatchers see and edit when equipment details change (e.g., customer moves the unit, or a correction is made).
- **`jobs.address_snapshot`** — a copy of the installation address taken at the moment the job is created. This is what technicians and generated documents reference for that specific job, and it stays historically accurate even if `equipment.installation_address` is later edited or the equipment is reassigned to a different location.

`customers` itself carries no address field — a customer's service locations live on their `equipment` records, since a customer can have multiple pieces of equipment at different sites. If a future requirement needs address history independent of equipment (e.g., a customer's billing address, or equipment that moves between multiple recurring sites), that's the trigger to introduce a normalized `addresses` table — not before.

**Status Fields:**

Every status column (`jobs.status`, `additional_work_items.status`, `payments.status`, `payments.method`, `photos.tag`, `documents.type`, `users.role`, `ai_tasks.task_type`, `ai_tasks.status`) is defined as a **Python `Enum`** in the `models/` layer and enforced at the database level via **SQLAlchemy `Enum`** (which Alembic renders as a Postgres native enum type, or a `CHECK` constraint if you prefer plain `VARCHAR` columns — see tradeoff below). This prevents invalid/typo'd values from ever reaching the database, while Pydantic schemas reuse the same enum for request/response validation, so there's a single source of truth for allowed values across the API and the DB.

- **Recommended approach for MVP status evolution speed:** use SQLAlchemy's `Enum` type with `native_enum=False`. This renders as a `VARCHAR` column with a `CHECK` constraint in Postgres, rather than a native Postgres `ENUM` type. Functionally it gives you the same guarantee (invalid values are rejected by the database), but adding a new status later is a simple constraint-altering migration — not the more awkward `ALTER TYPE ... ADD VALUE` dance that native Postgres enums require (which, notably, can't run inside a transaction in older Postgres versions). This keeps status evolution genuinely simple during active MVP development while still preventing inconsistent data.
- **No inventory/stock table** — `material_items` is a flat line-item log, not linked to a stock ledger.

---

## 4. Backend Project Structure

```
app/
├── main.py                    # FastAPI app instantiation, middleware, router registration
├── config.py                  # Settings (pydantic-settings), env vars
├── database.py                # Async engine, session factory, Base
├── dependencies.py            # Shared FastAPI dependencies (get_db, get_current_user, require_role)
│
├── models/                    # SQLAlchemy ORM models — one file per entity group
│   ├── organization.py
│   ├── user.py
│   ├── customer.py
│   ├── equipment.py
│   ├── job.py                 # Job, JobStatusHistory
│   ├── job_items.py           # Photo, MaterialItem, AdditionalWorkItem, Document
│   ├── payment.py
│   └── ai_task.py
│
├── schemas/                   # Pydantic v2 request/response models — mirrors models/
│   ├── organization.py
│   ├── user.py
│   ├── customer.py
│   ├── equipment.py
│   ├── job.py
│   ├── job_items.py
│   ├── payment.py
│   └── ai_task.py
│
├── routers/                   # Thin HTTP layer — parse request, call service, return response
│   ├── auth.py
│   ├── organizations.py
│   ├── users.py
│   ├── customers.py
│   ├── equipment.py
│   ├── jobs.py
│   ├── job_items.py           # photos, materials, additional work, documents endpoints
│   ├── payments.py
│   ├── dashboard.py
│   └── ai.py
│
├── services/                  # Business logic — one file per domain area, mirrors routers/
│   ├── auth_service.py
│   ├── user_service.py
│   ├── customer_service.py
│   ├── equipment_service.py
│   ├── job_service.py          # status transitions, warranty flagging logic
│   ├── job_items_service.py
│   ├── payment_service.py
│   ├── dashboard_service.py
│   └── ai_service.py           # calls out to Anthropic API, creates AITask records
│
├── storage/                   # S3 client wrapper
│   └── s3_client.py
│
├── documents/                 # PDF generation logic
│   └── job_report.py
│
├── workers/                   # Background task functions, invoked via FastAPI BackgroundTasks for now
│   ├── document_tasks.py
│   ├── ai_tasks.py
│   └── warranty_check_task.py  # scheduled job (invoked via startup loop / external cron for MVP)
│   # Note: this package is structured so its functions can be re-registered as arq tasks later
│   # without moving code — only the invocation mechanism (BackgroundTasks vs. arq) changes.
│
├── core/
│   ├── security.py             # JWT encode/decode, password hashing
│   └── exceptions.py           # custom exception classes + handlers
│
└── alembic/                   # migrations
```

**Responsibility summary:**
- **routers/** — HTTP concerns only: path/query params, request validation via schema, call one service method, map result to response schema. No business logic.
- **services/** — all business rules live here (e.g., "a job can only move to `completed` from `in_progress` or `awaiting_approval`"). Services take/return ORM objects or simple data, not Pydantic schemas, keeping them framework-agnostic.
- **models/** — SQLAlchemy declarative models only.
- **schemas/** — Pydantic v2 models for API I/O; never expose ORM models directly.
- **workers/** — anything that shouldn't block the request-response cycle.
- **storage/** and **documents/** — infrastructure adapters, kept separate so they can be swapped later.

This structure is intentionally flat (no `domain/`, `application/`, `infrastructure/` DDD layering) — Router → Service → SQLAlchemy, exactly as specified.

---

## 5. API Design

All routes are prefixed `/api/v1`. All (except `/auth/*`) require a JWT and are scoped to the caller's organization.

### Auth
| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register` | Register a new organization + owner user |
| POST | `/auth/login` | Authenticate, return JWT |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Current user profile |

### Users
| Method | Route | Purpose |
|---|---|---|
| GET | `/users` | List users in organization |
| POST | `/users` | Create a user (owner/dispatcher only) |
| GET | `/users/{id}` | Get user detail |
| PATCH | `/users/{id}` | Update user (role, active status) |
| DELETE | `/users/{id}` | Deactivate user |

### Customers
| Method | Route | Purpose |
|---|---|---|
| GET | `/customers` | List/search customers |
| POST | `/customers` | Create customer |
| GET | `/customers/{id}` | Customer detail (includes equipment + job history) |
| PATCH | `/customers/{id}` | Update customer |
| DELETE | `/customers/{id}` | Soft-delete/archive customer |

### Equipment
| Method | Route | Purpose |
|---|---|---|
| GET | `/customers/{customer_id}/equipment` | List equipment for a customer |
| POST | `/customers/{customer_id}/equipment` | Add equipment |
| GET | `/equipment/{id}` | Equipment detail + repair history |
| PATCH | `/equipment/{id}` | Update equipment |

### Jobs
| Method | Route | Purpose |
|---|---|---|
| GET | `/jobs` | List jobs (filter by status, technician, date range) |
| POST | `/jobs` | Create job |
| GET | `/jobs/{id}` | Job detail (full aggregate: timeline, photos, materials, additional work, payment, documents) |
| PATCH | `/jobs/{id}` | Update job fields (issue, address, schedule) |
| POST | `/jobs/{id}/assign` | Assign technician |
| POST | `/jobs/{id}/status` | Transition status (validates allowed transitions) |
| GET | `/jobs/{id}/timeline` | Full activity timeline |
| DELETE | `/jobs/{id}` | Cancel job |

### Job Sub-resources
| Method | Route | Purpose |
|---|---|---|
| POST | `/jobs/{id}/photos` | Upload photo (returns presigned upload or accepts multipart) |
| GET | `/jobs/{id}/photos` | List photos |
| POST | `/jobs/{id}/materials` | Add material line item |
| GET | `/jobs/{id}/materials` | List materials |
| POST | `/jobs/{id}/additional-work` | Flag additional work |
| PATCH | `/jobs/{id}/additional-work/{item_id}` | Approve/reject/mark billed |
| POST | `/jobs/{id}/documents` | Trigger document generation |
| GET | `/jobs/{id}/documents` | List generated documents |

### Payments
| Method | Route | Purpose |
|---|---|---|
| GET | `/jobs/{id}/payment` | Get payment status |
| PUT | `/jobs/{id}/payment` | Set/update payment (amount, method, status) |

### Dashboard
| Method | Route | Purpose |
|---|---|---|
| GET | `/dashboard/summary` | Active/delayed/completed counts, unbilled additional work count |
| GET | `/dashboard/metrics` | Avg completion time, revenue per technician, AOV, repeat-customer rate, warranty case count |

### AI (optional layer)
| Method | Route | Purpose |
|---|---|---|
| POST | `/ai/voice-note` | Submit a voice note for transcription → structured note (creates AITask) |
| POST | `/ai/jobs/{id}/summary` | Request a customer-friendly repair summary |
| POST | `/ai/jobs/{id}/suggest-additional-work` | Suggest additional work from technician notes |
| POST | `/ai/query` | Natural-language question over job history |
| GET | `/ai/tasks/{id}` | Poll AI task status/result |

---

## 6. Authentication & Authorization

**Authentication:**
- JWT-based, stateless. Access token (short-lived, ~30–60 min) + refresh token (longer-lived, ~7–30 days), following standard practice.
- Password hashing with `bcrypt` (via `passlib`).
- Token payload includes `user_id`, `organization_id`, `role` — avoids an extra DB lookup on every request for tenant scoping.

**Authorization — three roles, kept simple:**

| Role | Permissions |
|---|---|
| **Owner** | Full access: manage users, view all jobs/financials/dashboard, approve additional work, all CRUD |
| **Dispatcher** | Create/edit jobs, customers, equipment; assign technicians; view dashboard; cannot manage users or view org-level settings |
| **Technician** | View only their assigned jobs; update status, add photos/notes/materials/additional-work flags on their own jobs; no access to other technicians' jobs, no dashboard, no financial data beyond their own job's payment status if needed |

**Implementation approach:**
- A single `require_role(*roles)` FastAPI dependency, used per-route (e.g., `require_role("owner", "dispatcher")`).
- Row-level tenant scoping enforced in the service layer: every query filters by `organization_id` from the JWT — never trust a client-supplied org id.
- Technician-level "own jobs only" scoping enforced in `job_service` by checking `assigned_technician_id == current_user.id` for technician role before returning/mutating a job.

No need for a permissions table, policy engine, or RBAC framework — three hardcoded roles cover the MVP completely.

---

## 7. File Storage

**What goes to S3-compatible storage:**
- Job photos (originals; consider generating a thumbnail on upload or on first request — simple resize, not a full pipeline)
- Generated PDF documents (job reports / repair certificates)
- Voice note audio files (if AI voice-to-text feature is included)

**What goes to PostgreSQL (metadata only, never binary blobs):**
- `s3_key` (object path/identifier)
- `content_type`, `file_size` (optional, useful for display)
- `uploaded_by_id`, `created_at`
- Any tag/classification (`before`/`after`, document type)

**Upload flow (recommended, simplest for MVP):**
1. Frontend requests a presigned upload URL from the backend (`POST /jobs/{id}/photos/upload-url`) — backend generates it directly against the S3-compatible bucket.
2. Frontend uploads directly to storage using the presigned URL (keeps large files off the FastAPI process).
3. Frontend confirms upload by calling the actual `POST /jobs/{id}/photos` with the resulting `s3_key`, which the backend persists as metadata.

This avoids routing binary uploads through the API server and keeps the backend stateless and light. A simpler direct-multipart-through-backend approach is acceptable as a fallback if presigned URLs add too much frontend complexity in week 1 — worth revisiting once the basic flow works.

**Bucket structure (convention, not enforced by code):**
```
{organization_id}/jobs/{job_id}/photos/{uuid}.jpg
{organization_id}/jobs/{job_id}/documents/{uuid}.pdf
{organization_id}/jobs/{job_id}/voice-notes/{uuid}.mp3
```

---

## 8. AI Integration

AI is an **optional, isolated layer** — the app is fully functional with every AI feature disabled.

**Where it fits:** a dedicated `ai_service.py` + `/ai/*` routes + `ai_tasks` table. Nothing else in the core domain model depends on AI being present.

**Capabilities (from Product Definition) mapped to inputs/outputs:**

| Feature | Input | Output |
|---|---|---|
| Voice note → structured note | Audio file (S3 key) | Transcribed + structured technician note (text) |
| Repair history summary | Job ID (pulls timeline/notes) | Short natural-language summary |
| Customer-friendly repair summary | Job ID | Plain-language summary suitable for sending to customer |
| Suggest additional work | Technician notes (text) | Suggested additional work items (text, owner reviews/accepts manually — never auto-created) |
| Natural-language Q&A over job history | Free-text query + org_id scope | Answer text, grounded in that org's job data |

**Processing model — always asynchronous:**
1. Client calls an `/ai/*` endpoint → backend creates an `ai_tasks` row with `status=pending`, returns the task ID immediately.
2. A background worker picks up the task, calls the Anthropic API, writes the result back to `ai_tasks` (`status=done`, `output=...`) or marks it `failed` with an error message.
3. Frontend polls `GET /ai/tasks/{id}` (or the job detail endpoint includes latest AI task status) until done.

This keeps AI latency completely off the request/response path and means a slow or failed AI call never blocks core job operations.

**Future extensibility (not built now, but the shape supports it):**
- Swapping/adding models is isolated to `ai_service.py` — no ripple into job/customer logic.
- `ai_tasks.task_type` enum makes it trivial to add new AI capabilities without schema changes.
- A future "AI suggestions accepted" audit trail can hang off `job_status_history` the same way manual actions do.

**Hard rule carried from the Product Definition:** AI never auto-writes to a Job's core state (status, additional work, payment) — it only produces suggestions/drafts a human approves.

---

## 9. Background Jobs

| Task | Trigger | Async? |
|---|---|---|
| Document generation (PDF job report/certificate) | Job marked completed, or manual request | **Yes** — PDF rendering can take a second or two; don't block the request |
| AI processing (transcription, summaries, suggestions, Q&A) | User-initiated via `/ai/*` endpoints | **Yes** — always, per Section 8 |
| Warranty check | Scheduled (daily cron-style task) | **Yes** — scans jobs nearing/past warranty expiry, flags/notifies |
| Notifications (technician assigned, additional work needs approval) | Job assignment, additional work flagged | **Yes** for anything beyond immediate in-app state (email/SMS/push); in-app "unread" flags can be synchronous since they're just a DB write |
| Thumbnail generation for photos (nice-to-have) | Photo uploaded | Yes, if included — low priority, can be deferred |

**Recommended tooling — a two-stage progression, not a single choice:**

- **MVP (now):** **FastAPI `BackgroundTasks`** for everything in the table above — document generation, AI processing, notifications, and the warranty check. Zero extra infrastructure (no Redis, no worker process to deploy/monitor). This is sufficient for an MVP being validated with a handful of pilot companies; the volume doesn't justify a queue yet, and the operational simplicity is worth more than retry guarantees at this stage.
- **After first production users, once reliable retries and scheduling genuinely matter:** migrate to **arq with Redis**. This becomes worth the added infra once you have real users depending on AI processing not silently failing, or once the warranty check needs guaranteed daily execution rather than "runs if the process happens to be up." arq is preferred over Celery here — it's async-native (matches the FastAPI/SQLAlchemy-async stack directly, no sync/async bridging), and far lighter to operate for a single developer than Celery's broker/worker/beat setup.
- **Celery is explicitly out of scope at this stage.** It solves problems (multi-queue routing, complex retry topologies, distributed workers) that don't exist yet for this MVP, and its operational overhead (broker configuration, worker supervision, serialization gotchas) isn't worth paying before there's a concrete need.

**Scheduled task (warranty check):** for the MVP, a daily-run check via `BackgroundTasks` triggered on app startup with a simple sleep-loop, or an external cron hitting an internal endpoint, is enough. Once migrated to arq, its native cron support replaces this cleanly — no schema or logic changes needed, only the execution mechanism changes.

---

## 10. Development Plan

Each phase produces a working, testable increment. No phase should require revisiting a previous phase's schema in a breaking way.

### Phase 1 — Foundation (Week 1)
- Project scaffolding: FastAPI app, config, async DB engine, Alembic setup
- `organizations`, `users` models + migrations
- JWT auth: register, login, refresh, `get_current_user` dependency
- Role-based `require_role` dependency
- Basic health-check and error-handling middleware

**Outcome:** you can register an org, log in, and hit a protected endpoint.

### Phase 2 — Core Records (Week 1–2)
- `customers`, `equipment` models, routers, services
- Search/list endpoints with basic filtering
- CRUD fully working, tested via API client (Postman/HTTPie)

**Outcome:** dispatcher can manage customers and their equipment.

### Phase 3 — Jobs Core (Week 2–3)
- `jobs`, `job_status_history` models
- Job creation, status transition logic (with validated transitions), assignment
- Timeline endpoint

**Outcome:** the central workflow — job intake through status changes — works end to end.

### Phase 4 — Field Capture & Sub-resources (Week 3–4)
- `photos` (+ S3 presigned upload flow), `material_items`, `additional_work_items`
- Additional work approval flow
- `payments` (simple set/get)

**Outcome:** technician can log field work; owner can approve additional work and track payment.

### Phase 5 — Documents & Warranty (Week 4–5)
- PDF generation service (job report/certificate) + background task
- Warranty flagging logic on job completion + linking to origin job
- Scheduled warranty-check background task

**Outcome:** completed jobs generate real documents; warranty claims are detected automatically.

### Phase 6 — Dashboard & Metrics (Week 5)
- Aggregation queries for dashboard summary and metrics endpoints
- Likely the first place raw SQL/window functions are worth writing directly rather than through the ORM for performance

**Outcome:** owner has the operational visibility that's the whole point of the product.

### Phase 7 — AI Layer (Week 5–6, if time allows)
- `ai_tasks` model, background worker integration with Anthropic API
- Voice note transcription, job summary, additional work suggestion, Q&A endpoints
- Explicitly the first thing to cut or trim if the schedule slips — the product must work without it

**Outcome:** optional AI assist layered on top of a fully functional core.

### Phase 8 — Hardening (buffer, end of Week 6)
- Input validation edge cases, error responses, basic rate limiting on auth endpoints
- Seed/demo data script
- Smoke-test all workflows from the Product Definition end to end

**Note on frontend:** this plan assumes backend-first development with the frontend catching up module by module (auth → customers/equipment → jobs → field capture → dashboard), which matches the "Next.js in early stages" status already in progress.

---

## Guiding Principle (carried from Product Definition)

Every architectural choice here optimizes for **one developer shipping working software in six weeks** — not for handling a hypothetical 10,000-tenant future. Multi-tenancy is row-level because that's simplest; background jobs start as `BackgroundTasks` because that's simplest; AI is fully isolated because it's the most likely thing to change or get cut. Nothing here should need to be torn out to grow later — it just needs more of the same boring patterns applied further.
