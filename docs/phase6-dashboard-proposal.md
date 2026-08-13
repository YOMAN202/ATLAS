# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 6 — Dashboard Architecture Proposal (AWAITING APPROVAL — NOT YET IMPLEMENTED)

**Status: PROPOSAL — 2026-08-13**
*Sources of truth: ATLAS-SRS.md §6.7/§14/§15 (FROZEN), ATLAS-TDD.md §8 (FROZEN), ATLAS-Roadmap.md (FROZEN), `docs/phase5-validation.md`*

This is a design document only. No frontend or backend API code has been written. Per your instruction, implementation does not begin until you approve this proposal.

---

## 1. Scope, and a naming note

The frozen `ATLAS-Roadmap.md` splits what you're calling "Phase 6" across three of its own phases: **Phase 6 = Backend API**, **Phase 7 = BI & Decision Support** (recommendations, forecasting, explainability), **Phase 8 = Frontend**, with Frontend depending on both. You confirmed this proposal should cover the backend API layer and the frontend dashboard layer — the 5 KPI/visualization dashboards described in SRS §6.7 — and explicitly exclude the recommendation/forecasting/explainability machinery (SRS §6.8, FR-8.1–8.4) as separate, later work. That's this document's scope. Roadmap phase numbers are used below only where quoting frozen text; "Phase 6" in your sense means "backend API + frontend dashboards," not the Roadmap's own Phase 6 alone.

## 2. What the warehouse can actually support today

Before designing dashboards, it matters which SRS §15 KPIs have real, already-validated data behind them right now (per `docs/phase5-validation.md`) versus which don't exist in the warehouse yet. Overpromising here would mean designing a dashboard around a number that can't actually be computed.

