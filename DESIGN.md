---
name: Service Center Platform
description: Studio Console — a soft sage workspace with a floating icon rail and one bright accent, applied across the whole product.
colors:
  studio-sage: "oklch(0.91 0.015 155)"
  studio-card: "oklch(0.985 0.004 150)"
  studio-ink: "oklch(0.18 0.01 150)"
  studio-muted-ink: "oklch(0.5 0.012 150)"
  studio-border: "oklch(0.85 0.012 150)"
  studio-accent: "#04ca8b"
  studio-rail: "oklch(0.14 0.008 150)"
  status-delayed: "oklch(0.6 0.19 25)"
  status-pending: "oklch(0.72 0.15 80)"
  status-completed: "oklch(0.48 0.11 155)"
typography:
  label:
    fontFamily: "Oswald, 'Arial Narrow', sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.12em"
  heading:
    fontFamily: "Golos Text, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Golos Text, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  data:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
rounded:
  sm: "8px"
  md: "10px"
  lg: "13px"
  xl: "13px"
  2xl: "13px"
  full: "9999px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  card:
    backgroundColor: "{colors.studio-card}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.2xl}"
    padding: "16px 20px"
  metric-card-accent:
    backgroundColor: "{colors.studio-accent}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.2xl}"
    padding: "20px"
  button-primary:
    backgroundColor: "{colors.studio-accent}"
    textColor: "{colors.studio-ink}"
    rounded: "{rounded.full}"
    padding: "8px 14px"
---

# Design System: Service Center Platform

## Overview

**Creative North Star: "Studio Console"**

