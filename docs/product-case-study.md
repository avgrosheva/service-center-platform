# Service Center Platform --- Product Case Study

## Overview

Service Center Platform is a lightweight operational platform for small
field-service and repair companies.

The product is organized around one central idea: the **Repair Job** is
the unit that connects the customer request to the work the business
actually performs.

``` text
Customer → Repair Job → Technician → Work → Payment → Documents → Warranty
```

The MVP focuses on making that lifecycle visible and traceable without
expanding into a full ERP, accounting package, inventory system, or
marketplace.

## Problem

Small service businesses can operate with a fragmented set of tools:
customer conversations in messaging apps, schedules in spreadsheets,
repair details in technicians' notes, payments in a separate list, and
warranty history in people's memory.

The problem is not simply that information is stored in several places.
The larger issue is that there is no single operational record showing
what is happening with a repair from intake to closure.

That creates uncertainty around questions such as:

-   What jobs are currently active?
-   Who is responsible for each job?
-   What has already happened on the job?
-   Was additional work discovered and approved?
-   What materials were used?
-   Has the customer paid?
-   Was a repair document generated?
-   Is a later repair potentially covered by warranty?

## Target Customer

The product is designed for small field-service and repair companies
where an owner or dispatcher still has direct involvement in daily
operations and technicians perform work in the field.

Examples of relevant service contexts include appliance, HVAC,
refrigeration, boiler, coffee-machine, and similar repair businesses.

The product assumes a relatively lean operation that needs more
structure than chats and spreadsheets provide, but does not need the
complexity of a large ERP.

Primary product roles are:

-   **Owner / Manager** --- needs visibility across jobs, team activity,
    payments, and operational exceptions.
-   **Dispatcher** --- creates jobs, connects customers and equipment,
    assigns technicians, and tracks progress.
-   **Technician** --- works from assigned jobs and records operational
    information such as status updates, photos, notes, materials, and
    additional work.

## Operational Problems

### Fragmented customer and equipment history

A repeat customer or previously repaired unit may already have useful
history, but that history is difficult to use when it lives across chat
threads or informal notes.

### Unclear job ownership and status

When assignments and status updates happen verbally or through
messaging, it becomes difficult to maintain a reliable view of what is
new, assigned, in progress, delayed, completed, or cancelled.

### Field knowledge disappears

The technician knows what happened during a repair, but that knowledge
has limited operational value if it never becomes part of the job
record.

### Additional work can become lost revenue

A technician may discover extra work on-site, but a verbal agreement is
easy to lose between the field and the office. The product therefore
treats additional work as a structured object rather than an informal
note.

### Payments are disconnected from operations

The MVP does not attempt to become accounting software. It does,
however, keep basic payment state with the job so the operational team
can distinguish completed work from completed-and-paid work.

### Documentation is detached from the repair history

Generated repair documents are more useful when they remain attached to
the same job that contains the work, materials, technician, and warranty
context.

### Warranty follow-up depends on memory

When a customer returns with the same equipment, the business needs a
reliable way to connect the new issue to the previous repair and its
warranty period.

## Product Solution

Service Center Platform creates a shared operational record for each
repair.

The platform connects:

``` text
Customer
   ↓
Equipment
   ↓
Repair Job
   ├── Assignment
   ├── Status
   ├── Timeline
   ├── Photos
   ├── Materials
   ├── Additional Work
   ├── Payment
   ├── Documents
   └── Warranty Context
```

This keeps operational context close to the job rather than splitting
the workflow into unrelated modules.

The product is deliberately narrower than an ERP. Its purpose is to make
repair operations understandable and controllable with minimal overhead.

## The Core Repair Job Concept

The **Repair Job** is the central product entity.

A job represents more than a task assigned to a technician. It is the
record that carries the repair through its full lifecycle.

It connects:

-   the customer;
-   the equipment being serviced;
-   the reported problem;
-   the assigned technician;
-   scheduling information;
-   current status and status history;
-   field notes and photos;
-   materials used;
-   additional work;
-   payment information;
-   generated documents;
-   warranty information;
-   the activity timeline.

This model creates one place to answer both "what needs to happen next?"
and "what happened on this repair?"

## Main User Workflow

``` text
Request
   ↓
Create / select customer and equipment
   ↓
Create repair job
   ↓
Assign technician and scheduled time
   ↓
Technician performs diagnosis / work
   ↓
Record status, notes, photos and materials
   ↓
Capture additional work when needed
   ↓
Complete repair and record payment
   ↓
Generate job document
   ↓
Retain history for future warranty follow-up
```

The workflow is intentionally linear at the product level while still
allowing real service states such as waiting for approval, waiting for
parts, cancellation, and warranty follow-up.

## Important Product Decisions

### 1. Make the repair job the center of the product

The implementation is job-centric rather than CRM-centric.

Customer and equipment records matter because they provide context and
history, but the operational unit the business needs to move forward
every day is the job. This keeps the product focused on execution rather
than building a broad customer-management suite.

### 2. Preserve an activity timeline instead of relying only on current status

A current status answers where the job is now. A timeline explains how
it got there.

Keeping status changes and relevant activity as history makes the job
useful for operational follow-up, handoffs, and later warranty
questions.

### 3. Model additional work explicitly

Additional work is not stored only as technician notes.

