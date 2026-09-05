# Frontend Implementation Roadmap
## Field Service Repair Operations Platform — MVP

Companion document to the Product Definition, Technical Blueprint, and Backend Implementation Roadmap. The backend (Milestones 0–19) is complete and live at `/api/v1/*` with JWT auth. This roadmap breaks frontend implementation into small, independently testable milestones, each sized for a single focused development session (roughly half a day to a day and a half).

**Stack constant across all milestones:** Next.js (App Router), React, TypeScript, Tailwind CSS, shadcn/ui — per the frozen Technical Blueprint. The frontend is a pure consumer of the existing REST API; no backend endpoints are redesigned or added here. If a milestone reveals a genuine API gap, that's flagged as a question back to backend planning, not silently patched from the frontend.

**Screens covered** (from Product Definition §8): Login/org setup, Dashboard, Jobs List, Job Detail, New/Edit Job form, Customers List + Detail, Equipment Detail, Technicians List, Technician Mobile View, Calendar/Schedule, Settings.

---

## Milestone F0 — Project Bootstrap

**Goal:** a running Next.js app with the project structure in place, deployable locally, talking to the backend.

**Components implemented:**
- Next.js (App Router) + TypeScript project scaffold
- Tailwind CSS configured; shadcn/ui initialized (base components installed as needed per milestone, not all upfront)
- Folder structure: `app/` (routes), `components/` (shared UI), `lib/` (API client, utils), `hooks/`, `types/`
- `.env.local.example` with `NEXT_PUBLIC_API_BASE_URL` pointing at the backend
- ESLint + Prettier configured
- A trivial page confirming the app boots and can reach the backend's `/health`

**Dependencies:** none — starting point. Backend must be running locally (`docker compose up -d db && uvicorn app.main:app`) for the connectivity check to mean anything.

**API endpoints consumed:** `GET /health` (connectivity smoke check only).

**Testing checklist:**
- [ ] `npm run dev` boots without errors
- [ ] Page fetches `/health` and displays the backend's status
- [ ] Lint/format run clean on a fresh checkout

**Complexity:** Low
**Estimated time:** 0.5 day
**Risks:** Low.
**Prerequisites:** Backend running locally.

---

## Milestone F1 — API Client & Types

**Goal:** a single typed layer for talking to the backend — nothing else in the app should call `fetch` directly.

