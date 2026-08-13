# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7 — Decision Intelligence and Optimization: Architecture

**Status: ARCHITECTURE PROPOSAL — AWAITING APPROVAL — 2026-08-13**
*Sources of truth: `ATLAS-SRS.md` §6.5/§6.8/§6.9/§15/§17/§21 (FROZEN), `ATLAS-TDD.md` ADR-004 + Decision Support Module (FROZEN), `ATLAS-Roadmap.md` Phase 7 (FROZEN), `docs/phase6-completion.md`, `docs/phase5-validation.md`*

This is a design document only. No model, table, or endpoint has been implemented. Per your instruction, the simulation engine, warehouse schema, ETL architecture, dashboard architecture, and Phase 6 API contracts are all frozen inputs to this phase, not things this phase modifies.

---

## 1. Frozen constraints this architecture must honor

Stated explicitly, not left implicit, because they shape nearly every decision below:

- **No generative AI anywhere in this layer.** Three independent places in the frozen SRS say this: §17 Constraints ("No generative AI in the decision-support or scenario-analysis layer; all outputs must be rule/statistics-based and explainable"), §21 Out of Scope ("Generative-AI-based recommendations, scenario generation, or natural-language interfaces"), and Business Objective B5 ("Demonstrate explainable, rule-based decision-support analytics (no generative AI)"). FR-5.1 embeds it a fourth time: demand forecasts must be "statistical, not generative-AI based."
- **No ML framework for forecasting (ADR-004, already decided).** `ATLAS-TDD.md`: "Statistical forecasting (e.g. moving average / exponential smoothing implemented directly in SQL or Python) rather than a full ML pipeline." This isn't a choice this document makes — it's a frozen decision this document implements.
- **No black-box outputs (FR-8.4).** "Every recommendation shall be traceable to the underlying data and rule that produced it." This is the single most load-bearing requirement in this whole phase — it shapes the table schemas in §5, not just a documentation afterthought.
- **Supplier risk score is batch, not real-time (BR-4).** Recomputed per ETL cycle, warehouse-derived.
- **Scenario analysis is explicitly Phase 2/post-MVP** (SRS line 6, Roadmap line 526) — confirmed with you (§8 below) as deferred: this architecture designs its *interface shape* only, not an engine.
- **This phase does not touch**: `simulation/`, `etl/warehouse_ddl/*.sql` (the 6 facts + 7 dims + 1 summary), `etl/pipeline.py` and friends, `frontend/app/(executive|operations|admin)/*` and their existing routes, or any existing `backend/app/api/v1/*.py` route's contract. Everything here is additive — new tables, new read-mostly role, new routers, new dashboard route group.

## 2. Design decisions (the gaps the frozen spec leaves open, resolved with reasoning — same discipline as ADR-015 through ADR-022 in Phase 5)

**Where do new Phase 7 tables live?** In `atlas_olap`, alongside the warehouse and ETL-metadata tables, not a new schema. This mirrors ADR-015's exact reasoning from Phase 5: the Master Prompt's communication matrix doesn't grant a decision-support process write access to `atlas_oltp`, and inventing a fourth schema the frozen spec never calls for repeats a mistake already avoided once. New tables are **not** named `fact_*`/`dim_*` (they aren't part of the Kimball star schema — they're derived, model-produced data, same category as `etl_run_log`) — prefixed `ds_` (decision support) instead, so `SHOW TABLES` cleanly separates "the warehouse" from "what's built on top of it."

**Who can write these new tables?** A new MySQL role, `atlas_decision_support`: `SELECT` on all of `atlas_olap` (it needs to read every fact/dim to compute anything) plus `SELECT, INSERT, UPDATE, DELETE` on the specific `ds_*` tables only (enumerated per-table `GRANT`s, since MySQL has no prefix-wildcard grant — verbose but explicit, and explicitness is the point). This is the same least-privilege pattern as `atlas_reporting` (SEC-3), extended rather than reused, because `atlas_reporting` is contractually read-only everywhere (Phase 6 §4) and must stay that way — giving it write access anywhere, even to new tables, would be exactly the kind of contract change you told this phase not to make.