| Dashboard (SRS) | KPI | Computable now? | Source |
|---|---|---|---|
| Executive (FR-7.1) | Revenue | ✅ | `fact_orders.extended_revenue` / `summary_daily_revenue_by_region.total_revenue` |
| | Gross margin | ✅ | `fact_orders.gross_margin` / `summary_daily_revenue_by_region.total_gross_margin` |
| | Order volume | ✅ | `fact_orders` row/order count |
| | Order fulfillment rate | ✅ | `fact_orders.allocated_quantity` / `ordered_quantity` |
| | Cost-to-serve | ⚠️ partial | No single column; derivable by aggregating `fact_shipments.shipping_cost` + `fact_orders.extended_cost`, not a named KPI field — needs an explicit formula decision, proposed in §5.1 |
| Inventory (FR-7.2) | Inventory turnover | ✅ | `fact_orders.extended_cost` (COGS) ÷ avg `fact_inventory_snapshot.inventory_value` |
| | Stockout rate | ✅ | `fact_inventory_snapshot.is_stockout` (validated in `docs/phase5-validation.md` §9) |
| | Days of supply | ✅ | `quantity_on_hand` ÷ trailing avg daily usage (derived from `fact_orders`) |
| | Overstock value | ⚠️ partial | Computable, but "overstock" needs a threshold policy (e.g. days-of-supply > N) not yet defined anywhere in frozen spec — proposed in §5.2 |
| Warehouse (FR-7.2) | Capacity utilization | ✅ | `fact_inventory_snapshot.quantity_on_hand` (summed per warehouse) ÷ `dim_warehouse.total_capacity_units` |
| | Pick accuracy | ❌ not available | No picking-event fact exists anywhere in the warehouse (Phase 2's OLTP has no pick-level table) — **cannot be built without new OLTP/ETL scope**, out of this proposal |
| | Throughput per zone | ❌ not available | `warehouse_zones` exists in OLTP but no fact is at zone grain — every warehouse fact is warehouse-level, not zone-level — **cannot be built without new ETL work** |
| Transportation (FR-7.2) | On-time delivery rate | ✅ | `fact_shipments.is_on_time` |
| | Cost per mile/shipment | ✅ | `fact_shipments.shipping_cost` ÷ `distance_miles` |
| | Carrier utilization | ⚠️ partial | Shipment volume per carrier is computable; "utilization" against a capacity denominator isn't modeled (no carrier capacity fact) |
| Supplier (FR-7.2) | On-time delivery % | ✅ | `fact_supplier_delivery.is_on_time` |
| | Quality rejection rate | ✅ | `fact_supplier_delivery.quality_rejected_quantity` |
| | Lead-time variance | ✅ | `fact_supplier_delivery.lead_time_variance_days` |
| | Risk score | ❌ deferred | Explicitly Phase 7 decision-support territory (FR-8.2) per your chosen scope — not a warehouse column, requires scoring logic |
| Data Quality (FR-7.5) | Per-table DQ score, quarantine rate, referential integrity failure rate | ✅ all | `etl_run_table_metrics`, `dq_quarantine` — already fully built by Stage A/B, nothing new needed |

**Conclusion:** 5 dashboards are fully buildable now with real data — **Executive, Inventory, Transportation, Supplier, Data Quality** — each with 3–4 of their KPIs directly available and at most one needing a small, explicit formula/threshold decision (§5). **Warehouse** dashboard is buildable only for capacity utilization; pick accuracy and zone throughput have no underlying fact table and are out of scope until a future ETL pass adds one (not proposed here — flagged, not silently built as a fake number). **Risk & Exceptions** (FR-7.3) and **Forecasting & Planning** (FR-7.4) are deferred to Phase 7 per your chosen scope, except for the parts of Risk & Exceptions that are pure description, not scoring — see §5.6.

## 3. Backend API layer

**Framework:** FastAPI, per the frozen TDD stack (`ATLAS-TDD.md` §8, table row "API Layer").

**Structure** (new — `backend/app/api/` does not exist yet):
```
backend/app/api/
  v1/
    dashboards.py     # /api/v1/dashboards/{executive,inventory,transportation,supplier,data-quality}
    inventory.py       # /api/v1/inventory/warehouse/{id}, drill-downs
    suppliers.py        # /api/v1/suppliers/{id}, /api/v1/suppliers/{id}/deliveries
    shipments.py         # /api/v1/shipments, drill-downs by carrier/warehouse
    quality.py            # /api/v1/data-quality/runs, /api/v1/data-quality/runs/{id}
  deps.py               # DB session (atlas_reporting role), auth/role dependency
backend/app/core/security.py   # role-based access (SEC-5), does not exist yet
```

Endpoint naming follows the pattern already fixed in the TDD: `/api/v1/dashboards/executive`, `/api/v1/suppliers/{id}/risk` (that specific example endpoint is Phase 7 territory and deferred), `/api/v1/inventory/warehouse/{id}`.

**Data access:** every dashboard endpoint reads `atlas_olap` directly via the `atlas_reporting` role (SEC-3: read-only on OLAP, shared with Power BI) — never `atlas_app`'s OLTP connection. This is a hard boundary, not a convention: dashboard queries have no reason to touch OLTP, and using a read-only role structurally prevents a dashboard endpoint from ever accidentally writing.

**Validation:** every request/response shape is a Pydantic model (SEC-2) — query parameters (date ranges, warehouse/supplier/region filters, pagination) validated before reaching any SQL.

**Caching, driven by NFR-10 (≤500ms cached, ≤2s on-demand):** cache key = `(endpoint, filters, current etl_run_id)`. Every dashboard query result is cached until the next `etl_run_log` row with `status=SUCCEEDED` appears — per the TDD's own framing, this is a batch-analytics system where dashboards only need to refresh once per ETL cycle, not per request. `summary_daily_revenue_by_region` already exists as a physical pre-aggregation for the Executive dashboard's daily revenue/margin trend; other dashboards query their source facts directly with `GROUP BY`, since none of them are large enough post-Stage-B to need their own pre-built summary table (largest single-dashboard query would scan `fact_inventory_snapshot` at ~1.8M rows, well within NFR-9's 2s target with the existing indexes — no new summary table proposed unless a real measurement later says otherwise).

**Pagination/filtering:** standardized response envelope (`{data, page, page_size, total}`) across every list endpoint, since TanStack Table on the frontend expects this shape uniformly (TDD §8).

**Role-based access (SEC-5):** middleware checks a role-played actor identity (Executive / Operations Analyst / Supply Planner / Administrator, per SRS §3) against each endpoint's allowed roles — e.g., Executive dashboard readable by Executive + Admin; Supplier/Inventory/Transportation dashboards readable by Operations Analyst + Admin; write/admin endpoints (out of this proposal's scope — no dashboard endpoint writes anything) Administrator-only. No full identity provider (SRS §16 assumption: roles are role-played through the UI, not backed by real auth) — a lightweight role-selector, not a login system.

## 4. Frontend layer

**Framework/stack, fixed by the TDD, not a choice made here:** Next.js App Router, React, TypeScript, Tailwind, shadcn/ui, ECharts (charts), TanStack Table (tabular/drill-down), Framer Motion used sparingly.

**Current state:** `frontend/` is a bare scaffold (`app/layout.tsx`, `app/page.tsx`, `app/globals.css` only) — greenfield, no routes or components yet.

**Structure:**
```
frontend/app/
  (executive)/          # route group — Executive role
    dashboard/page.tsx
  (operations)/          # route group — Operations Analyst role
    inventory/page.tsx
    transportation/page.tsx
    supplier/page.tsx
  (admin)/                 # route group — Administrator role
    data-quality/page.tsx
  layout.tsx                 # role selector (role-played, per SRS §16), nav shell
frontend/components/
  charts/           # ECharts wrappers: RevenueChart, StockoutTrend, OnTimeDeliveryChart, etc.
  tables/            # TanStack Table wrappers with the standard {data,page,page_size,total} envelope
  kpi-card.tsx         # shared KPI tile (value + trend + sparkline)
frontend/lib/
  api-client.ts          # typed client generated/aligned against the FastAPI OpenAPI schema (TDD §8)
```

**Role-based route groups** map directly to SRS §3's four actors (Executive User, Operations Analyst, Supply Planner, Administrator) — a Supply Planner route group is scaffolded but empty in this phase, since Planning/Forecasting (FR-7.4) is deferred to Phase 7.

## 5. Dashboard specifications

### 5.1 Executive Overview (FR-7.1)
- **KPI tiles:** Revenue, gross margin, order volume, order fulfillment rate — each with a trailing trend line (ECharts sparkline) sourced from `summary_daily_revenue_by_region` (already pre-aggregated daily, exactly matching NFR-9's 2s target with no new table needed).
- **Cost-to-serve**, flagged in §2 as needing a formula decision: proposed as `(Σ fact_shipments.shipping_cost + Σ fact_orders.extended_cost) / Σ fact_orders.extended_revenue` for the selected date range — a reasonable, defensible definition, but a genuine judgment call worth your confirmation before building, not something to silently decide.
- **Main chart:** revenue/margin trend over time, filterable by region (`dim_region`) and date range (`dim_date`).
- **Drill-down:** clicking a date/region opens the order-line detail table (TanStack Table, paginated) backed by `fact_orders`.

### 5.2 Inventory (FR-7.2)
- **KPI tiles:** inventory turnover, stockout rate, days of supply.
- **Overstock value**, flagged in §2: proposed threshold of days-of-supply > 90 (a placeholder, explicitly a policy decision for you to confirm or adjust, not invented as fact).
- **Main chart:** stockout rate over time by product category (`dim_product.category`) and warehouse.
- **Drill-down:** product/warehouse detail table from `fact_inventory_snapshot`, filterable by date.

### 5.3 Transportation (FR-7.2)
- **KPI tiles:** on-time delivery rate, cost per mile, cost per shipment.
- **Carrier utilization**, flagged in §2 as partial: shown as shipment volume per carrier (a real, computable number) rather than a fabricated "utilization %" against a non-existent capacity baseline.
- **Main chart:** on-time delivery rate trend by carrier (`dim_carrier`).
- **Drill-down:** shipment detail table from `fact_shipments`, filterable by carrier/warehouse/date.

### 5.4 Supplier (FR-7.2)
- **KPI tiles:** on-time delivery %, quality rejection rate, lead-time variance — all directly from `fact_supplier_delivery`.
- **Risk score:** not included (Phase 7, per your chosen scope).
- **Main chart:** on-time % and lead-time variance trend by supplier (`dim_supplier`, SCD2-aware — if a supplier's terms ever change, the dashboard should show which version was current at each point in time, though today's real dataset has only one version per supplier, per `docs/phase5-validation.md` §5/§11).
- **Drill-down:** delivery-level detail table from `fact_supplier_delivery`.

### 5.5 Data Quality (FR-7.5)
- **KPI tiles:** latest run's per-table DQ score (accepted / (accepted + quarantined + rejected)), quarantine rate, DQ-3 (referential integrity) failure rate — all directly from `etl_run_table_metrics` and `dq_quarantine`, no new computation needed.
- **Main chart:** DQ score trend across runs (`etl_run_log` joined to `etl_run_table_metrics`).
- **Drill-down:** quarantine detail table from `dq_quarantine`, filterable by `source_table`/`rule_violated` — this is the one dashboard where every underlying number is already fully validated in `docs/phase5-validation.md` §7.

### 5.6 Risk & Exceptions (FR-7.3) — descriptive subset only
Full scope (supplier risk scores, stockout risk prediction) is Phase 7. A purely descriptive version is buildable now and proposed as an optional addition, not required for this phase: a table of "current exceptions" — shipments where `is_on_time = false` in the last N days, products currently `is_stockout = true`, PO lines with `quality_rejected_quantity > 0` — i.e., filtering/surfacing existing facts, not scoring or predicting anything. Flagged as optional so you can decide whether it belongs in this phase or waits for Phase 7 alongside real risk scoring.

## 6. Explicitly deferred (not in this proposal)

- **Phase 7 BI/decision support** — reorder recommendations (FR-8.1), supplier risk alerts (FR-8.2), route optimization suggestions (FR-8.3), explainability (FR-8.4) — per your chosen scope.
- **Forecasting & Planning dashboard** (FR-7.4) — depends entirely on Phase 7's forecasting logic.
- **Warehouse pick accuracy and zone-level throughput** — no underlying fact table exists; would require new OLTP/ETL scope beyond a dashboard/API change, not proposed here.
- **Supplier risk score** (part of FR-7.2's Supplier KPI list) — same reason as Phase 7 deferral above.
- **Scenario analysis** (FR-9.1) — depends on Phase 7's forecasting/recommendation engine.

## 7. Performance targets (inherited, not renegotiated)

- NFR-9: dashboard queries ≤2s, drill-downs ≤5s, at the target data volume — the real validated dataset (§2's tables, up to 1.8M rows in `fact_inventory_snapshot`) is the actual measurement basis, not a hypothetical.
- NFR-10: API ≤500ms cached, ≤2s on-demand — met via the ETL-run-keyed cache in §3.

No performance work is proposed here beyond the caching design — actual query performance against the real warehouse should be measured once endpoints exist, not assumed.

## 8. Proposed build sequence (for your review, not started)

1. `backend/app/api/` scaffold + `atlas_reporting` DB role + `core/security.py` role middleware.
2. Data Quality dashboard endpoint + page first — every underlying number is already validated (`docs/phase5-validation.md`), zero new formula decisions, good first proof of the full stack (API → cache → frontend → chart/table).
3. Executive dashboard (needs the cost-to-serve formula decision, §5.1).
4. Inventory, Transportation, Supplier dashboards (parallelizable, each self-contained).
5. Risk & Exceptions descriptive subset (§5.6), only if you want it in this phase.

---

**Awaiting your approval before any of this is implemented.** Two open decisions need your input before or during implementation: the cost-to-serve formula (§5.1) and the overstock-value threshold (§5.2) — both flagged rather than silently decided. Also flag whether §5.6's descriptive Risk & Exceptions view belongs in this phase or should wait for Phase 7.
