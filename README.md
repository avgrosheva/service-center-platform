# Field Service Platform

Full-stack MVP for managing field-service and repair operations: customers, equipment, repair jobs, technician assignments, job lifecycle, materials, additional work, payments, documents, warranty cases, scheduling, and operational dashboards.

The repository contains both the **FastAPI backend** and the **Next.js web application**.

## Features

### Operations

- Customer management
- Equipment registry and equipment history
- Repair/service job creation and tracking
- Technician assignment
- Job status lifecycle and timeline
- Schedule view for field work
- Materials and additional-work tracking
- Payment tracking
- PDF document generation
- Warranty/follow-up job logic
- Owner/operations dashboard
- Organization and user management
- Optional AI-assist layer

### Web Application

- Authentication and registration flows
- Protected application area
- Dashboard
- Jobs list, job creation, and job details
- Customers list, customer creation, and customer details
- Equipment details
- Schedule
- Settings
- Responsive component-based UI
- Typed API integration with the backend

---

## Tech Stack

### Backend

- Python 3.13
- FastAPI
- PostgreSQL 16
- SQLAlchemy Async
- Alembic
- Pydantic v2 / pydantic-settings
- asyncpg
- S3-compatible object storage via MinIO for local development
- FastAPI `BackgroundTasks`
- Pytest

Backend architecture follows a layered approach:

```text
Router -> Service -> SQLAlchemy
```

### Frontend

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4
- shadcn
- Base UI
- Lucide React
- ESLint
- Prettier

---

## Repository Structure

```text
service-center-platform/
├── app/                       # Backend application
│   ├── main.py                # FastAPI application
│   ├── config.py              # Environment/settings configuration
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic request/response schemas
│   ├── routers/               # HTTP/API layer
│   ├── services/              # Business logic
│   ├── storage/               # S3-compatible storage integration
│   ├── documents/             # PDF generation
│   ├── workers/               # Background tasks
│   └── core/                  # Security, exceptions, rate limiting, etc.
├── alembic/                   # Database migrations
├── docs/                      # Project/backend documentation
├── tests/                     # Backend tests
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   │   ├── (authenticated)/   # Protected application routes
│   │   │   ├── customers/
│   │   │   ├── dashboard/
│   │   │   ├── equipment/
│   │   │   ├── jobs/
│   │   │   ├── schedule/
│   │   │   └── settings/
│   │   ├── api/
│   │   ├── login/
│   │   └── register/
│   ├── components/            # UI and feature components
│   │   ├── auth/
│   │   ├── customers/
│   │   ├── equipment/
│   │   ├── jobs/
│   │   ├── shell/
│   │   └── ui/
│   ├── lib/                   # API client, auth/session helpers, utilities
│   ├── types/                 # Frontend TypeScript types
│   └── public/                # Static assets
├── .env.example               # Backend environment template
├── docker-compose.yml         # Backend + PostgreSQL + MinIO
├── Dockerfile                 # Backend container
├── requirements.txt           # Python dependencies
└── README.md
```

---

## Getting Started

### Prerequisites

For the recommended setup:

- Docker Desktop
- Node.js and npm

For running the backend without Docker:

- Python 3.13
- PostgreSQL

---

## 1. Clone the Repository

```bash
git clone https://github.com/avgrosheva/service-center-platform.git
cd service-center-platform
```

---

## 2. Start the Backend

Docker Compose is the recommended way to run the backend and its infrastructure.

Copy the backend environment template.

### macOS / Linux

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

Then start the stack:

```bash
docker compose up --build
```

This starts:

| Service | Address | Purpose |
|---|---|---|
| FastAPI | `http://localhost:8000` | Backend API |
| PostgreSQL | `localhost:5433` | Application database |
| MinIO API | `http://localhost:9000` | S3-compatible object storage |
| MinIO Console | `http://localhost:9001` | Local storage administration |

Check backend health:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "database": "connected"
}
```

PostgreSQL data is persisted in the `fsp_postgres_data` Docker volume and MinIO data in `fsp_minio_data`.

To stop the stack:

```bash
docker compose down
```

To stop it and delete persisted local data:

```bash
docker compose down -v
```

---

## 3. Start the Frontend

Open another terminal:

```bash
cd frontend
npm install
```

Create the frontend environment file.

### macOS / Linux

```bash
cp .env.local.example .env.local
```

### Windows PowerShell

```powershell
Copy-Item .env.local.example .env.local
```

The default development configuration points the frontend to the local backend:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Start the development server:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend API client uses `NEXT_PUBLIC_API_BASE_URL` as the backend base URL and calls the backend under `/api/v1`.

---

## Quick Start

Once the repository has been cloned, the normal local-development workflow is:

### Terminal 1 — Backend

```bash
cp .env.example .env
docker compose up --build
```

### Terminal 2 — Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Then open:

```text
http://localhost:3000
```

> On Windows PowerShell, use `Copy-Item` instead of `cp` if needed.

---

## Backend: Local Run Without Docker

If you want to run FastAPI directly on your machine, you need Python 3.13 and a local PostgreSQL instance.

### Windows / PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
```

Update `DATABASE_URL` in `.env` to point to your local PostgreSQL instance.

For example:

```env
DATABASE_URL=postgresql+asyncpg://fsp:dev_password_change_me@localhost:5432/field_service
```

