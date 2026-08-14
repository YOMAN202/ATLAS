# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7.2 Module F — Route and Cost Optimization: Completion & Validation Report

**Status: MODULE F COMPLETE — 2026-08-14**
*Sources of truth: `docs/phase7-2-architecture.md` §2, `docs/phase7-module-a/-c/-d/-b/-e-completion.md` (all frozen)*

Module F (Route and Cost Optimization) is implemented, validated (recommendation consistency, cost reconciliation, service-level impact, explainability), and integrated into the Planning dashboard. No external optimization engine — every recommendation is a closed-form, deterministic heuristic over `dim_carrier` and `fact_shipments`/`fact_orders`.

---

## 1. Why this module is built around vehicle right-sizing, not carrier selection

Real data grounding (`docs/phase7-2-architecture.md` §2.1), confirmed directly against the warehouse before any formula was written:

- `dim_carrier.vehicle_cost_per_mile` is determined **entirely** by `vehicle_type_code` — every carrier of the same type charges the identical rate (VAN $1.10/mi × 9 carriers, BOX_TRUCK $1.75/mi × 8, SEMI_TRAILER $2.50/mi × 8).
- Transit time is statistically indistinguishable both across carriers of the same type and across vehicle types themselves: VAN 3.3821, BOX_TRUCK 3.3818, SEMI_TRAILER 3.3829 average days (re-confirmed live during this build: spread 0.0011 days).

"Which of the 9 VAN carriers" and "which route" are genuinely degenerate optimization axes in this dataset — the same category of finding as Module C's zero-variance `fill_rate` and Module D's near-constant `transit_days`. The one real, actionable lever in `dim_carrier` is *vehicle type*, so this module is built around that: **vehicle right-sizing** (matching shipment size to the cheapest sufficient vehicle) and **shipment consolidation** (combining same-day/origin/destination shipments into one trip).

## 2. Methodology

**Right-sizing** (`route_cost_optimization.py::compute_right_sizing_recommendation`): for one shipment, `cheapest_sufficient_vehicle` finds the lowest-cost-per-mile vehicle type whose `vehicle_capacity_units` covers the shipment's real order-line quantity (resolved via `fact_orders.shipment_number`, never assumed). Recommends a switch only when it's both a different type and a real cost reduction.

**Consolidation** (`compute_consolidation_recommendation`): shipments sharing `(origin_warehouse_key, destination_customer_key, ship_date)` are grouped; a group of 2+ is evaluated as one combined trip on the cheapest sufficient vehicle for the combined quantity. `distance_miles` is **not** a fixed lane property in this dataset — it varies even for the same (origin, destination) pair (up to 45 distinct values for one pair, confirmed directly) — so the combined trip's cost uses the group's *average* distance, disclosed as an approximation. Consolidation does **not** always save money — a group whose combined size forces an expensive vehicle type can score negative savings and correctly receives no recommendation (a real, tested edge case, `test_consolidation_returns_none_when_it_would_not_actually_save_money`).

Scoped to a real, representative **30-day analysis window** (2021-12-02 through 2021-12-31 — the same "recent window, not the full year" convention Modules A/D's own backtests already use), not the full 696,747-shipment history — disclosed explicitly, not silently narrowed.

## 3. A real, honest finding: vehicle-type assignment is essentially uncorrelated with shipment size

Checked directly against the real data, not assumed: **every single shipment assigned to a BOX_TRUCK or SEMI_TRAILER in the analysis window has a real order-line quantity that would fit in the cheapest VAN** (100% — 23,443/23,443 SEMI_TRAILER shipments and 23,684/23,684 BOX_TRUCK shipments, all ≤500 units). Vehicle-type assignment in this simulated dataset carries no relationship to actual shipment size — meaning right-sizing has enormous, genuine optimization potential here, not a manufactured one. This is exactly why 47,127 of 73,571 window shipments (64%) receive a right-sizing recommendation, and why total estimated savings ($47.3M) is a large fraction of the window's real total shipping cost ($79.1M, confirmed directly).

## 4. Validation

| Check | Method | Result |
|---|---|---|
| Recommendation consistency | Re-run right-sizing assembly against the same inputs, assert identical results (pure functions, no RNG) | ✅ PASSED |
| Feasibility | Every recommended vehicle's `capacity_units` ≥ the row's `total_quantity` | ✅ PASSED (57,912 rows) |
| Cost reconciliation | `current_total_cost − estimated_savings == recommended_total_cost` for every row (within 2¢ double-rounding tolerance) | ✅ PASSED (57,912 rows) |
| Explainability | Every row has a non-empty `business_rationale` and `contributing_factors` | ✅ PASSED |
| Service-level impact | Live query: `AVG(transit_days)` grouped by `vehicle_type_code`, spread must stay under 0.1 days — the empirical premise behind "right-sizing has zero service-level impact," checked at run time, not just assumed | ✅ PASSED (spread = 0.0011 days) |

Real run against the live warehouse: 73,571 window shipments evaluated, 57,912 recommendations (47,127 right-sizing + 10,785 consolidation) persisted in 122.1 seconds.

## 5. Dashboard integration

New route: `frontend/app/(planning)/route-cost-optimization/page.tsx`, nav-gated to `supply_planner`/`administrator`. Verified end-to-end against the real running stack via headless-browser screenshot (zero console errors, zero failed requests):

- KPI tiles: total estimated savings, right-sizing/consolidation opportunity counts with their own savings, and an explicit "Service-Level Impact: None" tile.
- **Transportation Impact**: a stacked bar chart of estimated savings per warehouse (right-sizing vs. consolidation), the per-warehouse rollup required given the confirmed single-warehouse-per-product constraint (genuine cross-warehouse reallocation isn't actionable here).
- A filterable (by recommendation type), paginated detail table of all 57,912 recommendations, sorted by estimated savings.

## 6. API integration

Three new read-only endpoints (`backend/app/api/v1/route_cost_optimization.py`), mounted at `/api/v1/dashboards/planning/route-cost-optimization/`, role-gated to `supply_planner`/`administrator`, connecting via the existing `atlas_reporting` role (no new grant needed):

| Endpoint | Purpose |
|---|---|
| `GET /route-cost-optimization/summary` | Headline KPIs |
| `GET /route-cost-optimization/warehouse-impact` | Per-warehouse rollup — the Transportation Impact deliverable |
| `GET /route-cost-optimization/detail` | Paginated rows, filterable by type and warehouse |

## 7. Version traceability

Every `ds_optimization_recommendation` row carries `model_id` (module=`route_cost_optimization`) and `etl_run_id`. This module has no upstream Modules A/B/C/D/E dependency (it operates on real shipment/carrier/order data directly, not forecast or policy outputs), so no `source_*_model_id` columns apply here — disclosed as a deliberate scope boundary, not an omission.

## 8. Tests

- `backend/tests/decision_support/test_route_cost_optimization_unit.py` — 7 tests, exact-value formula checks including the "consolidation doesn't always save money" edge case.
- `backend/tests/decision_support/test_run_module_f_grouping_unit.py` — 5 tests, shipment-to-group assembly correctness (grouping key, missing-quantity skip, singleton-group skip, no-destination-customer skip).
- `backend/tests/api/test_route_cost_optimization_api.py` — 6 tests, API reconciliation against known seeded rows, role-based access control.

All pass.
