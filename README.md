# Service Center Platform

A lightweight operational platform for small field-service and repair
companies.

Service Center Platform keeps the full repair lifecycle in one place ---
from the first customer request through technician work, payment,
documentation, and warranty follow-up.

> **Core concept:** Customer → Repair Job → Technician → Work → Payment
> → Documents → Warranty

## The Problem

Small repair businesses often run operations across chat threads,
spreadsheets, paper notes, and individual employees' memory. That makes
even basic operational questions difficult to answer reliably.

Typical problems include:

-   customer and equipment history scattered across different places;
-   unclear job status and jobs slipping through the cracks;
-   technician assignments without a shared operational view;
-   additional work discovered on-site not being consistently tracked or
    billed;
-   materials and payment information separated from the job itself;
-   repair documents being created manually or not retained with the
    service history;
-   warranty follow-ups depending on memory instead of a structured
    record.

## The Solution

Service Center Platform treats the **Repair Job** as the central
operational record.

Instead of splitting information across separate tools, each job
connects the customer, equipment, assigned technician, status history,
field activity, photos, materials, additional work, payment, generated
documents, and warranty context.

The goal is not to replace a full ERP or accounting system. It is to
provide a focused operational workspace for the workflow a service
company manages every day.

## Core Workflow

``` text
Request
   ↓
Job
   ↓
Assignment
   ↓
Diagnosis / Work
   ↓
Additional Work
   ↓
Payment
   ↓
Documents
   ↓
Warranty
```

The job timeline preserves the operational history as the repair moves
through this lifecycle.

## Key Capabilities

-   **Customer management** --- customer records connected to equipment
    and repair history.
-   **Equipment** --- equipment records linked to customers and previous
    jobs.
-   **Repair jobs** --- the central entity for service operations.
-   **Technician assignment** --- assign work and scheduled time to
    technicians.
-   **Status transitions** --- move jobs through their operational
    lifecycle.
-   **Job timeline** --- retain a chronological activity history for
    each job.
-   **Photos** --- attach field photos to repair jobs.
-   **Materials** --- record materials and parts used without
    introducing full inventory management.
-   **Additional work** --- track work discovered during a repair,
    including approval/billing state.
-   **Payments** --- lightweight payment records linked directly to
    jobs.
-   **PDF documents** --- generate job-related PDF documents and store
    them with the repair record.
-   **Warranty logic** --- identify follow-up jobs for the same
    equipment that may fall within the original warranty period.
-   **Owner dashboard** --- operational visibility across active jobs,
    delayed work, payments, and other job-level signals.
-   **Optional AI assistance** --- an assistive layer in the existing
    MVP; it is not the core workflow and does not replace operational
    decisions.

## Demo Scenario

The repository includes seed data designed to demonstrate the product
across different real-world job states.

The demo covers:

-   a newly created job;
-   an active job already moving through the workflow;
-   a job with pending additional work;
-   a completed and paid job with a generated PDF document;
-   a follow-up job that is identified as a potential warranty case;
-   a cancelled job.

The seed data is intended to make the lifecycle easy to inspect locally.
It does not represent real customers, revenue, or production usage.

Run it with:

``` bash
python -m app.seed_demo_data
```

A running, migrated PostgreSQL database is required. MinIO must also be
running for the generated document used in the demo.

> The seed command is not idempotent. Each run creates a new demo
> organization.

## Architecture

The application deliberately uses a straightforward full-stack
architecture:

``` text
Next.js
   ↓
FastAPI
   ↓
Service Layer
   ↓
PostgreSQL

Documents / Photos
   ↓
S3-compatible storage
```

Backend business logic follows:

``` text
Router → Service → SQLAlchemy
```

FastAPI routers handle the HTTP layer, services contain business logic,
and SQLAlchemy provides persistence. Binary files such as photos and
generated PDFs are stored in S3-compatible object storage while their
application metadata remains in PostgreSQL.

Background document generation uses FastAPI `BackgroundTasks`. The MVP
intentionally avoids Redis and a separate worker process because the
current workload does not require the additional operational complexity
or retry guarantees of a dedicated queue.

