# Service Center Platform — Product Case Study

## Problem

Small field-service and repair businesses can run a large part of their operation through chats, spreadsheets, paper notes, and individual employees' memory.

The resulting problem is not only fragmented data. It is the absence of a single operational record that answers what is happening with a repair from customer request through completion, payment, documentation, and possible warranty follow-up.

## Target Customer

Service Center Platform is designed for small field-service and repair companies with lean operational teams.

The product fits businesses where an owner or dispatcher coordinates work and technicians perform repairs in the field. These teams need more structure than messaging and spreadsheets provide, but do not necessarily need the scope and complexity of a full ERP.

The implemented product supports organization users and technician assignment, while the frontend provides authenticated operational views for the main workflows.

## Operational Problems

### Fragmented customer and equipment history

A repeat customer or previously serviced unit may already have useful repair history, but that context is difficult to use when it is scattered across tools.

### Unclear job status and ownership

Without a shared job record, it is difficult to see which work is new, assigned, in progress, waiting, completed, or cancelled — and which technician owns it.

### Field activity is easy to lose

Photos, notes, materials, and status updates produced during a repair need to remain connected to the job instead of disappearing into chats or personal notes.

### Additional work can fall through the gap

Extra work discovered during diagnosis is operationally and commercially important. If it exists only as a conversation, it can be forgotten, performed without clear approval, or fail to make it into the final job value.

### Payment is separated from completion

A repair can be technically complete while payment is still outstanding. The operational team needs that distinction even if the system is not an accounting product.

### Documents are disconnected from service history

Repair documents are more useful when they remain attached to the same record as the customer, equipment, work, technician, and payment context.

### Warranty follow-up depends on previous repair context

When the same equipment returns, the team needs a reliable connection to earlier work and its warranty window.

## Product Solution

Service Center Platform puts the repair lifecycle into one shared system.

```text
Customer
   ↓
Equipment
   ↓
Repair Job
   ├── Technician assignment
   ├── Status & timeline
   ├── Photos
   ├── Materials
   ├── Additional work
   ├── Payment
   ├── Documents
   └── Warranty context
```

The platform is deliberately operational rather than ERP-like: it keeps the information required to execute and close repair work together without expanding into every adjacent business process.

## Why Repair Job Is the Central Entity

The **Repair Job** is the product's central operational object.

Customer and equipment records provide identity and history, but the job is where daily execution happens. It connects:

- the customer;
- the equipment;
- the reported service need;
- the assigned technician;
- scheduling information;
- current status and status history;
- timeline activity;
- photos and field context;
- materials used;
- additional work;
- payment information;
- generated documents;
- warranty relationships.

This means one object can answer both:

> What needs to happen next?

and:

> What happened during this repair?

That job-centric model keeps the product focused on operational execution instead of becoming a broad CRM.

## Main Workflow

```text
Customer
   ↓
Repair Job
   ↓
Technician
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

In practice, the job retains the status and timeline context needed to represent non-linear real-world states such as pending additional work, cancellation, and warranty follow-up.

## Product Decisions Reflected in the Implementation

### 1. Use Repair Job as the operational source of context

The product is job-centric rather than customer-record-centric. Customer and equipment data exists to support the lifecycle of the work, while job pages and job state carry the operational process.

### 2. Keep both current status and history

A status tells the team where a job is now; the timeline provides the history behind that state. The implementation preserves job activity rather than treating the current status as the only useful information.

### 3. Treat additional work as structured workflow data

Additional work is modeled separately from free-form notes. That reflects a real operational handoff: diagnosis can reveal work that must be surfaced, decided on, and retained as part of the job.

### 4. Record materials without building warehouse management

Materials used during service belong to the repair record, so the MVP tracks them at job level. It intentionally does not expand this into stock levels, purchasing, warehouses, or inventory reconciliation.

### 5. Keep payments operational and lightweight

Payment information is attached to the repair lifecycle so completed-but-unpaid work remains visible. The product does not attempt to replace accounting or payment-processing software.

### 6. Keep documents and photos outside the relational database

Binary files use S3-compatible object storage while structured application data remains in PostgreSQL. This keeps job relationships in the database without storing file payloads there.

### 7. Choose simple background execution for the MVP

PDF generation uses FastAPI `BackgroundTasks` rather than Redis and a dedicated worker queue. The current product does not require the infrastructure and retry guarantees of a distributed job system, so the implementation stays deliberately simple.

## MVP Scope

Implemented scope includes:

- authentication and organization/user management;
- customers;
- equipment and repair history;
- repair jobs and status transitions;
- technician assignment and scheduling;
- job timeline;
- photos;
- materials;
- additional work;
- payments;
- PDF documents;
- warranty/follow-up logic;
- owner dashboard;
- optional AI assistance already present in the backend;
- Next.js frontend for the main operational workflows.

The repository's seed data demonstrates the lifecycle using the actual service layer.

## Out of Scope

The MVP intentionally does not include:

- full accounting/bookkeeping;
- warehouse and inventory management;
- payroll;
- native mobile applications;
- customer self-service or self-booking;
- marketplace functionality;
- ERP-level reporting;
- complex external CRM/accounting/payment integrations;
- distributed background-job infrastructure.

These are scope boundaries rather than claims about future roadmap.

## Current Limitations

The implementation is an MVP and has deliberate constraints:

- payments provide operational visibility rather than accounting-grade functionality;
- materials are recorded per job without stock management;
- background PDF generation uses in-process `BackgroundTasks`, so it does not provide queue-backed retries;
- the warranty check exists as backend logic but is not backed by a guaranteed external scheduler;
- login rate limiting is in-memory and is therefore suited to the current single-process MVP rather than a distributed deployment;
- the product uses a web frontend rather than a native/offline technician application;
- complex third-party integrations are outside the current implementation.

## Product Metrics

The repository contains demo data, not validated production results. The following are metrics that would matter if the product were deployed with real service businesses; no actual values are claimed here.

### Operational Metrics

- **Average job completion time** — how long jobs take to move from creation/assignment to completion.
- **Delayed jobs** — jobs that have passed their scheduled time without completion.
- **Jobs by status** — distribution of work across the operational lifecycle.
- **Technician workload** — assigned and active jobs per technician.

These metrics indicate whether work is moving predictably and where operational bottlenecks appear.

### Revenue Metrics

- **Average job value** — average recorded value of completed work.
- **Additional-work conversion** — share of proposed additional work that is approved.
- **Unpaid jobs** — completed work with outstanding payment.
- **Revenue by technician / service type** — commercial mix of completed work where the required underlying data is available.

These are operational revenue signals, not a substitute for accounting.

### Customer Metrics

- **Repeat customers** — customers with multiple service relationships over time.
- **Warranty claims** — volume/share of jobs linked to warranty follow-up.
- **Customer return rate** — customers returning for another service job within a defined period.

These metrics would help test whether retained customer/equipment history creates value beyond a single repair.

## Demo Scenario

The seed script demonstrates several job states rather than only a happy-path repair:

- new work;
- active work;
- pending additional work;
- completed and paid work with a generated PDF;
- same-equipment warranty follow-up;
- cancelled work.

The scenario is designed to make the product lifecycle inspectable locally. It does not represent real customers, revenue, traction, or business performance.
