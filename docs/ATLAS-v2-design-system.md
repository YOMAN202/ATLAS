# ATLAS v2 Design System

Reference for the dark enterprise command-center visual language introduced in the v2
frontend redesign. Source of truth for the tokens is `frontend/app/globals.css`
(`:root` custom properties) and `frontend/tailwind.config.ts` (Tailwind role names layered
on top) — this document explains the *why* behind those values; the files themselves are
the values.

## Philosophy

ATLAS v2 is **dark-only by design** — not a light theme with a toggle, but one considered
identity for a supply-chain command center that's meant to be watched on a large monitor for
long stretches. The palette is the dataviz skill's validated dark-surface palette (base
surface `#1a1a19`), reused unchanged rather than re-derived, with the page plane pushed
darker still (`#0a0a0b`) for the graphite/near-black depth an operations-room product calls
for.

Two things the redesign was built to protect, inherited from the v1 platform and never
loosened for aesthetics:

- **Every number is real.** No dashboard fabricates or interpolates data — colors and
  motion exist to make real, already-verified numbers easier to read, never to imply
  precision that isn't there.
- **The copilot's verification badge stays the loudest thing on its page.** Redesigning
  `/copilot` as a "Verified Analytics Workspace" made this explicit rather than incidental.

## Color tokens

All colors are RGB triplets (not hex) in `:root`, so Tailwind's `<alpha-value>` opacity
modifier works on every token (`bg-surface/60`, `text-status-critical/80`, etc.).

| Role | Token | Value | Used for |
|---|---|---|---|
| Page | `bg-page` | `#0a0a0b` | The outermost background, behind every surface |
| Surface | `bg-surface` | `#1a1a19` | Cards, panels, the base elevation step |
| Surface 2 | `bg-surface-2` | `#232322` | Hover states, secondary chips, skeleton highlight |
| Surface inset | `bg-surface-inset` | `#131313` | Recessed areas — table headers, input fields |
| Ink primary | `text-ink-primary` | `#f5f5f4` | Headlines, primary values |
| Ink secondary | `text-ink-secondary` | `#c3c2b7` | Body text, table cells |
| Ink muted | `text-ink-muted` | `#898781` | Labels, captions, disabled state |
| Hairline | `border-hairline` | `rgba(255,255,255,.08)` | Default card/table borders |
| Hairline strong | `border-hairline-strong` | `rgba(255,255,255,.14)` | Hover-state borders |
| Accent | `bg-accent` / `text-accent` | `#3987e5` | Primary actions, active nav, links |
| Accent subtle | `bg-accent-subtle` | `rgba(57,135,229,.14)` | Selected-state backgrounds |

**Status palette** — reserved exclusively for state (never reused as a categorical series
color), always paired with an icon or label, never color alone:

| Token | Value | Meaning |
|---|---|---|
| `status-good` | `#0ca30c` | On target, low risk, improving |
| `status-warning` | `#fab219` | Needs attention, medium risk |
| `status-serious` | `#ec835a` | Elevated concern (between warning and critical) |
| `status-critical` | `#d03b3b` | Breached threshold, high risk, degrading |

**Chart categorical palette** — `series-1` through `series-8`, fixed order, never cycled
or reassigned when a filter changes the series count (the dataviz skill's non-negotiable
rule: color follows the entity, not its rank):

```
series-1  #3987e5  blue      series-5  #d55181  magenta
series-2  #d95926  orange    series-6  #008300  green
series-3  #199e70  aqua      series-7  #9085e9  violet
series-4  #c98500  yellow    series-8  #e66767  red
```

Chart furniture (axis lines, gridlines, tooltip chrome) uses two dedicated tokens rather
than the ink scale, since they need to recede further than body text: `--chart-gridline
(#2c2c2a)` and `--chart-baseline (#383835)`.

## Typography

An enterprise-command-center scale — wider than Tailwind's default, biased toward large
headline/hero figures with a small, calm body size. Data density needs a restrained body
size to fit; hierarchy comes from a big jump to headline/hero, not a crowded middle.

| Class | Size | Used for |
|---|---|---|
| `text-2xs` | 11px | Table headers, badges, captions |
| `text-xs` / `text-sm` | 12px / 14px | Body text, table cells (Tailwind defaults) |
| `text-headline` | 24px | Page titles |
| `text-display` | 36px | KPI card values |
| `text-hero` | 56px | Landing-page hero only |