For more detail, see [docs/architecture.md](docs/architecture.md).

For the product reasoning behind the MVP, see
[docs/product-case-study.md](docs/product-case-study.md).

## Tech Stack

### Frontend

-   Next.js 16
-   React 19
-   TypeScript
-   Tailwind CSS 4
-   shadcn / Base UI

### Backend

-   Python 3.13
-   FastAPI
-   PostgreSQL 16
-   SQLAlchemy Async
-   Alembic
-   Pydantic v2
-   asyncpg
-   Pytest

### Storage & Local Infrastructure

-   S3-compatible object storage
-   MinIO for local development
-   Docker Compose

## Repository Structure

``` text
service-center-platform/
├── app/                       # FastAPI backend
│   ├── core/
│   ├── documents/
│   ├── models/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── storage/
│   ├── workers/
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   └── seed_demo_data.py
├── alembic/                   # Database migrations
├── docs/                      # Product and technical documentation
├── frontend/                  # Next.js frontend
├── tests/                     # Backend tests
├── .env.example
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Local Setup

### Prerequisites

Recommended setup:

-   Docker Desktop
-   Node.js and npm

Running the backend without Docker additionally requires:

-   Python 3.13
-   PostgreSQL

### 1. Clone the repository

``` bash
git clone https://github.com/avgrosheva/service-center-platform.git
cd service-center-platform
```

### 2. Start the backend with Docker Compose

Copy the backend environment template.

macOS / Linux:

``` bash
cp .env.example .env
```

Windows PowerShell:

``` powershell
Copy-Item .env.example .env
```

Start the backend, PostgreSQL, and MinIO:

``` bash
docker compose up --build
```

Local services:

  Service         Address
  --------------- -------------------------
  FastAPI         `http://localhost:8000`
  PostgreSQL      `localhost:5433`
  MinIO API       `http://localhost:9000`
  MinIO Console   `http://localhost:9001`

Check backend health:

``` bash
curl http://localhost:8000/health
```

Expected response:

``` json
{
  "status": "ok",
  "database": "connected"
}
```

PostgreSQL data is persisted in the `fsp_postgres_data` volume and MinIO
data in `fsp_minio_data`.

Stop the stack:

``` bash
docker compose down
```

Reset persisted local data:

``` bash
docker compose down -v
```

### 3. Start the frontend

Open another terminal:

``` bash
cd frontend
npm install
```

Create the frontend environment file.

macOS / Linux:

``` bash
cp .env.local.example .env.local
```

Windows PowerShell:

``` powershell
Copy-Item .env.local.example .env.local
```

For local development, point the frontend to the backend:

``` env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start Next.js:

``` bash
npm run dev
```

Open:

``` text
http://localhost:3000
```

### Run the backend without Docker

For a native Windows / PowerShell setup:

``` powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
```

Update `DATABASE_URL` in `.env` to point to your local PostgreSQL
instance. For example:

``` env
DATABASE_URL=postgresql+asyncpg://fsp:dev_password_change_me@localhost:5432/field_service
```

Create the `field_service` database and `fsp` user, then run:

``` powershell
uvicorn app.main:app --reload
```

Check:

``` powershell
Invoke-RestMethod http://localhost:8000/health
```

## Database Migrations

Apply migrations with Alembic:

``` bash
alembic upgrade head
```

## Tests

Run backend tests with:

``` bash
pytest
```

Frontend quality checks are available from `frontend/`:

``` bash
npm run lint
npm run typecheck
npm run format:check
npm run build
```

## Project Scope

Service Center Platform is intentionally an MVP-sized operational
product.

It focuses on the repair-job lifecycle rather than becoming a
general-purpose ERP. Full accounting, warehouse inventory, payroll,
native mobile apps, customer self-service, complex integrations, and
other larger platform capabilities are outside the current MVP scope.

See [docs/product-case-study.md](docs/product-case-study.md) for the
product decisions and scope boundaries.