A soft, confident workspace: a sage-tinted page ground, a floating black icon-only rail, near-white rounded cards, and exactly one bright accent color (`#04CA8B`, the user's own pick) doing all the pointing. Started as a dashboard-only experiment, then promoted to the whole product once the user confirmed the direction ("ок мне в целом нравится. давай теперь в этом стиле все остальные вкладки") — every authenticated screen now shares one token system and one shell.

**Direction history**, all user-pinned via reference images rather than the concept-seed roll: v1 "Equipment Inspection Tag" (kraft, stamped bands, grommets) → v2 "Night Ops Console" (dark, glowing, glass — rejected by the user as "too template-y," a fair critique: dark-glass-glow is itself a saturated AI-dashboard cliché) → **v3 "Studio Console" (current)**, translated from a light SaaS admin reference (sage ground, floating icon rail, bold type, one bright accent, rounded two-tone cards, a percentage ring, a "lollipop" dot-and-stem chart) with the reference's yellow swapped for the user's `#04CA8B`. v3 shipped on the dashboard first, then was promoted to `:root` and the shared `AppShell` app-wide in the same session once approved. A later refinement pass flattened the radius scale (see Shapes) and moved the profile/locale controls from the bottom of the icon rail to a fixed top-right group, after the user flagged the original 24px-scaling corners as "loaded."

**Key Characteristics:**
- One accent, spent deliberately: `#04CA8B` carries every primary button, focus ring, active-nav state, and exactly one "hero" metric card per screen — never scattered across several cards at once.
- Modest, consistent rounding: a single flattened radius (~13px, `--radius: 13px` in `globals.css`) covers every "card-sized" surface — `rounded-lg` through `rounded-4xl` all resolve to the same base rather than scaling up per Tailwind step, correcting an earlier pass where the old `*1.4/*1.8/*2.2/*2.6` multiplier scale had ballooned `rounded-3xl` to ~39px and read as "loaded" corners. Only `sm`/`md` (chips, small controls) stay a touch tighter than the base. Every button and the icon rail remain fully circular (`rounded-full`), unaffected by this scale.
- Two data-honesty decisions define the translation from reference to product, worth preserving as the reasoning to reapply on future surfaces: (1) the reference's segmented "quota" progress meters were **not** replicated on plain counts with no natural "out of N" ceiling — a percentage ring appears only where a genuine percentage exists (repeat-customer rate). (2) The reference's day-by-day bar chart became a **technician-by-technician** lollipop chart, since this product has no daily-granularity data but does have real comparable per-technician revenue.
- One shared type system: Golos Text for body copy and page headings (Cyrillic-native — the product's target market is Russia/CIS), Oswald tracked caps reserved for small metric/form labels, JetBrains Mono strictly for tabular data.
- Full English/Russian localization, not just a Cyrillic-ready type system: a locale toggle (`components/shell/locale-toggle.tsx`) sits beside the profile menu in the top-right control group on every authenticated screen, backed by a custom `t()`/`useLocale()` layer (`lib/i18n/`) covering every page and component.

## Colors

Warm-neutral sage carries the surface; the one accent is spent with intent, never as ambient decoration.

### Primary
- **Studio Accent** (`#04ca8b`): the only saturated color besides status semantics. Primary buttons, focus rings, active nav state, and exactly one hero metric card per screen (the One-Hero-Card Rule). The exact value the user specified — never approximated.

### Neutral
- **Studio Sage** (`oklch(0.91 0.015 155)`): page background — a soft, warm-green-tinted off-white.
- **Studio Card** (`oklch(0.985 0.004 150)`): card/table surface — near-white.
- **Studio Ink** (`oklch(0.18 0.01 150)`): primary text, on both light cards and the accent card (the accent is light enough that dark text reads better than white).
- **Studio Muted Ink** (`oklch(0.5 0.012 150)`): secondary text, labels, placeholders.
- **Studio Border** (`oklch(0.85 0.012 150)`): the few remaining borders — table header rules, dashed dividers, input strokes. Filled cards themselves carry no border; separation comes from the sage/card contrast.
- **Studio Rail** (`oklch(0.14 0.008 150)`): the floating icon-rail sidebar surface, and the mobile drawer.

### Status (semantic — never a general UI accent)
- **Delayed** (`oklch(0.6 0.19 25)`): overdue/cancelled jobs.
- **Pending** (`oklch(0.72 0.15 80)`): additional-work pending approval.
- **Active** — **is** the Studio Accent: "in progress/nominal" and "the thing worth highlighting" are the same idea in this system.
- **Completed** (`oklch(0.48 0.11 155)`): a deeper forest green, kept visually distinct from the brighter accent.

### Named Rules
**The Hue-Is-Meaning Rule.** Outside the one accent, hue never decorates — it only appears as a job-state signal. A fifth accent color breaks the system.
**The One-Hero-Card Rule.** The bright accent fills exactly one metric card per screen — the single most important number (Active jobs on the dashboard). A second accent-filled card in the same view means the hierarchy decision wasn't made.
**The Honest-Ceiling Rule.** A circular percentage ring or segmented "quota" meter is only ever used on a value with a real, data-backed ceiling. Never invent one to borrow a reference's visual device.

## Typography

**Body/Heading Font:** Golos Text (with system-ui, sans-serif fallback) — Cyrillic-native, functional for the Russia/CIS market, used for both prose and page-level `<h1>` headings (bold, ~1.875rem, tight tracking — a plain confident voice, not tracked caps).
**Label Font:** Oswald (with Arial Narrow, sans-serif fallback) — reserved for small tracked-caps labels inside metric tiles and instrument readouts (11px, 0.12em tracking, uppercase).
**Data/Mono Font:** JetBrains Mono (with ui-monospace, monospace fallback) — tabular figures only.

### Hierarchy
- **Page Title:** Golos Text, 600, `text-3xl`, tight tracking. Every list/detail page (`Jobs`, `Customers`, `Schedule`, `Settings`, the dashboard) opens with one of these.
- **Card Title** (`CardTitle`, shared shadcn primitive): Golos Text, medium weight, `text-base` — section headers inside a `Card` (e.g. "Organization", "Users").
- **Metric Label** (Oswald, 500, 11px/1.2, 0.12em tracking, uppercase): labels inside `InstrumentReadout`/`MetricCard`.
- **Body** (Golos Text, 400, 0.875rem/1.5): all prose, descriptions, table content.
- **Data** (JetBrains Mono, 600, tabular-nums): the only place numerals are set in mono — card values, table figures where they're read as records, lollipop badges, date inputs.

### Named Rules
**The Data-Only-Mono Rule.** JetBrains Mono is reserved for figures read as a measurement or record. Never on prose or labels.

## Layout

A floating, icon-only pill rail (`w-16`, `rounded-full`, margined `inset-y-4 left-4`, dark `bg-sidebar`) replaces the old labeled sidebar on every authenticated route — no header bar at all; content runs full-bleed with `md:pl-24` to clear the rail. Below `md`, the rail becomes a floating rounded hamburger button that opens the exact same labeled `SidebarNav` list in a `Sheet` drawer — icon-only nav is a desktop-only device; the drawer keeps full discoverability on mobile, and every rail icon still carries `title`/`aria-label` text matching its drawer label.

The profile menu (`UserMenu`) and locale toggle live together in a fixed `top-4 right-4` group on desktop — not inside the rail — so `main`'s top padding (`md:pt-20`) leaves clearance for them above each page's own top-right content (a "New job" button, a date-range filter). On mobile, the same pair repeats as an ordinary in-flow row (`md:hidden`) at the top of `main`, since there's no fixed rail to anchor them to.

Page content: `mx-auto max-w-6xl flex flex-col gap-4` (list/detail pages) or `gap-6` (dashboard). List pages open with a bold page title, then filters, then a `bg-card` table or card grid at the base card radius — no border, separation comes from the sage/card contrast. Dashboard: summary cards `grid-cols-2 lg:grid-cols-4`, instrument grid `md:grid-cols-2 lg:grid-cols-3` with the revenue-per-technician readout spanning two columns.

## Elevation & Depth

Flat by design — no shadows, no glow anywhere in this system. Depth and hierarchy come entirely from color contrast (the one accent card against neutral ones, cards against the sage ground) and the floating rail's separation from the page, never from elevation effects. This is a deliberate correction from the rejected v2 direction, whose glow-as-elevation language was part of what read as "template-y."

### Named Rules
**The No-Shadow Rule.** Hierarchy is carried through color and shape, never drop shadows or glow. Reaching for a shadow here is reaching for the rejected v2 direction's device.

## Shapes

A single, modest card radius (~13px, `--radius` in `globals.css`) covers every card-sized surface — cards, tables, list items. This is deliberately flattened rather than scaled: `--radius-lg` through `--radius-4xl` all resolve to the same base value instead of ballooning with each Tailwind step (the retired scale put `rounded-3xl` at ~39px, which read as "loaded," not confident). `sm`/`md` (chips, small controls) stay a touch tighter at 60%/80% of the base. Every button and the icon rail are fully circular (`rounded-full`); this is the shared `Button` primitive's actual base radius now, not a per-instance override. Dashed rules (`border-dashed`) mark the one remaining divider device: the baseline under an `InstrumentReadout`'s label, and row dividers in the revenue-per-technician list.

## Components

### Buttons
Fully `rounded-full` at every size (the shared `ui/button.tsx` primitive's base radius, not a per-instance class). Primary: Studio Accent background, Studio Ink text, `hover:bg-primary/80`. Destructive (Archive/Deactivate actions): tinted red, `bg-destructive/10 text-destructive`.

### Card (shared shadcn primitive)
Base card radius (via the shared `--radius` token, not a component edit), `bg-card`, no visible border in most usages — pages needing internal separation nest a `bg-background` (sage) well inside the card instead of adding a border.

### Metric Card (`components/dashboard/metric-card.tsx`)
The dashboard's four-card summary row. A small icon badge sits beside the label; a large `JetBrains Mono` number sits below. Exactly one card per screen (Active jobs) takes the `accent` variant — solid Studio Accent fill, dark text; the rest are neutral.

### Percent Ring (`components/dashboard/percent-ring.tsx`)
A plain SVG circular progress ring (track + accent arc), used only for Repeat-customer rate — the one dashboard metric that is a genuine percentage. See the Honest-Ceiling Rule.

### Lollipop Chart (`components/dashboard/lollipop-chart.tsx`)
Revenue per technician as a thin vertical stem topped by an accent-colored knob, height scaled to each technician's revenue relative to the group's max, with a value badge floating above the knob.

### Instrument Readout (`components/dashboard/instrument-readout.tsx`)
Metric tile with a dashed baseline under the label. Built entirely from semantic tokens, so it needs no register-specific code.

### Job/Additional-Work Status Badges (`components/jobs/job-status-badge.tsx`, `job-additional-work.tsx`)
Small `rounded-full` pills, one hue per status. Job statuses use a wider category palette (8 distinct statuses need more hues than the 4-way status system carries) layered on top of the shared tokens where they overlap (`in_progress` uses the accent tint, `completed`/`cancelled` use the status-completed/status-delayed tokens); no dark-mode pairs, since the product has no dark-mode toggle.

### Navigation
Floating icon-only pill rail everywhere (see Layout). Active icon = solid accent-filled circle; inactive = 60%-opacity icon brightening on hover. Mobile: identical labeled list in a `Sheet` drawer, triggered by a floating rounded hamburger button.

### Avatar (`UserMenu`, `app/(authenticated)/profile/page.tsx`)
A circular, accent-filled initials badge (first + last name initial, monospace) doubles as the photo slot once a user uploads one — same circle, `object-cover` image instead of text. On the profile page, the large version is itself the upload trigger: hovering reveals a dark overlay with "Change photo" text: no separate button needed. Falls back to initials everywhere an avatar hasn't been set, never a placeholder icon.

## Do's and Don'ts

### Do:
- **Do** reserve the status colors strictly for job/work-item state; never repurpose one as a generic accent.
- **Do** keep JetBrains Mono limited to figures read as data.
- **Do** spend the bright accent on exactly one hero card per screen (the One-Hero-Card Rule).
- **Do** use a percentage ring only for a value with a real percentage backing it (the Honest-Ceiling Rule).
- **Do** give every icon-only nav item a `title`/`aria-label` matching its labeled drawer counterpart.
- **Do** open every list/detail page with a bold `text-3xl` page title before any filters or content.

### Don't:
- **Don't** add a fifth accent color anywhere.
- **Don't** reach for a shadow or glow — that's the rejected v2 direction's language (the No-Shadow Rule).
- **Don't** chart Active/Delayed/Completed/Unbilled as parts of one proportional whole — they aren't mutually exclusive categories.
- **Don't** stack a CSS transform on top of `bottom`/`top` positioning without checking the combined offset — the lollipop chart's first draft double-shifted its value badge this way, clipping the tallest column's badge outside its container.
- **Don't** let a rounding scale multiply per Tailwind step (`*1.4`, `*1.8`, ...) — it silently balloons the largest radius far past what "generous rounding" was meant to mean. Flatten `lg` through `4xl` onto one base value instead.
- **Don't** add a border to a filled card for internal separation — nest a `bg-background` well instead.
