# Product Definition Document
## Operational Platform for Small Field Service Repair Companies

---

## 1. Product Vision

Small repair businesses (AC, refrigeration, washing machines, boilers, coffee machines, appliances) run on WhatsApp threads, Excel sheets, and paper. The owner cannot answer basic questions — how many jobs are open, which ones are late, how much unbilled work is sitting out there — without calling people.

**Vision:** become the single operational workspace where a repair job lives from first customer call to the end of its warranty. Not a CRM, not an ERP — a lightweight system of record for the thing the business actually sells: the job.

If the owner can open the app each morning and immediately see what's active, what's late, and what's owed, the product has done its job.

---

## 2. Target Users

| Attribute | Profile |
|---|---|
| Company size | 5–30 employees, 2–15 field technicians |
| Volume | 100–1,000 repair jobs/month |
| Structure | Owner-managed, no dedicated ops manager |
| Current tools | WhatsApp, Excel, paper, or a barebones CRM |
| Market | Russia / CIS |
| Buyer | Owner or operations lead |

**User roles in the product:**

1. **Owner / Manager** — full visibility, approves quotes, sees financials, manages team
2. **Dispatcher** (may be the same person as owner in the smallest companies) — creates jobs, assigns technicians, tracks status
3. **Technician** — sees assigned jobs, updates status, logs notes/photos/materials from the field
4. **(Read-only) Accountant/bookkeeper** — optional, views payment and invoice data — explicitly *out of MVP*, mentioned only for roadmap context

---

## 3. Business Problems We're Solving

- Customer and equipment history scattered across chats and notebooks
- Technician knowledge (what was actually done, what parts were used) never recorded
- Additional work discovered on-site is forgotten or never invoiced
- No clear picture of what's been paid vs. owed
- Owner has zero real-time visibility into job status across the team
- Warranty claims are handled from memory, not records
- Repeat customers aren't recognized or leveraged

---

## 4. MVP Scope

**In scope:**
- Repair job lifecycle management (creation → completion → warranty)
- Customer & equipment records
- Technician assignment and mobile-friendly field updates
- Photos, notes, materials, additional work tracking per job
- Basic payment status tracking (not full accounting)
- Document generation (job report / customer summary)
- Owner dashboard with operational metrics
- Optional AI assist layer (voice-note-to-text, summaries, suggestions)

**Explicitly out of scope (see Section 10):** full accounting, warehouse/inventory management, payroll, marketplace, mobile native app, complex integrations, advanced autonomous AI agents.

---

## 5. Core Modules

1. **Jobs** — the core entity and workflow engine
2. **Customers & Equipment** — linked records, repair history per unit
3. **Technicians & Scheduling** — assignment, workload, calendar view
4. **Field Capture** — mobile-friendly web view for technicians (photos, notes, materials, additional work)
5. **Payments (lightweight)** — mark paid/unpaid, amount, method — not invoicing/accounting
6. **Documents** — generate a simple job report / repair certificate as PDF
7. **Warranty** — track warranty period per job/equipment, flag warranty claims
8. **Dashboard & Metrics** — owner's operational view
9. **AI Assist (optional layer)** — voice note transcription, summaries, suggested additional work, Q&A over job history

---

## 6. Main Entities

- **Organization** (the company using the app)
- **User** (owner, dispatcher, technician — role-based)
- **Customer** (name, phone, address(es), notes)
- **Equipment** (type, brand, model, serial number, linked to customer, install/warranty date)
- **Repair Job** (the central entity — see fields below)
- **Job Status History / Activity Timeline**
- **Material/Part used** (simple line item: name, quantity, cost — not full inventory)
- **Additional Work item** (description, price, approved/billed flag)
- **Payment** (amount, method, status, date)
- **Document** (generated PDF tied to a job)
- **Photo** (tied to a job, before/after tagging optional)

**Repair Job fields:**
customer · address · equipment · reported issue · assigned technician · status · photos · technician notes · materials used · additional work · payment info · generated documents · warranty info · activity timeline

**Job statuses (suggested):**
New → Assigned → En Route → In Progress → Awaiting Parts → Awaiting Approval → Completed → Warranty Claim (branch)

---

## 7. Primary Workflows

### 7.1 New Job Intake

**Current process:** Customer calls or messages via WhatsApp. Dispatcher writes it on paper or in a chat, sometimes forgets to log the address or equipment details, later has to call back to clarify.

**Problems:** No structured record. Details get lost. No way to check if this is a repeat customer or if the equipment has prior history.

**How the product improves it:** Dispatcher creates a Job in under a minute, searching/creating the customer and equipment records as they go. If the customer/equipment already exists, prior history surfaces immediately.

**User actions:** Search or create customer → search or create equipment → enter reported issue and address → save (status = New).

**Data created:** Customer record (if new), Equipment record (if new), Job record with status "New", initial timeline entry.

---

### 7.2 Assignment & Dispatch

**Current process:** Owner/dispatcher assigns jobs verbally or via a WhatsApp group message, often based on who's free "off the top of their head."

**Problems:** No visibility into technician workload; double-booking; jobs slip through the cracks.

**How the product improves it:** Dispatcher sees a simple list/calendar of technician workload and assigns the job with one action; technician is notified (in-app, or via a link sent to their phone).

**User actions:** Select job → assign technician → set scheduled time.

**Data created:** Job.assigned_technician, Job.scheduled_time, timeline entry ("Assigned to X").

---

