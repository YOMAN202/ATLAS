# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7.2 Architecture — Scenario Simulation & Route/Cost Optimization

**Status: APPROVED — 2026-08-14** (per your Phase 7.2 authorization message)
*Sources of truth: `docs/phase7-architecture.md` (Phase 7.1, frozen), `docs/phase7-module-a/-c/-d/-b-completion.md` (all four frozen baselines)*

Phase 7.2 adds a **decision-experimentation layer** on top of Phase 7.1's four frozen modules: Module E (Scenario Simulation) lets a user evaluate hypothetical operational conditions without touching real warehouse data; Module F (Route/Cost Optimization) recommends real, measurable transportation savings from the validated warehouse itself. Modules A, B, C, D are not modified — every formula this document specifies calls their existing, frozen functions with different inputs, never edits them.

This document resolves the design questions the authorization message leaves open — the same ADR-style discipline Phase 7.1 used — grounded in real data explored before any formula was chosen, not assumed.

---

## 1. Module E — Scenario Simulation

### 1.1 "Copied analytical state," concretely

The instruction is explicit: scenarios must not modify warehouse facts and must execute against a copy. The literal, correct, and *only* implementation available under ADR-004 (no ML framework, no external state-store) is: **the "copy" is an in-memory Python data structure**, not a database copy. A scenario:

1. Loads the same real baseline inputs Modules A/C/D/B's own batch scripts already load (demand series, supplier lead-time stats, current inventory positions) — read-only, via `atlas_reporting`/`atlas_decision_support`'s existing `SELECT`-only access to facts and dims.
2. Applies a **scenario transformation function** to those in-memory values (e.g., multiply demand by 1.3 for a 30% surge, add 5 days to a supplier's lead time) — pure Python, no database write.
3. Feeds the transformed values through Modules A/C/D/B's **existing, frozen formula functions** (`moving_average`, `compute_stockout_probability`, `compute_backorder_probability`, `compute_policy_recommendation`, etc. — imported and called, never edited) to get scenario outputs.
4. Persists only the **scenario's own results** to new `ds_scenario`/`ds_scenario_result` tables — fact tables (`fact_orders`, `fact_inventory_snapshot`, etc.) are never written to, structurally: the `atlas_decision_support` role's grants don't even permit it (verified live in every prior module's completion report).

