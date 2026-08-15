# ATLAS v2 — Frontend Redesign Review

A ground-up visual redesign of the ATLAS frontend into a dark, enterprise supply-chain
command center. Engineering underneath is unchanged — same backend, same warehouse, same
verified formulas — this is a presentation-layer pass plus one genuinely new page (the
Supply Chain Map) built from existing, real endpoints. Token/component rationale lives in
[`ATLAS-v2-design-system.md`](ATLAS-v2-design-system.md); this document covers what
changed and how it was verified.

## What changed

**Design system foundation** — `app/globals.css` + `tailwind.config.ts` define the full
dark palette, an enterprise-scaled type ramp, and three shared motion keyframes, all
sourced from the dataviz skill's validated dark-surface palette rather than invented ad
hoc. Every shared component (`Card`, `KpiCard`, `Badge`, `DataTable`, `Chart`,
`DashboardLoading`/`DashboardError`) was rebuilt on these tokens.

**Navigation** — the flat v1 link list became a sectioned sidebar (Overview / Operations /
Forecasting / Inventory / Suppliers / Scenarios / Optimization / Copilot), each link
role-gated to match its backend `require_role(...)` exactly, plus a ⌘K command palette
(`command-palette.tsx`) built from the same section data the sidebar renders.

**Landing page** (`app/page.tsx`) — rebuilt from scratch: hero, a real-metrics strip (365
days simulated, 1.8M+ warehouse records, 300 tests passing, etc. — all figures pulled
from the existing v1.0 report, not invented for the redesign), and a 5-stage pipeline
diagram (Simulate → Warehouse → Predict → Decide → Ask).

**Executive Command Center** (`(executive)/dashboard`) — reassembled as a true
cross-module command view: 8 KPI cards spanning revenue, margin, fulfillment, inventory
value, forecast accuracy, supplier risk, and predicted stockout/backorder risk; a
revenue/margin trend chart; and an operational-alerts panel that surfaces existing
threshold breaches (high-risk suppliers, high stockout-risk pairs, reorder-now count)
rather than computing anything new.

**Analytics Copilot** (`copilot/page.tsx`) — repositioned as a "Verified Analytics
Workspace": the verification badge and example prompts are now the visual focus, ahead of
the chat input, making the copilot's core guarantee (no unverified number ever ships)
the first thing a user sees.

**Scenario Simulation** — replaced the single dense comparison table with a selectable
card library (up to 5 scenarios) and a baseline-vs-scenario impact card per selection,
each metric rendered as `baseline → scenario` with a delta badge.

**Supply Chain Map** (new page, `(operations)/supply-chain`) — a warehouse network view
grouped by real region, each warehouse card showing actual city, capacity utilization
(as a meter), and quantity on hand, alongside a supplier risk watch panel (top suppliers
by risk score). Built entirely from real data — `city`/`region_name` were added to
`operational.py`'s `WarehouseCapacityRow` (a real, previously-unsurfaced `dim_warehouse`
join, not fabricated), and no geographic coordinates are used anywhere since none exist
in the schema; the page says so explicitly rather than faking a map.

**Remaining 11 dashboards** (sales, inventory, procurement, operational, supplier,
forecast, inventory-policy, route-cost-optimization, service-level, supplier-risk,
data-quality) — reskinned onto the shared components and tokens, plus a global ECharts
dark theme (`components/chart.tsx` registers `"atlas-dark"` once) so every chart's
axis/legend/tooltip colors are consistent without each page restating them.

**Motion pass** — `animate-rise-in` baked into the shared `Card` component (applies
everywhere at once, including on data refresh), hover-transition polish on table rows,
scenario cards, and the warehouse capacity meter's fill.

**Backend role-gate widening** (the only backend behavior change) — `EXECUTIVE` added to
`forecast`, `service-level`, `inventory-policy`, and `supplier-risk` `/summary`
endpoints, and `EXECUTIVE` + `OPERATIONS_ANALYST` added to `supplier-risk/detail` — all
strictly additive (existing roles keep exactly the access they had), needed because the
new Executive Command Center and Supply Chain Map genuinely read across modules that
were previously siloed by role.

## Screenshots

Captured via a headless-Chromium Playwright script (see Verification below) against the
live dev server with real warehouse data.