**Components implemented:**
- `lib/api-client.ts` — thin wrapper around `fetch`: base URL, JSON handling, attaches the auth token, normalizes error responses (matches the backend's consistent `{"detail": "..."}` shape from Milestone 19)
- `types/api.ts` — TypeScript interfaces mirroring the backend's Pydantic schemas (Organization, User, Customer, Equipment, Job, JobStatus, Photo, MaterialItem, AdditionalWorkItem, Payment, Document, AITask) — hand-written to match, since there's no shared codegen step in this stack
- A typed error class distinguishing 401 (redirect to login), 403 (permission), 404 (not found), 422 (validation), 5xx (generic failure) — so every screen can handle these consistently instead of each component reinventing error handling

**Dependencies:** F0.

**API endpoints consumed:** none new — this is the client that every later milestone's endpoints flow through.

**Business logic:** centralize the 401 → redirect-to-login behavior here, once, rather than in every page/hook.

**Testing checklist:**
- [ ] Client correctly attaches `Authorization: Bearer <token>` when a token is present
- [ ] A 401 response triggers the shared redirect behavior
- [ ] A 422 response surfaces field-level validation detail in a shape components can use
- [ ] Types compile against a few real backend responses (spot-check against the running API, not just written from memory of the schema)

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Medium — getting the error-shape handling right here saves rework in every later milestone; worth not rushing.
**Prerequisites:** F0.

---

## Milestone F2 — Authentication

**Goal:** a user can register, log in, stay logged in across a refresh, and log out; protected routes redirect unauthenticated users to login.

**Components implemented:**
- `app/login/page.tsx`, `app/register/page.tsx`
- `lib/auth.ts` — token storage strategy (see decision below), `useAuth()` hook exposing current user/role/loading state
- `AuthProvider` context wrapping the app
- Route protection: a layout-level guard that redirects to `/login` when unauthenticated, and (for role-gated pages) redirects/403s when the role doesn't match

**Dependencies:** F1.

**API endpoints consumed:** `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `GET /api/v1/auth/me`.

**Business logic:**
- **Token storage decision to make explicitly before writing code:** httpOnly cookie (via a Next.js route handler proxying the backend) vs. in-memory + refresh-on-load. httpOnly cookies are more resistant to XSS but require a thin Next.js API route to set/read them (the backend itself just issues bearer tokens, per the Technical Blueprint). Recommend httpOnly cookie via a Next.js route handler — flag this as a decision to confirm before building, since it shapes every other milestone's auth handling.
- Access token refresh happens transparently on 401 (attempt refresh once, retry the original request, otherwise redirect to login) — not on a timer.
- `useAuth()` exposes `role` so components can conditionally render (technician vs. dispatcher/owner UI) without each one re-deriving it.

**Validation rules:** client-side mirrors of the backend's obvious constraints (email format, password minimum length) for immediate feedback — never a substitute for the backend's own validation, just UX.

**Testing checklist:**
- [ ] Register → redirected to dashboard, session persists on refresh
- [ ] Login with wrong password shows the backend's error message, not a generic one
- [ ] Logout clears the session and redirects to login
- [ ] An expired/invalid token triggers the refresh flow, and a failed refresh redirects to login
- [ ] Visiting a protected route while logged out redirects to login; visiting login while logged in redirects to dashboard
- [ ] Technician role is correctly exposed and distinguishable from owner/dispatcher

**Complexity:** Medium-High (the token storage decision and refresh flow are the riskiest part of the whole frontend)
**Estimated time:** 1.5 days
**Risks:** Medium-High — get this wrong and every later milestone inherits the problem. Worth a deliberate decision on cookie vs. in-memory storage before writing code, not an accident of whatever's fastest to type.
**Prerequisites:** F1.

---

## Milestone F3 — App Shell & Navigation

**Goal:** a consistent layout (nav, header, current-user display) wrapping every authenticated page, with role-appropriate navigation.

**Components implemented:**
- `app/(authenticated)/layout.tsx` — shared shell: sidebar/topbar nav, user menu (name, org, logout)
- Role-based nav items: technicians see a reduced menu (their jobs, nothing else); owner/dispatcher see the full set (Dashboard, Jobs, Customers, Settings)
- Responsive behavior established here once (mobile nav collapse), since Milestone F13 (Technician Mobile View) builds on it rather than reinventing layout

**Dependencies:** F2.

**API endpoints consumed:** `GET /api/v1/auth/me` (already fetched by F2's auth context; this milestone just consumes it for display).

**Testing checklist:**
- [ ] Nav renders correctly for each of the three roles
- [ ] Logout from the user menu works
- [ ] Layout is usable at mobile width (not final mobile-specific UI — that's F13 — just not broken)

**Complexity:** Low-Medium
**Estimated time:** 0.75 day
**Risks:** Low.
**Prerequisites:** F2.

---

## Milestone F4 — Dashboard

**Goal:** the owner/dispatcher landing page — the screen the roadmap's backend milestones called "the whole reason the product exists."

**Components implemented:**
- `app/(authenticated)/dashboard/page.tsx`
- Summary cards (active/delayed/completed/unbilled counts)
- Metrics section (avg completion time, revenue per technician, AOV, repeat-customer rate, warranty case count)
- Date-range filter control

**Dependencies:** F3.

**API endpoints consumed:** `GET /api/v1/dashboard/summary`, `GET /api/v1/dashboard/metrics`.

**Business logic:** this page is read-only — no mutations. Role-gate at the route level (technician never reaches this page, consistent with the backend's own 403).

**Testing checklist:**
- [ ] All summary/metric values render and match what a manual API call returns for the same org/date-range
- [ ] Date-range filter re-fetches and updates the metrics section (not the summary section, per the backend's own scoping decision from Milestone 16)
- [ ] Technician attempting to navigate here directly is redirected/blocked
- [ ] Empty-data state (new org, no jobs yet) renders sensibly, not a broken layout

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Low-Medium — mostly about not misreading which numbers are date-scoped vs. snapshot, per the backend's documented distinction.
**Prerequisites:** F3.

---

## Milestone F5 — Customers

**Goal:** list, view, create, and edit customers.

**Components implemented:**
- `app/(authenticated)/customers/page.tsx` (list + search)
- `app/(authenticated)/customers/[id]/page.tsx` (detail — shows equipment list and job history; job history landed after F7 shipped `customer_id`/`equipment_id` filters on `GET /jobs`, via a shared `JobHistoryList` component reused by both this page and Equipment Detail)
- Create/edit forms (shadcn form components)

**Dependencies:** F3.

**API endpoints consumed:** `GET /api/v1/customers`, `POST /api/v1/customers`, `GET /api/v1/customers/{id}`, `PATCH /api/v1/customers/{id}`, `DELETE /api/v1/customers/{id}`.

**Business logic:** search-as-you-type against the backend's `ILIKE` search (debounced, not fired on every keystroke).

**Validation rules:** mirror the backend's (full_name required, basic phone format) client-side for immediate feedback.

**Testing checklist:**
- [ ] List renders, search filters correctly, debounced (not one request per keystroke)
- [ ] Create/edit forms round-trip correctly and surface backend validation errors (422) inline on the right field
- [ ] Archive (soft-delete) works and removed customer no longer appears in the default list
- [ ] Technician cannot reach this section at all

**Complexity:** Low-Medium
**Estimated time:** 1 day
**Risks:** Low.
**Prerequisites:** F3.

---

## Milestone F6 — Equipment

**Goal:** equipment nested under a customer, plus its own detail view with repair history.

**Components implemented:**
- Equipment list embedded in the Customer Detail page (F5) — now filled in for real
- `app/(authenticated)/equipment/[id]/page.tsx` — detail view showing repair history (list of jobs on this equipment)
- Create/edit forms for equipment, including `installation_address`

**Dependencies:** F5.

**API endpoints consumed:** `GET /api/v1/customers/{customer_id}/equipment`, `POST /api/v1/customers/{customer_id}/equipment`, `GET /api/v1/equipment/{id}`, `PATCH /api/v1/equipment/{id}`.

**Business logic:** none new on the frontend — this is a straightforward CRUD screen. Worth noting for whoever builds this: editing `installation_address` here does **not** retroactively change any existing job's `address_snapshot` (backend-enforced invariant from Milestone 8) — the UI doesn't need to do anything special for this, just shouldn't imply otherwise (e.g., don't show a "this will update all related jobs" message, since it won't).

**Testing checklist:**
- [ ] Equipment list under a customer renders and links to detail
- [ ] Create/edit round-trips correctly
- [x] Repair history on equipment detail shows real jobs, filtered by `equipment_id` on `GET /jobs` — landed post-F7, once that filter existed

**Complexity:** Low
**Estimated time:** 0.75 day
**Risks:** Low.
**Prerequisites:** F5.

---

## Milestone F7 — Jobs List

**Goal:** the primary operational view — filterable list of jobs.

**Components implemented:**
- `app/(authenticated)/jobs/page.tsx`
- Filters: status, technician, date range (matching the backend's actual filter support)
- Status displayed with clear visual distinction (a status badge/color scheme covering all 8 `JobStatus` values)

**Dependencies:** F3.

**API endpoints consumed:** `GET /api/v1/jobs` (with query filters — `status`, `assigned_technician_id`, `scheduled_from`/`scheduled_to`, plus `customer_id`/`equipment_id` added later specifically for the Customer/Equipment Detail job-history sections in F5/F6).

**Business logic:** for technicians, this list is implicitly scoped to their own assigned jobs by the backend already (Milestone 9's `_can_view_or_act_on_jobs` scoping) — the frontend doesn't need to filter client-side, just needs to not show a technician-only filter dropdown to a technician (since it'd be meaningless).

**Testing checklist:**
- [ ] List renders with correct status badges for all 8 statuses
- [ ] Each filter (status/technician/date range) works independently and combined
- [ ] Technician sees only their own jobs, with no technician-filter control shown (since it's redundant for them)
- [ ] Empty state (no jobs matching filters) renders sensibly

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Low-Medium.
**Prerequisites:** F3.

---

## Milestone F8 — New Job Form

**Goal:** dispatcher/owner can create a job.

**Components implemented:**
- `app/(authenticated)/jobs/new/page.tsx`
- Customer picker (search/select existing, or inline-create — decide which based on how F5's create flow feels; inline-create is a nice-to-have, not required for MVP)
- Equipment picker scoped to the selected customer (or manual address entry if no equipment selected, matching the backend's own flexibility from Milestone 8)
- Manual `is_warranty_claim` override control (matching the backend's Milestone 15 override support) — optional, defaults to unset/auto-detect

**Dependencies:** F5, F6, F7.

**API endpoints consumed:** `POST /api/v1/jobs`, plus `GET /api/v1/customers`/`GET /api/v1/customers/{id}/equipment` for the pickers.

**Business logic:** if no equipment is selected, the address field becomes required (mirrors the backend's own `model_validator` from Milestone 8) — validate this client-side for immediate feedback, but the backend remains the real enforcement.

**Testing checklist:**
- [ ] Creating with an existing customer+equipment correctly snapshots the address (verify the created job's `address_snapshot` in the response)
- [ ] Creating without equipment requires and accepts a manual address
- [ ] Validation error (e.g., missing `reported_issue`) surfaces inline, matching the backend's 422 response
- [ ] Successful creation navigates to the new job's detail page (F9)
- [ ] Technician cannot reach this form (blocked at the route level, matching backend's `_can_manage_jobs` gate)

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Low-Medium.
**Prerequisites:** F5, F6, F7.

---

## Milestone F9 — Job Detail: Core (Info, Status, Timeline)

**Goal:** the central screen of the whole app — job info, status transition controls, and the activity timeline. This milestone covers the core; sub-resources (photos, materials, additional work, payment, documents) are separate milestones so this one stays a manageable size.

**Components implemented:**
- `app/(authenticated)/jobs/[id]/page.tsx` — job info panel, editable fields (issue/address/schedule)
- Status transition control — only shows the transitions actually valid from the current status (mirrors the backend's `_ALLOWED_TRANSITIONS` state machine; don't hardcode a duplicate list — derive allowed next-statuses from what the backend accepts, either by attempting and handling 400 gracefully, or by hand-encoding the same transition map with an explicit comment that it must stay in sync with the backend's)
- Assign-technician control (technician picker, only shown when status is `new`, matching backend Milestone 9 constraint)
- Timeline component — chronological list of all event types (status changes, assignment, photo/material/additional-work/document events — the last few render placeholder-friendly until their own milestones land)
- Cancel action

**Dependencies:** F7.

**API endpoints consumed:** `GET /api/v1/jobs/{id}`, `PATCH /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/assign`, `POST /api/v1/jobs/{id}/status`, `GET /api/v1/jobs/{id}/timeline`, `DELETE /api/v1/jobs/{id}`.

**Business logic:**
- Technician viewing their own assigned job sees a reduced action set (status updates, no reassignment/cancel — matching `_can_manage_jobs` vs `_can_view_or_act_on_jobs` split from Milestone 9).
- An invalid transition attempt (should be prevented by only showing valid options, but the backend is the real guard) surfaces the 400 message clearly rather than failing silently.

**Testing checklist:**
- [ ] All job fields display correctly; editable fields save via PATCH
- [ ] Status control only offers valid next-transitions for the current status, across a few different starting statuses
- [ ] Assign control only appears when status is `new`, and disappears after assignment
- [ ] Timeline renders all event types in chronological order
- [ ] Technician sees the reduced action set on their own job; cannot reach a job not assigned to them (403/404 handled gracefully, not a broken page)
- [ ] Cancel works and is blocked from a terminal state (matching backend's Milestone 9 fix)

**Complexity:** Medium-High
**Estimated time:** 1.5 days
**Risks:** Medium — the status-transition-options-derived-from-backend-state-machine point is worth getting right; a hardcoded duplicate that drifts from the backend is a real future bug source.
**Prerequisites:** F7.

---

## Milestone F10 — Job Detail: Field Data (Photos & Materials)

**Goal:** photo upload (presigned flow) and materials logging, as sections within the Job Detail page.

**Components implemented:**
- Photo section: upload button → request presigned URL → direct upload to S3/MinIO → confirm with backend → thumbnail grid
- Materials section: add/edit/remove line items, inline table

**Dependencies:** F9.

**API endpoints consumed:** `POST /api/v1/jobs/{id}/photos/upload-url`, `POST /api/v1/jobs/{id}/photos`, `GET /api/v1/jobs/{id}/photos`, `POST/GET/PATCH/DELETE /api/v1/jobs/{id}/materials[/{item_id}]`.

**Business logic:** the two-step photo upload (presigned URL → direct S3 PUT → confirm) must be implemented exactly as the backend expects — a single "upload" button click triggers all three requests in sequence, with a loading state covering the whole sequence (not just the first request).

**Testing checklist:**
- [ ] Photo upload completes the full three-step flow and the photo appears in the grid without a manual refresh
- [ ] Unsupported file type is rejected client-side before attempting upload (matching backend's 422 on content-type)
- [ ] Material add/edit/remove all work and reflect immediately
- [ ] Quantity/cost validation errors surface inline
- [ ] Technician has full access on their own job, is blocked on others (matching backend)

**Complexity:** Medium-High (the presigned upload flow is the trickiest interaction in the whole frontend)
**Estimated time:** 1.5 days
**Risks:** Medium — get the upload sequencing/error-handling right; a failed step 2 (direct S3 upload) after a successful step 1 (presigned URL) needs a clear retry path, not a silent dead end.
**Prerequisites:** F9.

---

## Milestone F11 — Job Detail: Financials (Additional Work & Payment)

**Goal:** additional work flagging/approval and payment tracking, as sections within Job Detail.

**Components implemented:**
- Additional work section: technician can flag (description + price); owner/dispatcher see approve/reject/bill controls matching the backend's state machine (`pending → approved → billed`, or `pending → rejected`)
- Payment section: amount/method/status form (upsert — same form handles both first-set and update, matching the backend's `PUT` semantics)

**Dependencies:** F9.

**API endpoints consumed:** `POST/GET/PATCH /api/v1/jobs/{id}/additional-work[/{item_id}]`, `GET/PUT /api/v1/jobs/{id}/payment`.

**Business logic:** additional work action buttons shown are derived from current status + role (technician: flag only; owner/dispatcher: approve/reject/bill, never flag-then-immediately-approve-in-one-click — these stay separate actions matching the backend's separate endpoints).

**Testing checklist:**
- [ ] Technician can flag additional work on their own job; cannot approve/reject/bill (controls not shown, and a direct attempt would 403)
- [ ] Owner/dispatcher approve/reject/bill flow matches the backend's allowed transitions exactly
- [ ] Payment form correctly creates on first save, updates on subsequent saves (same UI, no separate "create" vs "edit" mode needed)
- [ ] `paid_at` auto-population (when marking paid without an explicit date) is reflected after save
- [ ] Technician has no access to the payment section at all (matching backend's full block, unlike additional-work's partial access)

**Complexity:** Medium
**Estimated time:** 1.25 days
**Risks:** Low-Medium.
**Prerequisites:** F9.

---

## Milestone F12 — Job Detail: Documents

**Goal:** trigger document generation and view/download generated PDFs, as a section within Job Detail.

**Components implemented:**
- Documents section: "Generate Report" / "Generate Certificate" buttons, list of previously generated documents with download links
- Since generation is backend-async (`BackgroundTasks`), the UI needs a pending → ready state — poll `GET /api/v1/jobs/{id}/documents` briefly after triggering, or simply prompt the user to refresh/re-check rather than building a complex polling UI for what's typically a sub-second operation

**Dependencies:** F9.

**API endpoints consumed:** `POST /api/v1/jobs/{id}/documents`, `GET /api/v1/jobs/{id}/documents`.

**Testing checklist:**
- [ ] Triggering generation shows a clear pending state and the document appears in the list shortly after (without a full page reload)
- [ ] Download link opens/downloads the actual PDF
- [ ] Multiple documents (report + certificate) both list correctly
- [ ] Technician has access on their own job; blocked on others, per established pattern

**Complexity:** Low-Medium
**Estimated time:** 0.75 day
**Risks:** Low.
**Prerequisites:** F9.

---

## Milestone F13 — Technician Mobile View

**Goal:** a simplified, mobile-first view for technicians — their job list and the field-capture form, optimized for a phone in the field rather than a repurposed desktop layout.

**Components implemented:**
- A technician-specific simplified job list (reuses F7's data fetching, different layout — larger tap targets, less information density)
- A streamlined version of F9/F10's job detail + field capture, dropping anything technicians can't act on anyway (financials, generation controls) rather than showing disabled versions of them

**Dependencies:** F7, F9, F10.

**API endpoints consumed:** same as F7/F9/F10 — no new endpoints, this is a UI-layer milestone.

**Business logic:** this is presentation, not new permissions logic — everything shown/hidden here should already be enforced by the backend; the mobile view just doesn't clutter the screen with controls a technician could never use anyway.

**Testing checklist:**
- [ ] Technician's mobile view is usable one-handed on a real phone-width viewport (test at actual mobile widths, not just resizing a desktop browser)
- [ ] Photo upload works smoothly from a mobile camera/gallery picker
- [ ] No desktop-only controls (financials, dashboard, customer management) leak into this view

**Complexity:** Medium
**Estimated time:** 1.25 days
**Risks:** Low-Medium — mostly a design/UX risk (does it actually feel good on a phone) rather than a technical one.
**Prerequisites:** F7, F9, F10.

---

## Milestone F14 — Calendar / Schedule View

**Goal:** a simple day/week list of scheduled jobs, per the Product Definition's "basic — day/week list" scope (explicitly not a full calendar widget).

**Components implemented:**
- `app/(authenticated)/schedule/page.tsx` — day/week toggle, list of jobs grouped by `scheduled_at`

**Dependencies:** F7.

**API endpoints consumed:** `GET /api/v1/jobs` (filtered by date range — reuses F7's existing filter support).

**Testing checklist:**
- [ ] Day and week views both render correctly grouped by scheduled date
- [ ] Clicking a job navigates to its detail page
- [ ] Jobs without a `scheduled_at` are handled sensibly (e.g., a separate "unscheduled" section), not silently dropped

**Complexity:** Low
**Estimated time:** 0.75 day
**Risks:** Low.
**Prerequisites:** F7.

---

## Milestone F15 — Settings

**Goal:** organization info display and user management, per the Product Definition's Settings screen.

**Components implemented:**
- `app/(authenticated)/settings/page.tsx` — org name/info (read-only for MVP unless the backend adds an update endpoint — check before building an edit form that has nowhere to submit to)
- User management: list, create, edit role/active-status, deactivate — full CRUD matching the backend's `/api/v1/users` from Milestone 5. `PATCH /users/{id}` later gained an optional `password` field, exposed as an owner-only "reset password" control next to role/active-status, for the case where a teammate forgets theirs and isn't logged in anywhere to use the self-service `/profile` flow.

**Dependencies:** F3.

**API endpoints consumed:** `GET /api/v1/auth/me` (org info), `GET/POST/PATCH/DELETE /api/v1/users[/{id}]`.

**Business logic:** mirror the backend's own business rules in the UI so errors are rare, not just handled: don't show a role-change control on the current user's own row (matches backend's "can't change own role"), don't show a deactivate control on the sole remaining active owner if detectable client-side (the backend is the real guard either way).

**Testing checklist:**
- [ ] User list renders with correct role badges
- [ ] Create/edit/deactivate all work and match backend responses
- [ ] Attempting to change your own role or deactivate the last owner is either prevented in the UI or shows the backend's clear error message
- [ ] Technician and dispatcher see appropriately restricted views (dispatcher: view-only per backend Milestone 5 role table; technician: no access at all)

**Complexity:** Medium
**Estimated time:** 1 day
**Risks:** Low-Medium.
**Prerequisites:** F3.

---

## Milestone F16 — AI Features (Optional, Gated)

**Goal:** surface the optional AI layer in the UI — only if `AI_ENABLED=true` on the backend the frontend is pointed at.

**Components implemented:**
- Feature-detect: check whether `/api/v1/ai/*` routes exist (a lightweight probe, or a config flag mirrored on the frontend) before rendering any AI UI at all — matching the backend's own "fully optional" requirement
- Voice-note-to-structured-note input (text transcript in, per the backend's Milestone 18 scope note — no in-browser audio transcription, that's out of scope)
- "Suggest additional work" button on the Job Detail additional-work section — shows the AI suggestion as a pre-filled draft in the existing flag-additional-work form, never auto-submits it
- Job summary generation, natural-language query screen — simple text-in/text-out with the async pending→done polling pattern from F12

**Dependencies:** F11 (additional-work UI to attach suggestions to), F9.

**API endpoints consumed:** `POST /api/v1/ai/voice-note`, `POST /api/v1/ai/jobs/{id}/summary`, `POST /api/v1/ai/jobs/{id}/suggest-additional-work`, `POST /api/v1/ai/query`, `GET /api/v1/ai/tasks/{id}`.

**Business logic:** hard rule carried over from the backend — no AI output is ever auto-submitted as job/additional-work/payment state. Every AI result lands as a pre-filled draft in an existing manual form, requiring an explicit human submit action.

**Testing checklist:**
- [ ] With AI disabled on the backend, no AI UI renders anywhere (not just hidden — actually absent, matching the backend's "routes don't even register" behavior)
- [ ] Suggested additional work pre-fills the existing form but requires manual submit — verify no auto-creation happens
- [ ] Async task polling (pending → done/failed) shows appropriate loading/error states
- [ ] A failed AI task shows a clear error, not a silent hang

**Complexity:** Medium
**Estimated time:** 1.25 days
**Risks:** Low-Medium — main risk is UI implying more autonomy than the backend actually allows; keep language and interaction patterns consistently "suggestion, not action."
**Prerequisites:** F9, F11.

---

## Milestone F17 — Final Polish & Hardening

**Goal:** production-readiness pass — the frontend equivalent of the backend's Milestone 19.

**Components implemented:**
- Consistent loading states (skeletons/spinners) across every data-fetching screen — audit for any screen still showing a blank flash
- Consistent error boundaries — a failed API call anywhere shows a recoverable error state, not a blank page or an unhandled exception
- Responsive QA pass across all screens at common breakpoints (not just the mobile view from F13, which was purpose-built — this is everything else)
- Basic accessibility pass (form labels, focus states, keyboard navigation on interactive elements)
- Environment/deploy configuration finalized (production API URL, build verified)

**Dependencies:** all previous milestones.

**Testing checklist:**
- [ ] Every screen has a loading state and an error state — walked through manually, not assumed
- [ ] A simulated backend failure (e.g., point at a wrong port) doesn't crash any screen
- [ ] All screens usable at common breakpoints (mobile/tablet/desktop)
- [ ] Keyboard-only navigation works for primary flows (login, create job, approve additional work)
- [ ] Production build (`next build`) succeeds with no warnings treated as acceptable-to-ignore

**Complexity:** Medium
**Estimated time:** 1.5 days
**Risks:** Low-Medium — mostly about discipline in actually walking every screen.
**Prerequisites:** all previous milestones.

---

## Summary Table

| # | Milestone | Complexity | Est. Time | Prerequisites |
|---|---|---|---|---|
| F0 | Project Bootstrap | Low | 0.5 day | — |
| F1 | API Client & Types | Medium | 1 day | F0 |
| F2 | Authentication | Medium-High | 1.5 days | F1 |
| F3 | App Shell & Navigation | Low-Medium | 0.75 day | F2 |
| F4 | Dashboard | Medium | 1 day | F3 |
| F5 | Customers | Low-Medium | 1 day | F3 |
| F6 | Equipment | Low | 0.75 day | F5 |
| F7 | Jobs List | Medium | 1 day | F3 |
| F8 | New Job Form | Medium | 1 day | F5, F6, F7 |
| F9 | Job Detail: Core | Medium-High | 1.5 days | F7 |
| F10 | Job Detail: Field Data | Medium-High | 1.5 days | F9 |
| F11 | Job Detail: Financials | Medium | 1.25 days | F9 |
| F12 | Job Detail: Documents | Low-Medium | 0.75 day | F9 |
| F13 | Technician Mobile View | Medium | 1.25 days | F7, F9, F10 |
| F14 | Calendar/Schedule | Low | 0.75 day | F7 |
| F15 | Settings | Medium | 1 day | F3 |
| F16 | AI Features | Medium | 1.25 days | F9, F11 |
| F17 | Final Polish & Hardening | Medium | 1.5 days | all |

**Total estimated time:** ~18–19 days of focused solo work.

---

## Recommended Order

The table order is the recommended order — F0–F3 (bootstrap, API client, auth, shell) are a hard sequential foundation. F4–F8 (dashboard, customers, equipment, jobs list, new job form) can flex slightly in order but each has real prerequisites as listed. F9–F12 (Job Detail's four sub-sections) are the biggest chunk of total effort and are deliberately split into four milestones rather than one large one — the roadmap discipline established on the backend (small, independently testable pieces) applies here too.

**Which milestone first:** F0, no ambiguity.

**MVP-usable checkpoint:** **F12** (end of Job Detail). By that point every core workflow from the Product Definition has a working UI: login, dashboard, customer/equipment management, job creation, the full job lifecycle (status/assign/timeline), field capture (photos/materials), financials (additional work/payment), and documents. F13–F17 make it genuinely pleasant and production-ready (mobile UX, schedule view, settings, AI, polish) but F0–F12 is the point at which a pilot user could actually use the product end to end on a desktop browser.

**Safe to postpone if time runs out** (safest first):
1. **F16 (AI Features)** — same reasoning as the backend: explicitly optional, cut first.
2. **F14 (Calendar/Schedule)** — the Jobs List (F7) with date filtering already covers most of the same need; the dedicated calendar view is a convenience, not a blocker.
3. **F13 (Technician Mobile View)** — technicians can use the same desktop-oriented UI on mobile in a pinch (it should still be minimally responsive from F3's baseline); the purpose-built mobile experience is a quality improvement, not a hard requirement for a first pilot.
4. **F17 partially** — the loading/error-state audit matters more than the accessibility pass if forced to choose; don't cut the whole milestone, but the accessibility item is the most deferrable single line item in it.

**Never cut:** F0–F12. That's the operational backbone the entire Product Definition is built around, on the frontend exactly as on the backend.

---

## Post-Roadmap Additions

Shipped after F0–F17, in response to direct user feedback rather than as pre-planned milestones. Recorded here so this document stays a reliable map of what exists, not just what was originally planned:

- **Localization (English/Russian toggle).** A full `t()`/`useLocale()` layer under `frontend/lib/i18n/` (`context.tsx`, `en.ts` source-of-truth dictionary, `ru.ts` mirror) covers every page and component — not just the Cyrillic-ready typography the Product Definition called for, but a real runtime-switchable UI language. A `LocaleToggle` sits beside the profile menu on every authenticated screen; locale persists per browser and is detected from `navigator.language` on first visit.
- **Self-service Profile (`/profile`).** A user editing their own name, email, phone, password (current-password-gated), and avatar (presigned-upload flow, same shape as job photos). Backend: `User` gained `phone`/`avatar_s3_key` columns; `PATCH /auth/me`, `POST /auth/me/password`, and the `/auth/me/avatar` upload-url/confirm/delete trio were added, distinct from the owner-only `/users/{id}` management in F15.
- **Owner password reset.** `PATCH /users/{id}` (F15's user management) gained an optional `password` field so an owner can reset a teammate's forgotten password directly.
- **Job history on Customer/Equipment Detail.** `GET /jobs` gained `customer_id`/`equipment_id` filters specifically to fill in what F5/F6 originally stubbed; both detail pages now render a real, clickable job list via a shared `JobHistoryList` component.
- **Design system.** The frontend now runs a custom "Studio Console" design system (see `DESIGN.md`) rather than default shadcn tokens — this postdates F0–F17, which didn't specify a visual identity beyond "shadcn/ui."

## Open Decisions to Confirm Before Starting

1. **Token storage strategy (F2)** — httpOnly cookie via a Next.js route handler (recommended) vs. in-memory. This shapes every later milestone's auth handling; decide once, explicitly, rather than defaulting to whatever's fastest to type in the moment.
2. **Testing tooling** — this roadmap's checklists assume manual verification plus component-level tests are welcome but not mandated per milestone (unlike the backend, where every milestone had a hard pytest gate). Decide whether to require Vitest + React Testing Library coverage per milestone (slower, more roadmap-like parity with the backend) or treat automated frontend tests as a stretch goal layered on top of manual QA (faster, more typical for early-stage frontend work). Recommend the latter for MVP speed, revisited once the product has real users.
3. **Deployment target** — Vercel (simplest for Next.js) vs. same infrastructure as the backend (Railway/Render/Yandex Cloud/VM). Not blocking for early milestones, but worth deciding before F17.
