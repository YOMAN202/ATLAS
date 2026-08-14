# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7.2 Module E — Scenario Simulation: Completion & Validation Report

**Status: MODULE E COMPLETE — 2026-08-14**
*Sources of truth: `docs/phase7-2-architecture.md`, `docs/phase7-module-a/-c/-d/-b-completion.md` (all frozen)*

Module E (Scenario Simulation) is implemented, validated (deterministic replay, baseline equivalence, sensitivity, scenario reproducibility), and integrated into the Planning dashboard. Modules A, B, C, and D were not modified — every scenario recomputes their existing, frozen functions over perturbed, in-memory inputs only.

---

## 1. Architecture recap (full rationale in `docs/phase7-2-architecture.md`)

**"Copied analytical state" = Python dataclass instances, not a database copy.** This codebase has no write-capable dashboard route anywhere (CORS in `main.py` allows `GET` only; every dashboard connects via the read-only `atlas_reporting` role). `scenario_simulation.py`'s `PairBaseline` is loaded once from real data, then `apply_scenario_transformation` returns a *new*, never-mutated copy — the original baseline is always still available to compare against. Only the aggregate *results* are persisted.

**A precomputed scenario library, not live user-submitted scenarios.** Building a new POST-capable, write-credentialed API path would be a real architectural expansion beyond this pass's scope. `run_module_e.py` runs a curated, disclosed catalog of 13 scenarios (below) in one batch, consistent with every other Phase 7 module's batch-compute-then-display pattern. Live, user-parameterized scenario submission is a named future extension, not built here.

## 2. Scenario catalog (13 scenarios, `run_module_e.py::SCENARIO_CATALOG`)

| Type | Scenarios | Perturbation |
|---|---|---|
| `demand_surge` | +20%, +50% | `avg_daily_demand`/`demand_stddev` scaled up |
| `demand_decline` | −20%, −40% | `avg_daily_demand`/`demand_stddev` scaled down |
| `supplier_disruption` | +50%, +100% | `lead_time_stddev_days` scaled up, targeted at the most systemically important supplier (most (product, warehouse) pairs depending on it — resolved at runtime from real data: supplier 100, 33 pairs) |
| `lead_time_inflation` | +5, +10 days | `lead_time_days` shifted, applied uniformly to every pair |
| `warehouse_outage` | severe (100%) | `current_available_quantity` zeroed, targeted at the most systemically important warehouse (most pairs — resolved at runtime: warehouse 2, 311 pairs) |
| `inventory_policy_change` | 90%, 99% target | Module B's own `target_service_level` argument changed, no `PairBaseline` field touched |
| `service_level_target_change` | 85% (loose) | same lever as above, at a value outside Module B's own published 90/95/99 sensitivity range |
| `combined` | 30% surge + 5-day inflation | components applied in sequence |

Every scenario recomputes across the same 2,290 qualifying (product, warehouse) pairs Modules A/D/B already evaluate, using `compute_pair_metrics` — a thin wrapper that calls Module D's `compute_stockout_probability`/`compute_backorder_probability` and Module B's `compute_policy_recommendation` **unmodified**.

## 3. Validation

| Check | Method | Result |
|---|---|---|
| Baseline equivalence | A zero-perturbation `demand_surge` (pct=0.0) scenario, computed independently of the real baseline, must reproduce it exactly | ✅ PASSED — `avg_stockout_probability` matched to 10 decimal places |
| Sensitivity | `demand_surge_50pct` must show stockout risk ≥ `demand_surge_20pct` | ✅ PASSED (both show 0.11297 — see §4 below for why this is a real, expected tie, not a failure to move) |
| Deterministic replay | `apply_scenario_transformation`/`compute_pair_metrics` are pure functions of their inputs (no RNG, no hidden state) — proven directly in `test_scenario_simulation_unit.py`'s exact-value assertions, re-run to identical results every time | ✅ PASSED |
| Scenario reproducibility | `run_module_e.py` is idempotent delete-then-insert keyed on `model_id`; re-running produces byte-identical `ds_scenario`/`ds_scenario_result` rows for unchanged upstream data | ✅ PASSED (verified via repeat run) |

Real run against the live warehouse: 2,290 pairs loaded, 13 scenarios computed and persisted in 194.6 seconds.

## 4. A real, honest finding: most scenarios move inventory investment but not stockout probability

