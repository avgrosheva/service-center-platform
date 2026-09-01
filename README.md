# Service Center Platform

A lightweight operational platform for small field-service and repair businesses.

Service Center Platform brings the repair lifecycle into one shared workspace: customer and equipment context, repair jobs, technician assignments, field work, additional work, payments, documents, and warranty follow-up.

**Core workflow**

```text
Customer → Repair Job → Technician → Work → Additional Work → Payment → Documents → Warranty
```

## Who It Is For

The product is designed for small service and repair teams where owners, dispatchers, and technicians need a shared operational view without the complexity of a full ERP.

Typical use cases include field-service businesses that manage customer equipment, schedule technicians, perform repairs on-site, record materials and additional work, collect payment, and retain service history for future warranty cases.

## The Problem

Small repair businesses often coordinate work across chats, spreadsheets, paper notes, and individual employees' memory. That creates operational gaps:

- customer and equipment history is scattered;
- job ownership and current status are unclear;
- technician assignments are difficult to track centrally;
- additional work discovered during a repair can be lost between the field and the office;
- materials and payments are disconnected from the job;
- documents are handled separately from service history;
- warranty follow-up depends on remembering previous repairs.

## The Solution

Service Center Platform uses the **Repair Job** as the central operational record.

A job connects the customer and equipment to the technician, current status, activity timeline, photos, materials, additional work, payment, generated documents, and warranty context. Instead of managing each part of a repair in a separate tool, the team can follow the lifecycle from intake to closure in one system.

## Product Workflow

```text
Customer
   ↓
Repair Job
   ↓
Technician Assignment
   ↓
Diagnosis / Work
   ↓
Additional Work
   ↓
Payment
   ↓
Documents
   ↓
Warranty / Follow-up
```

The job timeline keeps the operational history visible as the repair moves through this lifecycle.

## Key Capabilities

- **Customers** — customer records connected to equipment and repair history.
- **Equipment** — equipment records tied to customers and previous service jobs.
- **Repair jobs & statuses** — create and manage jobs through the repair lifecycle.
- **Technician assignment** — assign technicians and scheduled work.
- **Timeline** — retain chronological job activity and status history.
- **Photos** — attach repair photos to the job.
- **Materials** — record materials used during service.
- **Additional work** — capture work discovered during a repair and its decision state.
- **Payments** — keep lightweight payment information with the job.
- **Documents** — generate PDF documents and store them with the repair record.
- **Warranty** — connect follow-up work to previous equipment repairs and warranty context.
- **Dashboard** — owner-level operational visibility across service activity.
- **Optional AI assistance** — the backend includes an optional AI-assist layer; it supports the workflow rather than replacing operational decisions.

## Demo / Seed Data

The repository includes demo data that exercises different real-world job states through the application's service layer.

```bash
python -m app.seed_demo_data
```

The seed scenario includes new and active work, pending additional work, a completed and paid job with a generated PDF, a same-equipment warranty follow-up, and a cancelled job.

It requires a running, migrated PostgreSQL database and MinIO for the generated document.

> The seed script is not idempotent: each run creates a new demo organization. The data is illustrative only and does not represent real customers, revenue, or production usage.

## Architecture

```text
Next.js Frontend
       ↓
    FastAPI
       ↓
 Service Layer
       ↓
  PostgreSQL

Photos / Documents → S3-compatible storage
```

The backend follows a layered structure:

```text
Router → Service → SQLAlchemy
```

FastAPI routers handle HTTP concerns, services contain business logic, and SQLAlchemy provides asynchronous persistence to PostgreSQL. Photos and generated PDFs use S3-compatible object storage; MinIO provides that storage locally.

PDF generation uses FastAPI `BackgroundTasks`. The MVP deliberately avoids Redis and a separate worker process because the current background workload does not require durable queues or distributed retry guarantees.

See [docs/architecture.md](docs/architecture.md) for the concise technical overview and [docs/product-case-study.md](docs/product-case-study.md) for the product reasoning behind the MVP.

## Tech Stack

**Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn / Base UI