### 7.3 On-Site Execution (Field Capture)

**Current process:** Technician does the repair, maybe texts the owner a photo, writes nothing down formally. Materials used are recalled from memory later (or not at all).

**Problems:** No structured record of what was actually done. Materials/additional work forgotten. Nothing to show the customer.

**How the product improves it:** Technician opens the job on their phone (mobile web, no native app needed), updates status as they go, adds photos, notes (optionally via voice-to-text AI), logs materials used, and flags additional work needed with a price for owner/customer approval.

**User actions:** Update status → add photos → add notes → log materials → (optional) flag additional work.

**Data created:** Status updates + timeline entries, Photo records, technician notes text, Material line items, Additional Work item (pending approval).

---

### 7.4 Additional Work Approval & Billing

**Current process:** Technician tells the customer verbally "this will cost extra," sometimes never communicates it to the office, and it's never billed.

**Problems:** Lost revenue. No paper trail if the customer disputes it later.

**How the product improves it:** Additional work appears as a flagged item requiring owner (or customer, via shared link — future) approval before being marked billable; dashboard shows "jobs with unbilled additional work" as a metric so nothing falls through.

**User actions:** Owner reviews flagged additional work → approves/rejects → marks billed once invoiced externally (MVP doesn't do invoicing itself).

**Data created:** Additional Work status (approved/rejected/billed), timeline entry.

---

### 7.5 Job Completion & Documentation

**Current process:** Job "just ends" — nothing formal is sent to the customer, no record kept beyond a chat thread that gets lost.

**Problems:** No proof of work for warranty disputes; no professional document for the customer; no closure signal for the owner's tracking.

**How the product improves it:** On completion, the system generates a simple PDF job report/repair certificate (issue, work done, materials, technician, warranty terms) that can be sent to the customer or printed.

**User actions:** Technician/dispatcher marks job Completed → system generates document → send/download.

**Data created:** Job status = Completed, Document record (PDF), completion timestamp (used for completion-time metrics).

---

### 7.6 Payment Tracking

**Current process:** Owner tracks who's paid in their head or in an Excel column that's rarely up to date.

**Problems:** No clear picture of outstanding payments across the business.

**How the product improves it:** Each job has a simple payment field — amount, method, paid/unpaid — visible on the dashboard as "unpaid jobs."

**User actions:** Mark payment status and amount on the job.

**Data created:** Payment record linked to job.

---

### 7.7 Warranty Handling

**Current process:** Customer calls back weeks later saying it broke again; owner has no record of when the original repair happened or what the warranty terms were.

**Problems:** Disputes, lost trust, inability to verify warranty validity.

**How the product improves it:** Each completed job carries a warranty period; if a new job is created for the same equipment within that window, the system flags it as a potential warranty case and links to the original job's history.

**User actions:** System auto-flags; dispatcher confirms warranty case when creating the new job.

**Data created:** Job.is_warranty_claim flag, link to originating Job.

---

## 8. Suggested Application Screens

1. **Login / Organization setup**
2. **Dashboard** (owner view — active/delayed/completed counts, unbilled additional work, revenue snapshot)
3. **Jobs List** (filterable by status, technician, date)
4. **Job Detail** (the core screen — all fields, timeline, photos, documents)
5. **New Job / Edit Job form**
6. **Customers List + Customer Detail** (with equipment and job history)
7. **Equipment Detail** (repair history for that specific unit)
8. **Technicians List** (workload view)
9. **Technician Mobile View** (simplified job list + field capture form)
10. **Calendar / Schedule view** (basic — day/week list of assigned jobs)
11. **Settings** (users, roles, organization info)

---

## 9. Product Success Metrics

- Active jobs (current count)
- Delayed jobs (past scheduled time, not completed)
- Completed jobs (period-over-period)
- Average job completion time
- Revenue per technician
- Average order value
- % of jobs with additional work
- % of additional work billed vs. unbilled
- Repeat customer rate
- Warranty case count

---

## 10. Features Intentionally Excluded from MVP

- Full accounting / bookkeeping / invoicing engine
- Warehouse & inventory management (materials are logged, not tracked as stock)
- Payroll and technician compensation calculation
- ERP-level reporting or multi-branch consolidation
- Marketplace / customer-facing booking portal
- Native mobile application (mobile web is sufficient at this stage)
- Advanced autonomous AI agents (auto-scheduling, auto-negotiation, etc.)
- Complex third-party integrations (accounting software, payment gateways, telephony)
- Customer self-service portal
- SLA/contract management

---

## 11. Future Roadmap (Post-MVP)

**Phase 2 (validate + expand):**
- Customer-facing status link (SMS/WhatsApp link to track job status)
- Basic invoicing / export to accounting software (1C, etc.)
- Simple inventory/materials stock tracking
- Native mobile app for technicians (offline support)

**Phase 3 (scale):**
- Multi-branch / multi-location support
- Route optimization for technician scheduling
- Deeper AI: automatic quote suggestions, predictive maintenance flags
- Customer self-booking portal
- Integrations (telephony/CRM, payment gateways, accounting systems)

**Phase 4 (platform):**
- Marketplace connecting customers to service companies
- Analytics benchmarking across companies (anonymized)
- API for third-party integrations

---

## Guiding Principle

Every feature decision should pass one test: **does this help the owner see and control what's happening with repair jobs, right now, with minimum friction?** If a feature doesn't directly serve that, it's a Phase 2+ conversation, not an MVP conversation.
