# Service Center Platform --- Architecture

## Overview

Service Center Platform uses a deliberately simple full-stack
architecture appropriate for the current MVP.

The system consists of:

-   a Next.js frontend;
-   a FastAPI backend;
-   a service layer containing business logic;
-   PostgreSQL for application data;
-   S3-compatible object storage for binary files such as photos and
    generated PDFs.

``` mermaid
flowchart TD
    FE[Next.js Frontend] -->|REST / JSON| API[FastAPI API]
    API --> SL[Service Layer]
    SL --> DB[(PostgreSQL)]

    API --> DOC[Document / Photo handling]
    DOC --> S3[(S3-compatible storage)]
```

The architecture is intentionally monolithic. The MVP does not introduce
microservices, Redis, or a separate worker service.

## Backend Layers

The backend follows:

``` text
Router → Service → SQLAlchemy
```

### Router

FastAPI routers are the HTTP boundary.

They handle request/response concerns and delegate application behavior
to services rather than containing the main business logic themselves.

### Service

The service layer contains the product's business logic, including
repair-job operations and related domain workflows.

This keeps domain behavior separate from the HTTP layer and allows the
same logic to be reused by flows such as demo-data seeding.

### SQLAlchemy

SQLAlchemy Async is used for persistence against PostgreSQL.

Application entities are represented through ORM models, while Alembic
manages database migrations.

## Authentication

Authentication is handled by the FastAPI backend.

The application includes organization/user management and authenticated
application routes. The frontend uses the backend API for authentication
and protects the operational application area accordingly.

The MVP also applies in-memory rate limiting to the login endpoint. This
is suitable for the current single-process shape but is not intended to
behave as a distributed rate limiter across multiple backend workers.

## Database

PostgreSQL is the primary system of record.

It stores the structured application data for organizations, users,
customers, equipment, repair jobs, job history/timeline, materials,
additional work, payments, document metadata, photos, and
warranty-related relationships.

The backend uses asynchronous SQLAlchemy access through `asyncpg`.

Local Docker development uses PostgreSQL 16.

## Object Storage

Binary objects are stored separately from PostgreSQL.

The application uses an S3-compatible storage abstraction for files such
as:

-   job photos;
-   generated PDF documents.

For local development, Docker Compose runs MinIO. The backend
communicates with object storage through the same S3-compatible
interface, allowing the storage implementation to be changed through
configuration without moving binary data into the relational database.

PostgreSQL retains the application metadata and relationships for those
objects.

## Background Document Generation

PDF generation is handled with FastAPI `BackgroundTasks`.

When document generation is requested, the background task:

1.  opens its own database session;
2.  generates the PDF;
3.  uploads the file to S3-compatible storage;
4.  persists the document record and related timeline information.

This prevents PDF generation and upload work from unnecessarily blocking
the request lifecycle.

## Why There Is No Redis or Separate Worker

The MVP deliberately does not use Redis, Celery, arq, or a separate
worker process.

For the current scope, FastAPI `BackgroundTasks` provides enough
separation for non-blocking document generation without adding another
infrastructure component.

That choice keeps local development and deployment simpler:

``` text
Frontend
Backend
PostgreSQL
Object Storage
```

A queue-backed worker would become justified when background work
requires stronger guarantees such as:

-   automatic retries;
-   durable job state;
-   guaranteed scheduled execution;
-   multiple application processes coordinating background work.

Those guarantees are not required by the current MVP, so the extra
operational complexity is intentionally excluded.

## Local Infrastructure

Docker Compose provides the backend infrastructure used in local
development:

``` text
FastAPI        http://localhost:8000
PostgreSQL     localhost:5433
MinIO API      http://localhost:9000
MinIO Console  http://localhost:9001
```

The frontend runs separately through Next.js at:

``` text
http://localhost:3000
```

## Design Principle

The architecture follows the same principle as the product scope: keep
the system as small as possible while preserving clear domain
boundaries.

The current structure is sufficient for the implemented repair-service
MVP and avoids introducing distributed-system complexity before the
product requires it.