**Backend:** Python 3.13, FastAPI, PostgreSQL 16, SQLAlchemy Async, Alembic, Pydantic v2, asyncpg

**Infrastructure:** Docker Compose, S3-compatible object storage, MinIO for local development

**Testing / quality:** Pytest, ESLint, TypeScript type checking, Prettier

## Repository Structure

```text
service-center-platform/
├── app/                       # FastAPI backend
│   ├── core/                  # Security, exceptions, rate limiting
│   ├── documents/             # PDF generation
│   ├── models/                # SQLAlchemy models
│   ├── routers/               # HTTP/API layer
│   ├── schemas/               # Pydantic schemas
│   ├── services/              # Business logic
│   ├── storage/               # S3-compatible storage integration
│   ├── workers/               # Background task functions
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   └── seed_demo_data.py
├── frontend/                  # Next.js frontend
│   ├── app/                   # App Router pages and API routes
│   ├── components/            # Feature and UI components
│   ├── lib/                   # API/auth/session helpers
│   ├── public/
│   ├── types/
│   ├── .env.local.example
│   └── package.json
├── alembic/                   # Database migrations
├── tests/                     # Backend test suite
├── docs/                      # Product and architecture documentation
├── .env.example               # Backend environment template
├── Dockerfile                 # Backend image
├── docker-compose.yml         # Backend + PostgreSQL + MinIO
├── alembic.ini
├── pytest.ini
└── requirements.txt
```

## Local Setup

### Prerequisites

Recommended setup:

- Docker Desktop
- Node.js and npm

Running the backend natively instead of through Docker additionally requires Python 3.13 and PostgreSQL.

### 1. Clone the repository

```bash
git clone https://github.com/avgrosheva/service-center-platform.git
cd service-center-platform
```

### 2. Start the backend infrastructure

Copy the backend environment template:

**macOS / Linux**

```bash
cp .env.example .env
```

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

Start FastAPI, PostgreSQL, and MinIO:

```bash
docker compose up --build
```

Local services:

| Service | Address |
| --- | --- |
| FastAPI | `http://localhost:8000` |
| PostgreSQL | `localhost:5433` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |

Check backend health:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok","database":"connected"}
```

To stop the stack:

```bash
docker compose down
```

To also reset persisted PostgreSQL and MinIO data:

```bash
docker compose down -v
```

### 3. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
```

Create the frontend environment file:

**macOS / Linux**

```bash
cp .env.local.example .env.local
```

**Windows PowerShell**

```powershell
Copy-Item .env.local.example .env.local
```

The example configuration points the frontend at the local FastAPI server:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start Next.js:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend API client prefixes requests with `/api/v1` on top of `NEXT_PUBLIC_API_BASE_URL`.

### Backend without Docker

On Windows / PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
```

Set `DATABASE_URL` in `.env` to a local PostgreSQL instance, for example:

```env
DATABASE_URL=postgresql+asyncpg://fsp:dev_password_change_me@localhost:5432/field_service
```

Create the `field_service` database and `fsp` user, then run:

```powershell
uvicorn app.main:app --reload
```

Check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### Database migrations

```bash
alembic upgrade head
```

### Tests and frontend checks

Backend:

```bash
pytest
```

Frontend, from `frontend/`:

```bash
npm run lint
npm run typecheck
npm run format:check
npm run build
```

## MVP Scope

The MVP focuses on the operational repair lifecycle: authentication and organization/users, customers, equipment, repair jobs, assignments, status transitions and timeline, photos, materials, additional work, payments, documents, warranty logic, owner dashboard, and the existing optional AI-assist layer.

The web frontend covers the main authenticated workflows, including dashboard, customers, equipment, jobs, schedule, and settings.

## Out of Scope

The project deliberately does not try to become a full ERP. Current scope does not include full accounting, warehouse inventory management, payroll, native mobile apps, customer self-service/self-booking, or complex enterprise integrations.

These boundaries keep the product focused on the operational question at the center of a service business: **what is happening with each repair job, who owns it, and what needs to happen next?**