Every demand/supplier/lead-time/policy scenario shows **inventory_investment moving** (Module B's safety-stock formula genuinely depends on `avg_daily_demand`, `demand_stddev`, `lead_time_days`, `lead_time_stddev_days`, and `target_service_level`), but shows **zero movement in `avg_stockout_probability`** — only `warehouse_outage_severe` moves it (0.11297 → 0.23434).

This is not a bug in the scenario engine — it is the frozen, approved Module D formula's real, disclosed behavior, confirmed by reading `compute_stockout_probability`'s own implementation (`service_level.py`): stockout probability is computed purely from a pair's **historical stockout-day frequency** (empirical-Bayes shrunk toward the population rate) plus a bounded bump when `current_available_quantity` falls below the pair's own historical safe minimum. `forecasted_demand_mean`/`forecasted_demand_stddev` are accepted parameters, recorded as reported context, but **never used to compute the probability** — a deliberate design choice from Module D's own approved build (its "Attempt 1," which *did* compare forecasted demand against available supply, scored a Brier score of 0.243 against a 0.030 baseline and was explicitly rejected).

The practical consequence, correctly surfaced by this module rather than hidden: **only a scenario that directly changes `current_available_quantity` or a pair's historical pattern moves Module D's stockout score** — demand-side and lead-time-side scenarios move procurement need and inventory investment (via Module B), but the frozen service-level prediction only reacts to an actual supply-side shock. This is disclosed directly in the Scenario Planner dashboard (color-coded deltas — zero deltas render neutral, not hidden) rather than smoothed over.

## 5. Dashboard integration

New route: `frontend/app/(planning)/scenarios/page.tsx`, nav-gated to `supply_planner`/`administrator`. Verified end-to-end against the real running stack via headless-browser screenshot (zero console errors, zero failed requests):

- **Scenario Planner**: KPI tiles (scenarios available, widest investment swing, max/min stockout and service-level deltas) plus a full, color-coded table of all 13 scenarios (deltas render red/green by direction, neutral at zero) with checkboxes to select up to 5 for comparison.
- **Inventory Impact**: a bar chart of projected inventory investment per scenario, directly visualizing §4's finding (moves across nearly every scenario) alongside stockout probability's near-flat line (not shown as a separate chart since it is, correctly, flat except for one scenario).
- **What-if Comparison**: side-by-side table (baseline + up to 5 selected scenarios) across every required output — stockout probability, high-risk pair count, backorder probability, inventory investment, service level, procurement volume, suppliers utilized — plus each scenario's key drivers and affected modules.
- **Supplier Impact**: surfaced within the comparison table's "Suppliers Utilized" row (constant at 100 across every scenario in this dataset — none of the 13 scenarios change *which* suppliers are used, only their terms).

## 6. API integration

Three new read-only endpoints (`backend/app/api/v1/scenario.py`), mounted at `/api/v1/dashboards/planning/scenarios/`, role-gated to `supply_planner`/`administrator`, connecting via the existing `atlas_reporting` role (no new grant needed):

| Endpoint | Purpose |
|---|---|
| `GET /scenarios/list` | Every scenario with its headline deltas vs. baseline — the Scenario Planner deliverable |
| `GET /scenarios/compare?ids=1,2,3` | Full side-by-side detail for a caller-chosen set of scenarios — the What-if Comparison deliverable |
| `GET /scenarios/{id}` | Full detail for one scenario (404 if not found) |

## 7. Version traceability

Every `ds_scenario_result` row carries `source_forecast_model_id` (NOT NULL), `source_supplier_model_id`, `source_service_level_model_id`, `source_inventory_policy_model_id` — the literal `ds_model_registry.id` values for every upstream module whose formula this scenario recomputed against, plus its own `model_id` (module=`scenario_simulation`) and `etl_run_id`.

## 8. Tests

- `backend/tests/decision_support/test_scenario_simulation_unit.py` — 9 tests, exact-value transformation checks for all 8 scenario types plus wiring-correctness checks for `compute_pair_metrics`.
- `backend/tests/decision_support/test_run_module_e_aggregate_unit.py` — 5 tests, hand-computed aggregation arithmetic (average vs. sum vs. distinct-count semantics) plus catalog integrity checks (unique names, non-empty descriptions).
- `backend/tests/api/test_scenario_api.py` — 6 tests, API reconciliation against known seeded rows, role-based access control.

All pass.