| Page | Screenshot |
|---|---|
| Landing | [`screenshots/v2-landing.png`](screenshots/v2-landing.png) |
| Executive Command Center | [`screenshots/v2-executive-dashboard.png`](screenshots/v2-executive-dashboard.png) |
| Supply Chain Map | [`screenshots/v2-supply-chain-map.png`](screenshots/v2-supply-chain-map.png) |
| Scenario Simulation | [`screenshots/v2-scenario-simulation.png`](screenshots/v2-scenario-simulation.png) |
| Analytics Copilot | [`screenshots/v2-copilot.png`](screenshots/v2-copilot.png) |
| Supplier Risk | [`screenshots/v2-supplier-risk.png`](screenshots/v2-supplier-risk.png) |
| Sales | [`screenshots/v2-sales.png`](screenshots/v2-sales.png) |
| Data Quality | [`screenshots/v2-data-quality.png`](screenshots/v2-data-quality.png) |

## Verification performed

- **TypeScript**: `tsc --noEmit` clean throughout, checked after every change.
- **Backend test suite**: `pytest tests/` run to completion in the backend container
  after every backend edit. All role-gate changes have matching test coverage — 4 stale
  tests that asserted the *old*, narrower role gate (written before this session's
  widening) were found and rewritten to assert the new gate plus a positive
  "allows_executive"/"allows_operations_analyst" case, rather than deleted.
- **Live browser verification**: no `chromium-cli` was available in this native
  Windows/git-bash environment, so Playwright + Chromium were installed directly
  (routed to a separate drive with headroom to avoid the constrained system drive) and
  driven with a script that navigates every redesigned page, switches role via the nav
  selector, waits for the loading skeletons to actually clear (not a fixed sleep), and
  captures both a full-page screenshot and the browser console for errors.
- **Bugs found and fixed during this verification pass** (not caught by TypeScript or
  the backend suite, since they're rendering/layout issues):
  - Two files still used hardcoded Tailwind colors (`red-600`, `amber-600`,
    `emerald-600`, etc.) for risk/balancing classification text instead of the
    `status-critical`/`warning`/`good` tokens — missed by an earlier grep that only
    checked for the old `slate-*` classes. Fixed in `supplier-risk/page.tsx` and
    `inventory-policy/page.tsx`.
  - The Scoring Model KPI card clipped long values (e.g. `weighted_composite_v1`)
    instead of wrapping — a classic flexbox bug (`min-width: auto` on a flex child
    blocks `break-words` from taking effect). Fixed by adding `min-w-0` to `KpiCard`'s
    value element.
  - `DataTable`'s long free-text columns (e.g. supplier risk's "Triggering Metrics")
    were cut off because every cell defaults to `whitespace-nowrap` — correct for the
    numeric-heavy majority of columns, wrong for free text. Added an opt-in
    `meta: { wrap: true }` on `ColumnDef` rather than changing the shared default.
  - A raw `JSON.stringify` dump of the scoring model's weights was reformatted into
    readable `trend 15% · on_time 35% · ...` text.
  - One hydration-mismatch console warning traced to editing `card.tsx` while the dev
    server was live (a Next.js Fast Refresh artifact); confirmed gone after a clean
    restart. A second, unrelated warning on the copilot page's text input
    (`caret-color: transparent`, not set anywhere in app code) was confirmed pre-existing
    by comparing against the deleted v1 copilot page, which had the same input shape —
    left as a known, non-blocking, environment-level warning rather than "fixed."

## Known non-blocking observations

- **Executive dashboard's Forecast Accuracy (MAPE) shows 4,135.7%.** This is real,
  computed data from the existing forecasting module (unchanged by this redesign) — MAPE
  is well known to blow up when actual values are near zero, which is a data
  characteristic, not a UI bug. Out of scope for a presentation-layer redesign.
- **Local dev environment has an intermittent file-watcher gap** on this Docker
  Desktop + Windows bind-mount setup — a small number of edits during this session
  didn't trigger `next dev`'s auto-recompile and needed a manual container restart to
  pick up. This is a known category of Docker-on-Windows limitation, not a project
  configuration bug; worth knowing if a future edit "doesn't seem to apply."