Font is Inter (`--font-inter`), with `font-feature-settings: "cv11", "ss01"` set globally
on `body` for the single-story `a` and slashed zero. All numeric values use
`.tabular-nums` (`font-variant-numeric: tabular-nums`) so figures in a column or a
delta don't visually jitter as digits change.

## Motion

Three keyframe animations, all in `tailwind.config.ts`:

- **`animate-rise-in`** (`opacity 0→1` + `translateY(6px→0)`, 0.35s) — baked directly into
  the shared `Card` component (`components/ui/card.tsx`), so *every* card-based surface in
  the app gets a consistent entrance for free, including on data refresh (role switch,
  filter change) — one edit, applied everywhere, rather than repeating the class across
  every page.
- **`animate-fade-in`** (0.3s) — available for non-card elements that need a plain fade.
- **`animate-shimmer`** — the `.skeleton` loading-state class (`app/globals.css`), a
  moving gradient sweep used for every dashboard's pre-data loading state.

Hover transitions (`transition-colors`, `transition-[width]`) are applied per-element
where a state actually changes — table row hover, card border hover, meter-fill width —
rather than a blanket `transition-all` on everything, which tends to animate properties
you didn't intend to.

## Components

| Component | File | Notes |
|---|---|---|
| `Card` / `CardHeader` / `CardTitle` / `CardContent` | `components/ui/card.tsx` | The base surface every panel, KPI, and chart container composes from. Carries `animate-rise-in` and `transition-colors` by default. |
| `KpiCard` | `components/kpi-card.tsx` | Label + big value + optional delta (up/down/flat, with a `positiveIsUp` flag since "up" isn't always good — e.g. backorder rate) + optional note. `min-w-0` + `break-words` on the value so long non-numeric values (model names) wrap instead of overflowing the card. |
| `Badge` | `components/ui/badge.tsx` | Six tones (`neutral`, `accent`, `good`, `warning`, `serious`, `critical`) for inline status chips. |
| `DataTable` | `components/data-table.tsx` | Generic `@tanstack/react-table` wrapper. Cells default to `whitespace-nowrap` (right for the numeric-heavy majority of columns); a column opts into wrapping via `meta: { wrap: true }` in its `ColumnDef` for long free-text columns instead of fighting the default per-cell. |
| `Chart` | `components/chart.tsx` | Thin ECharts wrapper. Registers a shared `"atlas-dark"` ECharts theme once (series colors, axis/legend/tooltip styling) applied via `echarts.init(el, "atlas-dark")` — every chart across the app is styled consistently from one place rather than restating axis/legend colors in each page's chart option. |
| `DashboardLoading` / `DashboardError` | `components/dashboard-status.tsx` | Shared loading skeleton (4-card grid) and error states (403 → role-switch hint, 503 → no-ETL-run hint, generic → message). |
| `Nav` | `components/nav.tsx` | Sectioned sidebar (Overview / Operations / Forecasting / Inventory / Suppliers / Scenarios / Optimization / Copilot), each link role-gated to match its backend `require_role(...)`, plus the role switcher and a "Jump to…" trigger for the command palette. |
| `CommandPalette` | `components/command-palette.tsx` | ⌘K fuzzy-navigable list of every nav-visible route, built from the same `SECTIONS` array `Nav` renders — no separate route list to keep in sync. |

## Adding a new page

1. Compose from `Card`/`CardHeader`/`CardTitle`/`CardContent` and `KpiCard` — don't
   reach for raw `<div>` + Tailwind color utilities; the shared components already carry
   the right border, background, and motion.
2. Use `text-ink-primary` / `-secondary` / `-muted` for all text — never a hardcoded
   Tailwind gray/slate/red/emerald class. (`text-status-*` for state, never a raw color.)
3. Charts: build the `EChartsOption` as usual and pass it to `<Chart option={...} />` —
   the dark theme is automatic. Only set colors explicitly in the option for things the
   theme can't know about (e.g., a status-colored bar).
4. Long free-text table columns: add `meta: { wrap: true }` to that column's `ColumnDef`
   rather than styling the cell manually.
5. Role-gate the nav link in `components/nav.tsx` to match the backend's
   `require_role(...)` exactly — the nav comment block explains why this must stay in
   sync (a visible link to a route that 403s is worse than no link).