It has its own structured state because it represents a critical handoff
between diagnosis, approval, and billing. This is one of the places
where operational information can directly affect whether completed work
is captured commercially.

### 4. Track materials without building inventory management

Materials used on a job are operationally relevant, so they are recorded
as job-level line items.

The MVP intentionally stops there. It does not introduce warehouses,
stock movements, purchasing, reorder logic, or inventory reconciliation.
That keeps the scope aligned with service execution rather than ERP
functionality.

### 5. Keep payment tracking lightweight

Payment belongs in the job lifecycle because an operationally completed
repair may still be unpaid.

The MVP records payment information without trying to become a
bookkeeping, invoicing, or payment-processing platform. This preserves
visibility while avoiding a large adjacent product domain.

### 6. Connect warranty logic to equipment history

Warranty is treated as a continuation of repair history rather than a
separate support module.

When a new job is created for the same equipment within the relevant
warranty window, the system can identify it as a potential warranty case
and retain the connection to the original repair.

### 7. Prefer a mobile-friendly web product over a native technician app

Technicians need field access, but a native mobile application would add
a separate product and engineering surface.

The MVP uses the web application so the same system can support office
and field workflows without introducing app-store distribution, native
release cycles, or offline synchronization.

## MVP Scope

The implemented MVP focuses on the operational repair lifecycle.

Included capabilities:

-   authentication and organization/user management;
-   customer records;
-   equipment records and repair history;
-   repair-job creation and lifecycle management;
-   technician assignment and scheduling;
-   status transitions and job timeline;
-   field photos and notes;
-   materials used;
-   additional-work tracking;
-   lightweight payment tracking;
-   PDF document generation;
-   warranty/follow-up logic;
-   owner dashboard;
-   optional AI assistance as a supporting layer;
-   a Next.js web interface for the main operational workflows.

## Intentionally Excluded Functionality

The following areas are deliberately outside the MVP:

-   full accounting and bookkeeping;
-   a full invoicing engine;
-   warehouse and inventory management;
-   payroll and technician compensation calculation;
-   ERP-level reporting and multi-branch consolidation;
-   marketplace functionality;
-   native mobile applications;
-   customer self-service portal;
-   customer self-booking;
-   SLA and contract management;
-   complex integrations with accounting systems, payment gateways,
    telephony, or external CRMs;
-   advanced autonomous AI agents.

These exclusions are product decisions, not missing pieces required to
understand the current MVP. Each would substantially expand the problem
space beyond repair operations.

## Current Limitations

The current implementation should be understood as an MVP rather than a
production-scale service platform.

Notable limitations include:

-   payment tracking is operational, not accounting-grade;
-   materials are logged per job but stock is not managed;
-   document generation runs as an in-process background task and does
    not have queue-backed retry guarantees;
-   warranty checking does not rely on a dedicated production
    scheduler/worker infrastructure;
-   login rate limiting is in-memory and therefore designed for the
    current single-process MVP shape rather than distributed deployment;
-   the web application replaces a native technician app, so
    native/offline mobile behavior is outside the current
    implementation;
-   complex external integrations are intentionally absent.

## Product Metrics

The current repository does **not** claim real business performance or
production metrics. If the product were deployed and validated with real
service businesses, the following metrics would be useful for evaluating
whether it improves operations.

### Operational

-   **Average job completion time** --- time from job creation or
    assignment to completion.
-   **Delayed jobs** --- jobs past their scheduled time that are not
    completed.
-   **Jobs by status** --- distribution of work across the repair
    lifecycle.
-   **Technician workload** --- assigned/active jobs by technician over
    a selected period.

These metrics would indicate whether work is moving through the system
predictably and whether operational bottlenecks are visible.

### Revenue

-   **Average job value** --- average recorded value of completed jobs.
-   **Additional-work conversion** --- share of proposed additional work
    that is approved/billed.
-   **Unpaid jobs** --- completed work that still has outstanding
    payment.
-   **Revenue by technician / service type** --- useful for
    understanding the commercial mix of completed work where the
    underlying data is available.

These are product-relevant operational revenue metrics, not a
replacement for accounting.

### Customer

-   **Repeat customers** --- customers with more than one repair
    relationship over time.
-   **Warranty claims** --- volume and share of jobs identified as
    warranty follow-ups.
-   **Customer return rate** --- share of customers who return for
    another service job over a defined period.

These metrics would help evaluate whether the stored customer/equipment
history becomes useful beyond a single repair.

No actual values are included here because the repository contains demo
data rather than validated production usage.

## Demo Scenario

The seed script demonstrates multiple job states through the real
service layer rather than presenting a single idealized happy path.

It includes examples of:

-   new work;
-   work already in progress;
-   pending additional work;
-   a completed and paid repair with a generated PDF;
-   a same-equipment follow-up that can be recognized as a warranty
    case;
-   a cancelled repair.

This makes the repository useful as a product demonstration without
implying real customers or business traction.

## Product Principle

The MVP follows a simple scope rule:

> A feature belongs in the core product when it helps the business
> understand, execute, or close a repair job with less operational
> ambiguity.

That is why customer history, assignments, additional work, payment
state, documents, and warranty context are included --- while full
accounting, inventory, payroll, marketplace functionality, and complex
integrations are not.