**How do dashboards/API see this without changing Phase 6's contracts?** New routers only: `backend/app/api/v1/decision_support/*.py`, mounted at a new prefix (`/api/v1/decision-support/...`), using `atlas_decision_support`'s connection for writes (model runs) and read endpoints, following the exact request/response/caching/role patterns `backend/app/api/deps.py` and `backend/app/api/cache.py` already established — reused, not reinvented. No existing route in `backend/app/api/v1/{executive,sales,inventory,procurement,supplier,operational,data_quality}.py` changes. A new frontend route group, `frontend/app/(planning)/`, is additive to the existing role-based nav (the Supply Planner role already exists in `frontend/lib/roles.ts` and was scaffolded-but-empty in Phase 6 precisely for this).

**What does "model registry" and "experiment tracking" mean without an ML framework?** Given ADR-004, there is no model *artifact* to serialize (no `.pkl`, no ONNX, no MLflow) — a "model" here is a named statistical method plus its parameters (e.g., `exponential_smoothing, alpha=0.3` or `moving_average, window=14`). The registry (`ds_model_registry`, §5) tracks *which parameterization* produced a given forecast, and experiment tracking (`ds_experiment_run`) tracks *backtested accuracy* per parameterization so one can be promoted to active — a lightweight, warehouse-native substitute for MLOps tooling that a heavier framework would provide, sized to what four statistical methods actually need.

**EOQ needs order cost and holding cost — neither exists in the warehouse.** Flagged explicitly rather than invented (the same discipline your Phase 6 rules required for cost-to-serve/overstock threshold): Economic Order Quantity's formula, `sqrt(2DS/H)`, needs `S` (fixed cost per order) and `H` (annual holding cost per unit) as *policy inputs* — no fact table has "cost to place an order" or "cost to hold one unit for a year." Module B (§5) computes reorder point and safety stock (which only need forecasted demand, lead time, and a target service level — all derivable) but **does not compute EOQ** until you supply these two policy values or approve a documented default. Stated as a real gap, not silently defaulted.

**What target service level does safety stock use?** Also a policy input, not a warehouse fact. Proposed default — **95%** (z ≈ 1.65), a conventional supply-chain default — but exposed as a parameter on every reorder-point computation (not hardcoded into the formula), and every recommendation's output row records which service level it was computed for. You can override the default per product/category later without an architecture change.

## 3. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  atlas_olap (existing, frozen)                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐│
│  │ 7 dimensions │  │ 6 facts +    │  │ etl_run_log,             ││
│  │ (dim_*)      │  │ 1 summary    │  │ etl_run_table_metrics,   ││
│  │              │  │ (fact_*)     │  │ dq_quarantine, etc.      ││
│  └──────┬───────┘  └──────┬───────┘  └─────────────────────────┘│
└─────────┼──────────────────┼──────────────────────────────────────┘
          │ read-only         │ read-only
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Feature layer (SQL views, computed on read — §4)                │
│  daily demand by SKU/warehouse, lead-time stats, on-time trend    │
└──────────────────────────┬──────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Decision Support Module (new — backend/app/decision_support/)   │
│  Module A: Forecasting   │ Module B: Inventory Optimization       │
│  Module C: Supplier Risk │ Module D: Service-Level Prediction     │
│  Module E: Scenario (stub interface only) │ Module F: Route (low) │
│  ─────────────────────────────────────────────────────────────  │
│  ds_model_registry, ds_experiment_run  (registry + evaluation)   │
└──────────────────────────┬───────────────────────────────────────┘
                            │ writes (atlas_decision_support role)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  atlas_olap: ds_demand_forecast, ds_reorder_recommendation,       │
