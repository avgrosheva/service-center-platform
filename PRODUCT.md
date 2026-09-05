# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Small field-service and repair businesses (AC, refrigeration, washing machines, boilers, coffee machines, general appliances) with 5–30 employees and 2–15 field technicians, running 100–1,000 repair jobs/month. Primarily owner-managed, with no dedicated ops manager. Target market is Russia/CIS; the current tools these businesses replace are WhatsApp threads, Excel sheets, and paper.

Three roles use the product today:

1. **Owner / Manager** — full visibility, approves quotes, sees financials, manages the team. This is the buyer.
2. **Dispatcher** (may be the same person as the owner in the smallest companies) — creates jobs, assigns technicians, tracks status.
3. **Technician** — sees assigned jobs, updates status, logs notes/photos/materials from the field, typically on a phone, on-site.

A fourth role, a read-only accountant/bookkeeper viewing payment and invoice data, is explicitly out of MVP scope and mentioned only for roadmap context.

## Product Purpose

Service Center Platform (working title) is a lightweight operational workspace where a repair job lives from first customer call through the end of its warranty. It exists so an owner can open the app each morning and immediately see what's active, what's late, and what's owed — without calling people. It is a system of record for the repair job, not a CRM and not an ERP.

## Positioning

The **Repair Job** is the central operational record, not the customer and not a generic ticket. A job connects the customer and equipment to the technician, current status, activity timeline, photos, materials, additional work, payment, generated documents, and warranty context in one place. Competing tools force the team to track these pieces across separate systems (chat, spreadsheet, paper, generic CRM); this product's mechanism is that one record follows the job through its entire lifecycle:

```
Customer → Repair Job → Technician → Work → Additional Work → Payment → Documents → Warranty
```

## Operating Context

- Dispatchers and owners typically work from a desktop/laptop in an office setting.
- Technicians work in the field, on-site at the customer's location, and use the product on a phone — the mobile web view for technicians (job list + field capture form) is a first-class surface, not an afterthought.
- Core recurring workflows: new job intake, assignment/dispatch, on-site execution (field capture), additional-work approval and billing, job completion and documentation (generated PDF job report/repair certificate), payment tracking (paid/unpaid, not full accounting), and warranty handling (auto-flagged repeat issues on the same equipment within the warranty window).
- The team currently coordinates this work manually across WhatsApp, Excel, and paper — the product's job is to replace that coordination overhead, not to add process.
- Demo/seed data exists (`backend/app/seed_demo_data.py`) exercising new/active/pending/completed/warranty/cancelled job states; requires a running Postgres + MinIO. Not idempotent, illustrative only.

## Capabilities and Constraints

**In MVP scope:** authentication and organization/users (including self-service profile editing — name, email, phone, password, avatar), customers (with job history), equipment (with job history), repair jobs, technician assignment, status transitions and activity timeline, photos, materials, additional work (capture + approval + billed flag), lightweight payments (amount/method/paid-unpaid, not invoicing), generated PDF documents per job, warranty logic (auto-flag same-equipment repeat within warranty window), owner dashboard, and an optional AI-assist layer (voice-note-to-text, summaries, suggested additional work) that supports but does not replace operational decisions.

**Explicitly out of scope:** full accounting/bookkeeping/invoicing engine, warehouse/inventory management (materials are logged as line items, not tracked as stock), payroll, native mobile apps (mobile web is the field surface), customer self-service/self-booking portal, marketplace, multi-branch/multi-location support, SLA/contract management, complex third-party integrations (accounting software, payment gateways, telephony), and advanced autonomous AI agents.

**Localization:** the product must support Russian as a real UI language (Cyrillic script), not just English with Russia/CIS as background market context. Design decisions (typography, layout for text expansion/contraction) need to account for this.

**Stack (existing codebase, not a greenfield decision):** Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/Base UI on the frontend; Python 3.13, FastAPI, PostgreSQL 16, SQLAlchemy Async, Alembic, Pydantic v2 on the backend; S3-compatible object storage (MinIO locally) for photos and generated PDFs; Docker Compose for local orchestration.

## Brand Commitments

None yet. "Service Center Platform" is a working/descriptive title, not a finalized product name or binding identity — visual and naming decisions remain open for future design work.

## Evidence on Hand

- Product documentation: `docs/product-definition.md`, `docs/architecture.md`, `docs/product-case-study.md`, `docs/technical-blueprint.md`, `docs/implementation-roadmap.md`.
- Screenshots of the current implementation exist under `docs/images/` (dashboard, job details, jobs list, schedule) and are referenced from the README — real product screens, not staged marketing imagery.
- No testimonials, customer logos, press, pricing, or benchmark data exist; future work must not fabricate any of these.
- Frontend now runs a custom design system ("Studio Console" — see `DESIGN.md`): a sage workspace background, a single accent color (`#04ca8b`), and a distinct typographic system (Golos Text for body/headings, JetBrains Mono for tabular data, Oswald for tracked-caps labels), replacing the earlier default shadcn tokens.
- The Russian-localization requirement above is implemented, not just planned: a full English/Russian UI toggle (`frontend/lib/i18n/`) covers every page and component, with locale persisted per browser and detected from `navigator.language` on first visit.

## Product Principles

1. The repair job, not the customer or a generic ticket, is the unit the whole product organizes around — every feature should attach to a job's lifecycle.
2. Field capture on a technician's phone is a first-class surface, not a scaled-down afterthought of the desktop dispatcher/owner experience.
3. Every feature decision is tested against: does this help the owner see and control what's happening with repair jobs, right now, with minimum friction? Anything else is a post-MVP conversation.
4. Stay a lightweight system of record — deliberately resist full-ERP scope creep (accounting, inventory, payroll, multi-branch).
5. Design must work in Russian (Cyrillic) as a real, primary UI language, not as a translation layer bolted onto an English-first design.

## Accessibility & Inclusion

No formal accessibility standard has been specified; follow solid accessibility practice by default (contrast, focus states, keyboard navigation, semantic structure).
