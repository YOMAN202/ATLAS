# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7 — Decision Intelligence and Optimization: Review Checklist

**Status: PROPOSAL — AWAITING APPROVAL — 2026-08-13**
*Companion to `docs/phase7-architecture.md` and `docs/phase7-roadmap.md`. Use this to gate each module's completion, and the phase's overall completion, the same way `docs/phase5-validation.md` and `docs/phase6-completion.md`'s acceptance-criteria tables gated those phases.*

---

## A. Frozen-boundary compliance (check before any module is considered done)

- [ ] No change to `simulation/*`
- [ ] No change to `etl/warehouse_ddl/*.sql` (the 6 facts, 7 dimensions, 1 summary table)
- [ ] No change to `etl/pipeline.py`, `etl/stage_b.py`, or any existing ETL transform/load/reconcile module
- [ ] No change to any existing dashboard page (`frontend/app/(executive|operations|admin)/*`)
- [ ] No change to any existing API route's request/response contract (`backend/app/api/v1/{executive,sales,inventory,procurement,supplier,operational,data_quality}.py`)
- [ ] `atlas_reporting`'s grants are unchanged except strictly additive `SELECT` grants on new `ds_*` tables — never write access to anything
- [ ] `atlas_app`/`atlas_etl` roles untouched

## B. Explainability (FR-8.1, FR-8.4 — the load-bearing requirement of this whole phase)

For **every** recommendation/prediction row produced by **every** module:

- [ ] The row itself contains the named input features used (not a reference to an external, undocumented feature set)
- [ ] The row itself contains or references the exact calculation/formula (not a similarity score, not a fitted-model coefficient with no formula behind it)
- [ ] The row itself contains a confidence measure, and that measure's derivation is documented (e.g. "±1.96×historical RMSE," not an unexplained number)
- [ ] The row itself contains, or is traceable via FK to, the business rationale (which rule, which threshold, which model version)
- [ ] A reviewer unfamiliar with the code could reconstruct the recommendation by hand from the row's own columns plus the documented formula — this is the actual test for "no black-box outputs," not a subjective judgment call

## C. No generative AI / no ML framework (SRS §17, §21; ADR-004)

- [ ] No call to any third-party generative-AI API (OpenAI, Anthropic, etc.) anywhere in `backend/app/decision_support/`
- [ ] No ML framework dependency added to `backend/requirements.txt` (no scikit-learn, no TensorFlow/PyTorch, no XGBoost/LightGBM) unless a future ADR explicitly revisits ADR-004 — statistical methods only (moving average, exponential smoothing, seasonal-naive, weighted-formula scoring)
- [ ] No natural-language interface, chatbot, or NL-to-SQL layer

## D. Reproducibility and versioning

- [ ] Every model run is recorded in `ds_model_registry` with its exact parameters (JSON), not just a name
- [ ] Re-running the same model against the same `etl_run_id`'s warehouse state produces byte-identical output (deterministic — no unseeded randomness anywhere, matching this project's SCD2/ETL determinism discipline from Phase 5)
- [ ] Every `ds_*` prediction/recommendation row records which `etl_run_id` (warehouse state) and which `model_id` (registry entry) produced it

## E. Evaluation (SRS §15 Planning KPIs: "Forecast accuracy (MAPE), reorder recommendation acceptance rate")

- [ ] Every forecasting model in `ds_model_registry` has at least one `ds_experiment_run` row before `is_active = 1`
- [ ] Every experiment's backtest uses walk-forward validation against real historical `fact_orders` data — not synthetic/toy data
- [ ] Every experiment records a baseline (seasonal-naive) MAPE alongside the candidate model's MAPE, so "this model is actually better than doing nothing" is provable from the row, not asserted in a comment
- [ ] Supplier risk scores (Module C) and stockout risk (Module D) have a documented validation approach appropriate to their type (e.g., risk score correctly flags suppliers with known historical performance degradation in the validated dataset) even though MAPE doesn't apply to them directly

## F. Security

- [ ] `atlas_decision_support` role exists with `SELECT` on all of `atlas_olap` and `SELECT/INSERT/UPDATE/DELETE` only on enumerated `ds_*` tables (verified live against the database, the same way Phase 6 §4 verified `atlas_reporting` — not just by code review)
- [ ] No dashboard-facing endpoint under `/api/v1/decision-support/` accepts write operations from the frontend — recommendations are computed by the decision-support module's own batch process, never by a user-triggered write through the API
- [ ] Every new API route has a `require_role(...)` check, following Phase 6's pattern exactly

## G. Disclosed gaps stay disclosed (don't silently resolve them with an assumption)

- [ ] EOQ remains `NULL` with a documented reason in `ds_reorder_recommendation` until order-cost/holding-cost policy values are supplied — no invented cost assumption substituted quietly
- [ ] Target service level default (95%) is recorded per-recommendation, not hardcoded invisibly — an override path exists even if unused initially
- [ ] Shipment fulfillment-delay prediction remains explicitly out of Module D's scope, with the same `estimated_delivery_date`-is-NULL reason Phase 6 already documented — not silently re-attempted with a workaround that produces a misleading number

## H. Scenario Simulation (Module E) stays a stub

- [ ] `ds_scenario_definition`/`ds_scenario_result` schema exists (if implemented at all this phase) but no simulation engine logic is written
- [ ] Nothing under Module E writes to any non-`ds_scenario_*` table, ever (BR-7, extended per architecture §5)

## I. Overall Phase 7 architecture-stage completion (this document's actual gate)

Phase 7's **architecture stage** (this document + `docs/phase7-architecture.md` + `docs/phase7-roadmap.md`) is complete when:

- [ ] You have reviewed and approved `docs/phase7-architecture.md`
- [ ] You have reviewed and approved `docs/phase7-roadmap.md`'s module sequencing and first-module recommendation (or redirected it)
- [ ] All three Phase 7 planning documents are committed
- [ ] No model implementation has begun (per your explicit instruction — this checklist exists to be used *during* implementation, not to imply implementation already started)