│  ds_supplier_risk_score, ds_stockout_risk, ds_scenario_* (stub)   │
└──────────────────────────┬───────────────────────────────────────┘
                            │ read-only (new atlas_decision_support
                            │ SELECT grant, or atlas_reporting extended
                            │ — see §6)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  New API routers (backend/app/api/v1/decision_support/*.py)      │
│  Existing Phase 6 routers: UNCHANGED                              │
└──────────────────────────┬───────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  frontend/app/(planning)/  — new route group, Supply Planner role │
│  Existing Phase 6 dashboards: UNCHANGED                           │
└─────────────────────────────────────────────────────────────────┘
```

## 4. Feature engineering layer

Not a feature *store* (no ML framework needs one) — a set of SQL views computing derived signals directly from the existing warehouse, read-only, so every module reads the same, consistently-defined inputs instead of six modules each reimplementing "what's the average lead time" slightly differently:

| View | Source | Computes |
|---|---|---|
| `v_daily_demand` | `fact_orders` | `allocated_quantity` summed per `(product_key, fulfillment_warehouse_key, order_date_key)` — the base series every forecast is built from |
| `v_demand_calendar_features` | `v_daily_demand` joined `dim_date` | day-of-week, `is_weekend`, month, quarter — `dim_date` already carries these (Phase 4), reused not recomputed |
| `v_lead_time_stats` | `fact_supplier_delivery` | mean/stddev of `lead_time_variance_days` per `(supplier_key, product_key)`, trailing-window and all-time |
| `v_supplier_performance_trend` | `fact_supplier_delivery` | rolling on-time rate and quality-rejection rate, most-recent-N-deliveries vs. all-time — the "becoming unreliable" signal (a degrading trend, not just a low average) |
| `v_inventory_position` | `fact_inventory_snapshot` | latest `quantity_on_hand`/`quantity_available` per `(product_key, warehouse_key)`, already the pattern Phase 6's Operational dashboard uses for capacity |

## 5. Prediction and recommendation tables (`ds_*`, all in `atlas_olap`)

Every one of these follows the same shape, deliberately, because FR-8.4 applies to all of them identically: the predicted/recommended value, **named contributing-factor columns** (not a black-box `score`), a confidence measure, and versioning back to the model that produced it.

### `ds_model_registry`
`model_id` (PK), `module` (A/B/C/D/F), `model_name` (e.g. `exponential_smoothing`, `moving_average_14d`, `seasonal_naive`), `parameters` (JSON — e.g. `{"alpha": 0.3}`), `is_active`, `created_at`, `created_by_experiment_id`.

### `ds_experiment_run`
`experiment_id` (PK), `model_id` (FK), `train_start_date`, `train_end_date`, `test_start_date`, `test_end_date` (walk-forward backtest windows — real, not synthetic, since 365 real validated days exist), `metric_name` (`MAPE`, per SRS §15), `metric_value`, `baseline_metric_value` (naive-forecast MAPE, so "better than doing nothing" is provable, not assumed), `run_at`.

### `ds_demand_forecast` (Module A)
Grain: one row per `(product_key, warehouse_key OR region_key OR NULL-for-total, forecast_date, model_id)`. Columns: `predicted_quantity`, `confidence_interval_low`, `confidence_interval_high` (from the model's own residual distribution — e.g. ±1.96×historical RMSE for a 95% interval, itself explainable, not a fabricated number), `model_id` (FK to registry), `generated_at`, `etl_run_id` (which warehouse state this forecast was computed from — the same "as of" discipline Phase 6's API responses use).

### `ds_reorder_recommendation` (Module B)
Grain: one row per `(product_key, warehouse_key, generated_at)`. Columns: `recommended_reorder_point`, `recommended_safety_stock`, `target_service_level` (the policy input, recorded not assumed), `avg_daily_demand_used`, `lead_time_days_used`, `lead_time_stddev_used` (every input to the formula, so "reason, contributing factors" per FR-8.1 is the row itself, not a separate explanation system), `demand_forecast_id` (FK — which forecast this was computed from), `eoq` (nullable — populated only once §2's cost-input gap is resolved).

### `ds_supplier_risk_score` (Module C)
Grain: one row per `(supplier_key, etl_run_id)` — BR-4's "recomputed per ETL cycle." Columns: `risk_score` (0–100, a documented weighted formula over the next three columns — weights stated in code and in this doc, not hidden), `on_time_rate`, `quality_rejection_rate`, `lead_time_variance_days`, `trend_direction` (improving/stable/degrading, from `v_supplier_performance_trend`), `triggering_metrics` (JSON list of which specific thresholds were crossed — directly satisfies FR-8.2's "specific metrics that triggered the alert").

### `ds_stockout_risk` (Module D)
Grain: one row per `(product_key, warehouse_key, as_of_date)`. Columns: `stockout_risk_level` (Low/Medium/High from forecasted demand vs. current position, not a probability from a fitted classifier — statistical, explainable), `days_of_supply_remaining`, `forecast_id_used` (FK), `backorder_risk_level` (from `fact_orders.backordered_quantity` trend). Shipment/fulfillment-delay prediction is **not implemented for `fact_shipments`**: Phase 6 found `estimated_delivery_date` NULL for 100% of shipments at the OLTP source (`docs/phase6-completion.md` §2), so "delay vs. estimate" can't be computed there any more than `is_on_time` could be — this table's fulfillment-delay coverage is PO-delivery delay (`fact_supplier_delivery`, fully populated) only, disclosed here rather than silently scoped down.

### `ds_scenario_definition` / `ds_scenario_result` (Module E — interface only, §8)
Schema shape defined, no population logic: `scenario_id`, `scenario_type` (`supplier_delay`, `demand_surge`, `capacity_reduction`, `lead_time_change` — matching SRS FR-9.1's own enumeration), `parameters` (JSON), `is_hypothetical` (always `TRUE`, enforced — BR-7: "Scenario analyses never write to production OLTP or baseline warehouse tables," extended here to mean never write to the *real* `ds_*` tables either, only to these clearly-separate, clearly-labeled ones).

### `ds_route_efficiency` (Module F — lower priority, §8)
Grain: one row per `(carrier_key, origin_warehouse_key, generated_at)`. Columns: `avg_cost_per_mile`, `avg_transit_days`, `efficiency_rank`, from `fact_shipments` + `dim_carrier.vehicle_cost_per_mile` — the same source columns Phase 6's Operational dashboard already surfaces, just aggregated and ranked rather than shown raw.

## 6. Security (extends SEC-3, doesn't touch it)

```sql
CREATE USER 'atlas_decision_support'@'%' IDENTIFIED BY '...';
GRANT SELECT ON atlas_olap.* TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_model_registry TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_experiment_run TO 'atlas_decision_support'@'%';
-- ...one GRANT per ds_* table, enumerated, not a schema wildcard.
```

`atlas_reporting` (Phase 6's dashboard role) gets **additive** `SELECT` grants on the new `ds_*` tables once they exist, so the Planning dashboard can read predictions the same read-only way it reads everything else — `atlas_reporting` never gains write access to anything, anywhere, which is the one invariant from Phase 6 this phase must not touch.

## 7. Evaluation framework

Every model in the registry is backtested before `is_active = 1`, using genuine walk-forward validation against the real 365-day dataset (not synthetic data — the validated Phase 5 warehouse is the evaluation set): train on an early window, forecast a held-out later window, compare to `fact_orders`' actual `allocated_quantity`, compute MAPE. A model is only promoted if its MAPE beats a **seasonal-naive baseline** (forecast = same day last period) — recorded in `ds_experiment_run.baseline_metric_value` so "this model is worth using" is a provable comparison, not an assumption. This directly implements SRS §15's named Planning KPI ("Forecast accuracy (MAPE)") as the evaluation gate, not just a dashboard number computed after the fact.

## 8. Explicitly deferred / scoped down (per your decisions this session)

- **Module E (Scenario Simulation)**: interface schema only (§5); no simulation engine. The frozen SRS designates this Phase 2/post-MVP; this architecture respects that sequencing rather than overriding it.
- **Module F (Route/Cost Optimization, FR-8.3)**: included (§5's `ds_route_efficiency`) but explicitly lower priority than A–D in the roadmap (`docs/phase7-roadmap.md`) — not dropped, not silently missing, just sequenced last.
- **EOQ** (part of Module B): not computed until order-cost/holding-cost policy inputs are supplied (§2).
- **Fulfillment-delay prediction for shipments** (part of Module D): not computed — inherits Phase 6's `estimated_delivery_date` data gap.

## 9. What this architecture explicitly does not include

No generative AI, no third-party ML framework/API call, no natural-language interface, no black-box model of any kind (every model is a named, documented statistical method with inspectable parameters) — per SRS §17/§21 and ADR-004, restated here as a design commitment, not just a constraint being worked around.