Create the `field_service` database and `fsp` user in PostgreSQL, then start the API:

```powershell
uvicorn app.main:app --reload
```

Check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

---

## Database Migrations

The project uses Alembic for database migrations.

Apply migrations with:

```bash
alembic upgrade head
```

When the backend is running in Docker, run Alembic in the appropriate backend environment/container if migrations are not already applied by your development workflow.

---

## Demo Data

With PostgreSQL migrated and MinIO running:

```bash
python -m app.seed_demo_data
```

The seed script creates a demonstration organization with:

- an owner
- a dispatcher
- two technicians
- three customers with equipment
- five jobs covering different lifecycle states

The sample jobs include new and in-progress work, pending additional work, a completed paid job with a generated PDF document, a warranty follow-up, and a cancelled job.

The script prints demo login credentials and dashboard values when it finishes.

> The seed command is not idempotent. Running it multiple times creates additional demo organizations.

---

## Authentication and Access

The application includes authentication plus organization/user management.

The frontend contains public login and registration routes and keeps operational pages under the authenticated application layout.

The backend's login endpoint is rate-limited to **5 attempts per 60 seconds per client IP** for the MVP.

API error responses use a consistent shape:

```json
{
  "detail": "Error message"
}
```

---

## Main Frontend Routes

```text
/login
/register
/dashboard
/jobs
/jobs/new
/jobs/[id]
/customers
/customers/new
/customers/[id]
/equipment/[id]
/schedule
/settings
```

---

## Frontend Development Commands

Run these from `frontend/`.

### Development Server

```bash
npm run dev
```

Starts the Next.js development server.

### Production Build

```bash
npm run build
```

Creates a production build.

### Production Server

```bash
npm run start
```

Starts the production Next.js server after a build.

### Linting

```bash
npm run lint
```

Runs ESLint.

### Type Checking

```bash
npm run typecheck
```

Runs the TypeScript compiler without emitting files.

### Formatting

```bash
npm run format
```

Formats frontend files with Prettier.

### Formatting Check

```bash
npm run format:check
```

Checks formatting without modifying files.

---

## Backend Tests

Run:

```bash
pytest
```

The fast unit tests mock database connectivity where appropriate.

Real PostgreSQL connectivity can be checked separately through the Docker Compose stack and `/health` endpoint.

---

## Background Tasks

The MVP currently uses FastAPI `BackgroundTasks` rather than a separate Redis-backed worker system.

Current background-task functionality includes:

- PDF document generation and S3 upload
- warranty-check task logic

Document generation opens its own database session, generates the PDF, uploads it to S3-compatible storage, and persists the resulting document/timeline data.

For a larger production deployment, a dedicated queue such as Redis + arq can replace the current approach when reliable retries or guaranteed scheduled execution become necessary.

---

## Object Storage

Local development uses MinIO as an S3-compatible object store.

The backend accesses object storage through an S3 client abstraction, allowing the local MinIO setup to be replaced by another S3-compatible provider in deployment through configuration.

Docker Compose exposes:

```text
MinIO API:     http://localhost:9000
MinIO Console: http://localhost:9001
```

---

## Environment Configuration

Backend configuration starts from:

```text
.env.example
```

Frontend configuration starts from:

```text
frontend/.env.local.example
```

For frontend development, the main variable is:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Do not commit real secrets or local `.env` files.

---

## Architecture

At a high level:

```text
Browser
   |
   v
Next.js / React frontend
   |
   | HTTP / JSON
   v
FastAPI routers
   |
   v
Service layer
   |
   +--------------------+
   |                    |
   v                    v
PostgreSQL          S3-compatible storage
(SQLAlchemy)            (MinIO locally)
```

The backend keeps HTTP concerns in routers and business logic in services. Persistence is handled through asynchronous SQLAlchemy models and sessions.

The frontend is organized around Next.js App Router routes, reusable feature components, shared UI components, typed API access, and authentication/session helpers.

---

## Core Domain Flow

A typical service operation can move through the platform roughly as follows:

```text
Customer
   |
   v
Equipment
   |
   v
Service / Repair Job
   |
   +--> Technician assignment
   +--> Status transitions
   +--> Timeline
   +--> Photos / materials
   +--> Additional work
   +--> Payment
   +--> PDF documents
   +--> Warranty / follow-up
```

The dashboard and schedule provide operational views over these domain records.

---

## Production Notes

The current repository is an MVP-oriented implementation.

Before a production deployment, review at least:

- production secrets and environment management
- CORS/origin configuration
- HTTPS and reverse proxy configuration
- database backups
- production object storage
- persistent application logging and monitoring
- multi-process implications for in-memory rate limiting
- reliable background-job processing if retries become required
- frontend and backend deployment configuration

---

## Project Status

The backend implements the MVP scope described by the project's implementation roadmap, including:

- authentication
- organization and user management
- customers
- equipment
- repair jobs
- assignments
- lifecycle and timeline
- materials
- additional work
- payments
- documents
- warranty logic
- dashboard functionality
- optional AI assistance
- backend hardening

The repository also contains the working **Next.js frontend** for the main user workflows.

The project should therefore be treated as a **full-stack application** rather than a backend-only service.

---

## License

No license file is currently documented in this repository.

Add a `LICENSE` file and update this section if the project is going to be distributed publicly under a specific license.
