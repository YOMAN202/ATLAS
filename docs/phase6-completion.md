# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 6 — Dashboard Implementation & Validation Report

**Status: PHASE 6 COMPLETE — 2026-08-13**
*Sources of truth: `docs/phase6-dashboard-proposal.md` (approved), `docs/phase5-validation.md`, `ATLAS-SRS.md` §6.7/§14/§15, `ATLAS-TDD.md` §8*

This is the completion and validation report for Phase 6: a read-only FastAPI backend serving 7 dashboards over the validated Phase 5 warehouse, and a Next.js frontend rendering them. Per your instruction, this report documents every implemented KPI's source table, grain, calculation, refresh behavior, and validation method, and confirms the acceptance criteria before any Phase 7 work begins.

---

## 1. What was built

**Backend** (`backend/app/api/`): FastAPI routers for 7 dashboards (`executive.py`, `sales.py`, `inventory.py`, `procurement.py`, `supplier.py`, `operational.py`, `data_quality.py`), each with a summary endpoint and (except Executive) a paginated detail/drill-down endpoint. Role-based access (`backend/app/core/security.py`) via an `X-Atlas-Role` header, checked per-route. An ETL-run-keyed cache (`backend/app/api/cache.py`) so repeated requests within one ETL cycle don't re-query the warehouse.