This satisfies "must not modify warehouse facts" by construction (no code path exists that could), and "execute against a copied analytical state" literally (the copy is the Python values in memory during the scenario's computation, discarded after).

### 1.2 Pre-computed scenario library, not live user-submitted scenarios

The brief names dashboard views ("Scenario Planner," "What-if Comparison") that could imply a user types in arbitrary parameters and gets a live result. That would require a new capability this codebase does not have anywhere today: **every existing dashboard route is read-only** (`main.py`'s CORS middleware allows only `GET`; every API module connects via the read-only `atlas_reporting` role). Adding a live, synchronous, user-triggered write path means a new POST-capable route, a new write-credentialed API connection, and new request-validation/abuse-scoping concerns — a real architectural expansion, not a natural extension of the existing pattern.

**Decision**: Module E follows every prior Phase 7 module's established shape exactly — a batch script (`run_module_e.py`) precomputes a **curated, representative library** of named scenarios (the types the brief lists: demand surge, demand decline, supplier disruption, lead-time inflation, warehouse outage, inventory policy change, service-level target change, and multi-factor combinations), each at 2-3 representative parameter values, persisted once, then the dashboard's "Scenario Planner" and "What-if Comparison" views **browse and compare** these precomputed scenarios (GET-only, matching every other view in this application). This is a disclosed, deliberate scope decision, not an oversight: it satisfies every literal requirement (support these scenario types; compare them side-by-side; full explainability) without introducing a live-write capability the rest of the platform doesn't have. Extending to live, user-parameterized submission is a natural, separately-scoped future capability, not built here.

### 1.3 Scenario catalog (what gets precomputed)

| Scenario type | Parameter(s) | Representative values |
|---|---|---|
| `demand_surge` | % increase to `avg_daily_demand` | +20%, +50% |
| `demand_decline` | % decrease to `avg_daily_demand` | −20%, −40% |
| `supplier_disruption` | % increase to a supplier's `lead_time_stddev_days` and `avg_lead_time_variance_days` | +50%, +100% (simulates a supplier becoming unreliable) |
| `lead_time_inflation` | days added to `lead_time_days` | +5, +10 |
| `warehouse_outage` | % of a warehouse's `avg_daily_demand` treated as unfulfillable for N days | 100% outage, 7 days |
| `inventory_policy_change` | target service level override | 90%, 99% (reuses Module B's own `SENSITIVITY_TARGET_SERVICE_LEVELS`) |
| `service_level_target_change` | Module D's implicit target reframed as a stricter/looser stockout tolerance | tighter (half the population rate), looser (double) |
| `combined` | any two of the above, composed | demand surge + lead-time inflation (a realistic joint stress case) |

Each scenario recomputes, **for the same 2,290 qualifying (product, warehouse) pairs Modules A/D/B already use**: stockout probability (Module D's formula), backorder probability (Module D's formula), inventory investment (Module B's safety-stock × unit-cost), service level (1 − stockout probability, aggregated), procurement volume (Module A's forecasted demand, aggregated), and supplier utilization (which suppliers' lead-time inputs were perturbed and by how much). All compared against the **baseline** — the real, unperturbed Modules A/D/B outputs already persisted — computed once per scenario run, not re-derived per comparison.

### 1.4 Validation, concretely

- **Deterministic replay**: running the same scenario definition twice produces byte-identical results — true by construction (no randomness anywhere in Modules A/C/D/B's formulas, confirmed across all four completion reports), proven by a unit test that runs a scenario twice and asserts equality.
- **Baseline equivalence**: a "null scenario" (zero perturbation) must reproduce the real baseline outputs exactly — the strongest possible proof the transformation pipeline doesn't silently corrupt data even when it changes nothing.
- **Sensitivity validation**: within one scenario type, a larger perturbation must move outputs in the theoretically correct direction (e.g., `demand_surge +50%` must show *higher* stockout probability than `demand_surge +20%`) — checked directly against real computed results, not asserted.
- **Scenario reproducibility**: the persisted `ds_scenario` row's parameters fully determine its `ds_scenario_result` rows — re-running `run_module_e.py` deletes and reinserts by `(scenario_id)`, the same idempotent delete-then-insert pattern every prior module uses.

## 2. Module F — Route and Cost Optimization

### 2.1 Real data findings that shaped this design (checked before any formula was written)

- **`dim_carrier.vehicle_cost_per_mile` is a real, quoted, DDL-native rate — but it's determined entirely by `vehicle_type_code`, not by individual carrier.** VAN=$1.10/mile (9 carriers), BOX_TRUCK=$1.75/mile (8 carriers), SEMI_TRAILER=$2.50/mile (8 carriers) — every carrier of the same type charges the *exact* same rate. Confirmed directly, not assumed.
- **Individual carriers of the same vehicle type are statistically indistinguishable in transit time**: all nine VAN carriers average 3.38 ± 0.01 days — no genuine reliability differentiation to select on.
- **Transit time doesn't vary by vehicle type either** (VAN 3.3821 / BOX_TRUCK 3.3818 / SEMI_TRAILER 3.3829 days, effectively identical). This is the load-bearing fact behind §2.2's service-level-neutrality claim.
- **Consequence, disclosed rather than glossed over**: "carrier selection" in the sense of picking a better-priced or more-reliable carrier *among carriers of the same vehicle type* is a genuinely degenerate optimization in this dataset — the same category of finding as Module C's zero-variance `fill_rate` and Module D's near-constant `transit_days`. The real, actionable cost lever this data supports is **vehicle-type right-sizing**: matching each shipment's actual quantity to the *cheapest vehicle type with sufficient capacity*, since transit time is provably unaffected by which type is used.
- **Every shipment resolves to real order-line quantities** (`fact_orders.shipment_number`, 0 unmatched shipments out of 696,747) — shipment sizes are typically small (single-digit units per the sampled rows), while even the cheapest vehicle type (VAN, 500-unit capacity) comfortably covers the overwhelming majority — meaning a large, real mismatch between shipment size and assigned vehicle cost is plausible and checked directly, not assumed, in Module F's methodology report.
- **`distance_miles` varies even for the same (origin warehouse, destination customer) pair** (confirmed: up to 45 distinct distance values for one pair) — it is not a fixed lane property in this simulation. Consolidation-savings estimates therefore use the **average distance_miles within each consolidation group**, disclosed as an approximation, not a fixed-lane assumption.
- **98,213 real (origin, destination, ship-date) groups have more than one shipment** — a large, real, verified consolidation opportunity pool, not a hypothetical one.

### 2.2 The resulting methodology

Two closed-form, deterministic heuristics — no external optimization engine (no linear programming, no OR-tools), per instruction:

1. **Vehicle right-sizing**: for each shipment, resolve its quantity (`SUM(fact_orders.allocated_quantity)` via `shipment_number`), find the cheapest vehicle type whose `vehicle_capacity_units` covers it, and compare its cost (`distance_miles × cheapest_sufficient_rate`) to the shipment's actual cost. A gap is a recommendation, with **provable service-level neutrality**: transit time doesn't depend on vehicle type in this dataset (§2.1), so a right-sizing recommendation carries zero disclosed service-level risk — the strongest form of the required "service-level impact validation."
2. **Shipment consolidation**: group same-day, same-origin, same-destination shipments; where a group's combined quantity still fits a single (possibly larger) vehicle, compare the group's real total cost to one consolidated shipment's estimated cost at the group's average distance. A large enough gap is a recommendation.

"Carrier selection" and "route efficiency" are **folded into right-sizing**, not built as separate, hollow metrics against data that doesn't support them — disclosed explicitly in `docs/phase7-module-f-completion.md`, the same choice Module D made when a parametric formula didn't fit real data and Module C made when `fill_rate` had zero variance.

**Warehouse allocation**, reframed for a real, confirmed constraint: this dataset is single-warehouse-per-product (established in Module A/D's own findings — every product resolves to exactly one warehouse), so *reassigning which warehouse serves a product* isn't an actionable lever here. "Warehouse allocation impact" instead means: which warehouses' *outbound* shipments carry the most right-sizing/consolidation opportunity — a real, warehouse-scoped rollup of §2.2's two metrics, not a network-flow reallocation the data can't support.

### 2.3 Validation, concretely

- **Recommendation consistency**: re-running the batch produces byte-identical recommendations (idempotent, deterministic formulas, no randomness).
- **Cost reconciliation**: every recommendation's claimed savings is `actual_cost − recommended_cost`, computed directly from persisted `dim_carrier.vehicle_cost_per_mile` and `distance_miles` — independently re-derivable from the same warehouse data by any reviewer, not a black-box number.
- **Service-level impact validation**: proven neutral, directly (§2.1's transit-time-invariance finding), not merely asserted — the completion report shows the actual query and result.
- **Explainability validation**: every recommendation carries `contributing_factors` (shipment quantity, current vehicle type/cost, recommended type/cost, distance) and a generated `business_rationale` sentence, the same pattern Module B established.

## 3. New tables (both modules, `atlas_olap`)

| Table | Module | Purpose |
|---|---|---|
| `ds_scenario` | E | One row per precomputed scenario definition (type, parameters, description) |
| `ds_scenario_result` | E | One row per (scenario, product, warehouse): projected outputs vs. baseline |
| `ds_optimization_recommendation` | F | One row per shipment or consolidation-group recommendation |
| `ds_experiment_run` (reused) | E, F | Validation metrics — the same shared, module-agnostic table every prior module uses |

`ds_model_registry` gains two new `module` values: `scenario_simulation` (E) and `route_cost_optimization` (F) — the same registry every prior module reuses, not a new mechanism.

## 4. Version traceability

Every `ds_scenario_result` and `ds_optimization_recommendation` row carries `source_forecast_model_id`, `source_supplier_model_id`, `source_service_level_model_id`, and (for Module E's inventory-policy-touching scenarios) `source_inventory_policy_model_id` — literally Modules A/C/D/B's active `ds_model_registry.id` values at computation time, the same pattern every prior module established, extended to a fourth upstream dependency.

## 5. Dashboard integration plan

Five new views under a `(scenarios)` planning route group, all read-only (`GET`), role-gated to `supply_planner`/`administrator`:

- **Scenario Planner** — browse the precomputed scenario library, grouped by type.
- **What-if Comparison** — select 2+ scenarios (plus baseline), see projected stockouts/backorders/investment/service-level side by side.
- **Inventory Impact** — a scenario's effect on Module B's safety-stock/reorder-point outputs.
- **Supplier Impact** — a scenario's effect on Module C-derived supplier utilization/risk exposure.
- **Transportation Impact** — Module F's right-sizing/consolidation recommendations, filterable by warehouse.

## 6. What this document deliberately does not do

Per instruction, Modules A, B, C, D are not touched — every function this phase calls from them is imported, never edited. EOQ remains out of scope (Module F's cost formulas are shipment-level, not reorder-quantity optimization — a different question, still blocked on the same undefined ordering-cost inputs). No external optimization solver is introduced anywhere. Live, user-parameterized scenario submission is named as a disclosed future extension, not built in this pass.