**Frontend** (`frontend/`): Next.js App Router, one page per dashboard, role-based navigation (a link only renders for roles that can actually open it — kept in sync with the backend's `require_role(...)` calls), ECharts for the two trend charts (Executive revenue/margin, Data Quality score trend), TanStack Table for every drill-down table, a role selector persisted to `localStorage` (role-played through the UI per SRS §16, not a real login).

**Infrastructure**: the `atlas_reporting` MySQL role (SEC-3) — read-only on `atlas_olap`, structurally unable to write anything or read `atlas_oltp` at all — created via `docker/mysql/init/02-create-app-roles.sql` and verified directly (§4 below). This is the dashboard API's only database connection.

## 2. KPI Registry

Every KPI actually rendered anywhere in the UI, with its source table, grain, calculation, refresh behavior, and validation method. KPIs that are **not** implemented (and why) are listed at the end of each dashboard's table, not silently omitted.

### Executive (`/api/v1/dashboards/executive`, `backend/app/api/v1/executive.py`)

| KPI | Source table | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| Revenue | `summary_daily_revenue_by_region` | 1 row / region / day | `SUM(total_revenue)` | Cached until next ETL run | Exact match to `docs/phase5-validation.md` §1 ($414,858,410.46) |
| Gross Margin | `summary_daily_revenue_by_region` | 1 row / region / day | `SUM(total_gross_margin)` | Same | Exact match ($210,074,493.78) |
| Order Volume / Order Lines | `summary_daily_revenue_by_region` | 1 row / region / day | `SUM(total_orders)` / `SUM(total_order_lines)` | Same | Exact match (292,925 / 732,549) |
| Order Fulfillment Rate | `fact_orders` joined `dim_customer` | 1 row / order line | `SUM(allocated_quantity) / SUM(ordered_quantity)` | Same | 95.44% — independently recomputed via direct SQL during this validation, matches |
| Daily Revenue/Margin Trend | `summary_daily_revenue_by_region` joined `dim_date` | 1 row / region / day | `GROUP BY full_date, SUM(...)` | Same | Rendered as an ECharts line chart, spot-checked visually |

**Not implemented:** Cost to Serve (SRS §15) — no formula defined anywhere in frozen spec; the response returns `null` with an explicit note rather than an invented calculation (per your rule 2).

### Sales (`/api/v1/dashboards/sales`, `backend/app/api/v1/sales.py`)

| KPI | Source table | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| Order Lines | `fact_orders` | 1 row / order line | `COUNT(*)` | Cached until next ETL run | 732,549 — exact match |
| Distinct Orders | `fact_orders` | 1 row / order line | `COUNT(DISTINCT order_number)` | Same | 292,925 — exact match |
| Ordered/Allocated/Backordered Quantity | `fact_orders` | 1 row / order line | `SUM(...)` per column | Same | Cross-checked: allocated/ordered = 0.9544, matches Executive's fulfillment rate exactly (same underlying data, different endpoint) |
| Fulfillment Rate | `fact_orders` | 1 row / order line | `SUM(allocated_quantity)/SUM(ordered_quantity)` | Same | 95.44% |
| Average Order Value | `fact_orders` | 1 row / order line | `SUM(extended_revenue) / COUNT(DISTINCT order_number)` | Same | $1,416.26 |
| Order Line Detail (drill-down) | `fact_orders` | 1 row / order line | Direct row projection, paginated | Same | Row 1 matches a manually cross-checked OLTP order line |

### Inventory (`/api/v1/dashboards/inventory`, `backend/app/api/v1/inventory.py`)

| KPI | Source table(s) | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| On Hand (units) | `fact_inventory_snapshot` | 1 row / product / warehouse / day | `SUM(quantity_on_hand)` at latest `snapshot_date_key` | Cached until next ETL run | 214,127 units as of 2021-12-31 |
| Inventory Value | `fact_inventory_snapshot` | same | `SUM(inventory_value)` at latest date | Same | $19,845,581.04 |
| Stockout Rate | `fact_inventory_snapshot` | same | `AVG(is_stockout)` at latest date | Same | 0.68% — consistent with `docs/phase5-validation.md` §9's 17,708/1,825,000 finding |
| Inventory Turnover | `fact_orders` (COGS) + `fact_inventory_snapshot` (avg value) | cross-table, explicitly two sources | `SUM(extended_cost) / AVG(daily total inventory_value)` over the selected period | Same | 8.75 — a standard supply-chain formula, not invented, documented as genuinely needing two tables |
| Days of Supply | `fact_inventory_snapshot` (on-hand) + `fact_orders` (units sold) | cross-table | `latest total on-hand / avg daily units sold` | Same | 37.3 days |
| Snapshot Detail (drill-down) | `fact_inventory_snapshot` | 1 row / product / warehouse / day | Direct row projection, paginated, most recent first | Same | 1,825,000 total rows shown in pagination footer — exact match |

**Not implemented:** Overstock Value (SRS §15) — needs an explicit days-of-supply threshold policy not defined anywhere in frozen spec; returns `null` with a note rather than a placeholder threshold.

### Procurement (`/api/v1/dashboards/procurement`, `backend/app/api/v1/procurement.py`)

| KPI | Source table | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| PO Lines | `fact_procurement` | 1 row / PO line | `COUNT(*)` | Cached until next ETL run | 21,189 — exact match |
| Total Spend | `fact_procurement` | same | `SUM(extended_cost)` | Same | $214,388,276.10 |
| Average Unit Cost | `fact_procurement` | same | `SUM(extended_cost) / SUM(ordered_quantity)` | Same | $97.81 |
| Receipt Rate | `fact_procurement` | same | `SUM(received_quantity) / SUM(ordered_quantity)` | Same | 94.65% |
| Quality Rejection Rate | `fact_procurement` | same | `SUM(quality_rejected_quantity) / SUM(received_quantity)` | Same | 2.00% |
| PO Line Detail (drill-down) | `fact_procurement` | 1 row / PO line | Direct row projection, paginated | Same | 21,189 total rows in pagination footer |

### Supplier (`/api/v1/dashboards/supplier`, `backend/app/api/v1/supplier.py`)

| KPI | Source table | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| Deliveries | `fact_supplier_delivery` | 1 row / delivery event | `COUNT(*)` | Cached until next ETL run | 20,493 — exact match |
| On-Time Delivery % | `fact_supplier_delivery` | same | `AVG(is_on_time)` | Same | 92.08% |
| Avg Lead Time Variance | `fact_supplier_delivery` | same | `AVG(lead_time_variance_days)` | Same | 0.23 days |
| Quality Rejection Rate | `fact_supplier_delivery` | same | `SUM(quality_rejected_quantity) / SUM(received_quantity)` | Same | 2.00% — matches Procurement's figure exactly (same underlying quality data, cross-checked between two dashboards) |
| Delivery Detail (drill-down) | `fact_supplier_delivery` | 1 row / delivery event | Direct row projection, paginated | Same | 20,493 total rows |

**Not implemented:** Risk Score (SRS §15) — Phase 7 decision-support scope (FR-8.2), per your approved scope exclusion.

### Operational (`/api/v1/dashboards/operational`, `backend/app/api/v1/operational.py`)

| KPI | Source table(s) | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| Shipments | `fact_shipments` | 1 row / shipment | `COUNT(*)` | Cached until next ETL run | 696,747 — exact match |
| On-Time Delivery Rate | `fact_shipments` | same | `AVG(is_on_time)` | Same | **Structurally unavailable — see finding below**, disclosed via `on_time_delivery_rate_note` |
| Avg Cost / Mile | `fact_shipments` | same | `SUM(shipping_cost) / SUM(distance_miles)` | Same | $1.76 |
| Avg Transit Days | `fact_shipments` | same | `AVG(transit_days)` | Same | 3.38 days |
| Warehouse Capacity Utilization | `fact_inventory_snapshot` (latest on-hand per warehouse) + `dim_warehouse` (capacity) | cross-table | `SUM(quantity_on_hand) / total_capacity_units` per warehouse, at latest date | Same | Rendered per-warehouse in a table, cross-checked against Inventory dashboard's total on-hand |
| Shipment Detail (drill-down) | `fact_shipments` | 1 row / shipment | Direct row projection, paginated | Same | 696,747 total rows |

**Not implemented:** Pick Accuracy, Zone Throughput (SRS §15) — no fact table exists at picking-event or warehouse-zone grain anywhere in the warehouse; both return `null` with an explicit note (per your rule 1).

**Real finding, disclosed rather than hidden:** while building this dashboard, `on_time_delivery_rate` came back `null` for all 696,747 shipments. Investigation traced this to the source: `atlas_oltp.shipments.estimated_delivery_date` is `NULL` for 100% of rows — the simulation engine never populates it — so `fact_shipments.is_on_time` (which needs both the estimate and the actual date) can never be computed. This is a genuine upstream data limitation, not a dashboard bug; `transit_days` (which only needs `actual_delivery_date`) is unaffected and correctly populated (99% non-null). The API discloses this explicitly rather than showing a bare, unexplained `null`.

### Data Quality (`/api/v1/dashboards/data-quality`, `backend/app/api/v1/data_quality.py`)

| KPI | Source table | Grain | Calculation | Refresh | Validated |
|---|---|---|---|---|---|
| Overall DQ Score | `etl_run_table_metrics` | 1 row / run / table | `(extracted − quarantined − rejected) / extracted`, summed across tables for the current run | Cached until next ETL run | 100% — matches `docs/phase5-validation.md` §7's clean-quarantine finding exactly |
| Quarantine Rate | `etl_run_table_metrics` | same | `SUM(quarantined) / SUM(extracted)` | Same | 0% |
| Referential Integrity Failure Rate | `dq_quarantine` + `etl_run_table_metrics` | — | `COUNT(rule_violated='DQ-3' for this run) / SUM(extracted)` | Same | 0% |
| Run Duration | `etl_run_table_metrics` | 1 row / run / table | `SUM(duration_seconds)` for the run — **not** `etl_run_log.duration_seconds` | Same | 1,460.69s (24.3 min), matches the Stage B fact/summary total in `docs/phase5-stage-b-completion.md` §8 exactly |
| Per-Table Breakdown | `etl_run_table_metrics` | 1 row / run / table | Same formula as Overall DQ Score, per table | Same | All 7 fact/summary tables shown, each 100%, extracted counts match §1 of `docs/phase5-validation.md` exactly |
| Run Trend | `etl_run_log` + `etl_run_table_metrics` | 1 row / run | DQ score per `SUCCEEDED` run, charted | Same | Shows the real run history (runs #1 and #9 — the only two `SUCCEEDED` full runs in this environment) |
| Quarantine Detail (drill-down) | `dq_quarantine` | 1 row / quarantined record | Direct row projection, paginated, filterable by table/rule | Same | Correctly shows 0 rows (empty table) |

**Deliberate deviation from `etl_run_log.duration_seconds`:** disclosed in `docs/phase5-validation.md` §8 as an unreliable column for runs finalized via the one-off `run_one_fact.py` helper. The dashboard sums `etl_run_table_metrics` instead — every code path (including that helper) always writes those rows correctly.

## 3. Reconciliation validation (acceptance criterion: "API responses reconcile to warehouse aggregates")

Every "Validated" cell in §2 was checked live against this session's already-independently-validated `docs/phase5-validation.md` figures, or (for KPIs that document doesn't cover, e.g. fulfillment rate, turnover, receipt rate) recomputed directly via `mysql` CLI against `atlas_olap` and compared to the API's JSON response. No discrepancies found after the one bug fix in §5.

Cross-dashboard consistency was also checked, not just dashboard-to-database: Sales' fulfillment rate (95.44%) matches Executive's independently-computed fulfillment rate exactly (same source data, two different endpoints/queries); Procurement's and Supplier's quality rejection rates (2.00%) match exactly despite being computed by different endpoints against different-but-related fact tables (`fact_procurement` vs. `fact_supplier_delivery`).

## 4. Read-only enforcement (acceptance criterion: "no dashboard feature may write to OLTP or OLAP")

Verified directly against the live database, not just by code inspection:

```
atlas_reporting SELECT on atlas_olap.fact_orders:  succeeded (732,549 rows)
atlas_reporting DELETE on atlas_olap.fact_orders:  ERROR 1142 — command denied
atlas_reporting SELECT on atlas_oltp.orders:       ERROR 1142 — command denied
```

Every dashboard route's only database dependency is `get_olap_connection` (`backend/app/api/deps.py`), which connects exclusively via `atlas_reporting`. No route anywhere in `backend/app/api/` executes `INSERT`/`UPDATE`/`DELETE`/`DDL` — confirmed by inspection of all 7 router files (every SQL statement is a `SELECT`).

## 5. Real bug found and fixed during implementation

`GET /api/v1/dashboards/inventory/detail` hung indefinitely (confirmed via direct `curl` and MySQL's `MAX_EXECUTION_TIME`, both timing out past 8 seconds) when queried with no filters — which is the default, first-load case. Root cause: the query joined `dim_date` to format the snapshot date, then ordered by the *joined* column (`dd.full_date`) rather than the fact table's own indexed column (`f.snapshot_date_key`). Against `fact_inventory_snapshot`'s 1.8M rows — the warehouse's largest table — with an unfiltered `WHERE`, MySQL had no usable index for that `ORDER BY` and fell back to a full filesort of the entire joined result before applying `LIMIT`.

**Fix:** removed the `dim_date` join entirely from the detail query; `ORDER BY f.snapshot_date_key DESC, f.product_key, f.warehouse_key` uses the existing `ix_fact_inventory_snapshot_snapshot_date_key` index directly. The response's `snapshot_date` field is now computed in Python from the `YYYYMMDD` integer key (`date(key // 10000, (key // 100) % 100, key % 100)`) — no join needed at all. Verified fixed: the same request that hung for 8+ seconds now returns in well under a second, and the frontend's drill-down table renders all 25 rows correctly (screenshot-verified).

This was caught by actually driving the frontend in a real (headless) browser and watching the network tab — not by API-level `curl` checks alone, which had already reported the *summary* endpoint as healthy and could easily have missed a detail-endpoint-only bug if only spot-checked at the API layer.

## 6. Automated tests

`backend/tests/api/` — 16 tests, all passing, run against a dedicated `atlas_olap_test` schema (real DDL applied via `etl/warehouse_ddl/apply_ddl.py`, same pattern as `etl/tests/`), not mocks:

- `test_security_and_cache_unit.py` (7 tests): `require_role` accept/reject/case-insensitivity/unknown-role logic; cache key stability and roundtrip — pure unit, no DB.
- `test_executive_reconciliation.py` (6 tests): hand-seeded summary/fact rows reconciled against exact expected sums; region filtering; role-based 200/403/422/503 responses.
- `test_data_quality_scoring.py` (3 tests): hand-seeded `etl_run_table_metrics`/`dq_quarantine` rows reconciled against exact expected DQ score/quarantine rate/referential-integrity-failure-rate arithmetic; role rejection; quarantine filtering.

```
16 passed in ~70s (warm) / ~200s (cold, full DDL apply)
```

**Not covered by automated tests** (disclosed, not silently skipped): Sales, Inventory, Procurement, Supplier, and Operational dashboards don't have dedicated reconciliation tests — Executive and Data Quality were chosen as the two representative examples (proving the pattern against both a Type-1-style summary table and the ETL metadata tables). All 7 were verified manually against real data (§2, §7) instead.

## 7. Full-stack browser verification

Screenshotted via headless Chromium (Playwright) against the real, running `atlas_frontend`/`atlas_backend`/`atlas_mysql` containers with the actual validated warehouse data — not a mocked or seeded test dataset:

- Executive: KPI tiles and the 365-day revenue/margin trend chart render correctly; `Revenue $414,858,410`, `Gross Margin $210,074,494`, `Orders 292,925`, `Order Lines 732,549`, `Fulfillment Rate 95.4%` all visible and correct.
- Data Quality: `Overall DQ Score 100%`, `Quarantine Rate 0%`, per-table breakdown showing all 7 tables at 100%, run trend chart, empty quarantine table correctly showing "No rows for the current filters."
- Inventory: after the fix in §5, the 1,825,000-row drill-down table paginates correctly (`page 1 of 73000`), summary KPIs correct.
- Sales, Procurement, Supplier, Operational: all render their summary KPIs and 25-row-paginated drill-down tables correctly with real data; Operational's warehouse capacity table and shipment detail table both verified.
- Zero browser console errors or page errors across all 7 dashboards.

## 8. Known limitations (stated plainly, per this project's established practice)

1. **Frontend types are hand-typed, not generated** (`frontend/lib/types.ts`) — mirrors the backend's Pydantic models manually rather than via OpenAPI codegen, a deliberate scope simplification noted in the approved proposal (§4). A drift between the two would currently only surface at runtime, not compile time.
2. **`estimated_delivery_date` is NULL for 100% of shipments at the OLTP source** (§2's Operational section) — `on_time_delivery_rate` is structurally unavailable from this dataset, disclosed via an explicit API field rather than a silent `null`.
3. **5 of 7 dashboards lack dedicated automated reconciliation tests** (§6) — verified manually instead; Executive and Data Quality carry the automated-test burden as representative examples of the pattern.
4. **OFFSET-based pagination** on the drill-down tables gets linearly more expensive at high page numbers on the largest tables (`fact_inventory_snapshot`, `fact_orders`, `fact_shipments`) — not a problem at the page counts a human would actually browse to, but not cursor-based either; not re-engineered in this pass since it wasn't the bottleneck actually observed (§5's bug was the ORDER BY/JOIN issue, not OFFSET itself).
5. **Cost to Serve, Overstock Value, Risk Score, Pick Accuracy, Zone Throughput** are not implemented, each with an explicit reason documented in §2 — per your rules 1 and 2, no placeholder formulas or fabricated thresholds were used anywhere.
6. **`atlas_app`/`atlas_etl` roles exist but aren't wired into the running application** (only `atlas_reporting` is) — the OLTP backend and ETL pipeline continue using their pre-existing root-credentialed connections; migrating those was out of scope for a dashboard-focused phase and wasn't requested.

## 9. Acceptance criteria — assessment

| Criterion | Status |
|---|---|
| Every implemented KPI is warehouse-backed | ✅ — §2, every KPI's source table(s) and calculation documented; nothing computed from outside `atlas_olap` |
| Every dashboard query is documented | ✅ — §2 (KPI-level) and inline in every router's module docstring and per-query comments (code-level) |
| API responses reconcile to warehouse aggregates | ✅ — §3, cross-checked against `docs/phase5-validation.md` and independent SQL recomputation |
| Dashboard totals reconcile to OLAP facts | ✅ — §7, browser-verified against the same real data |
| UI contains no fabricated or estimated business metrics | ✅ — every unavailable KPI (§2's "Not implemented" notes, §8.5) returns `null` with an explanatory note, never a placeholder number |
| No invented KPIs (pick accuracy, zone throughput) | ✅ — §2 Operational section, explicit non-implementation |
| No invented business formulas (cost-to-serve, overstock threshold) | ✅ — §2 Executive/Inventory sections, explicit non-implementation |
| Read-only analytics layer | ✅ — §4, verified live against the database, not just by code review |

**Phase 6 is complete.** Per your instruction, this is where implementation stops — no Phase 7 (decision support, forecasting, optimization, recommendations) work has begun.
