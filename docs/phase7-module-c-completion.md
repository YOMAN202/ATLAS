# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7 Module C — Supplier Intelligence: Completion & Validation Report

**Status: MODULE C COMPLETE — 2026-08-14**
*Sources of truth: `docs/phase7-architecture.md`, `docs/phase7-roadmap.md`, `docs/phase7-review-checklist.md`, `docs/phase7-module-a-completion.md` (Module A, approved and frozen)*

Module C (Supplier Intelligence) is implemented, validated against the real warehouse, and integrated into the Planning dashboard alongside Module A. Per your instruction, Module A's forecasting architecture, feature layer, backtesting methodology, MAPE framework, and the `moving_average_14d` baseline are frozen and untouched by this work — Module C is purely additive. This report is the gate before Module D; nothing beyond Module C has been built.

---

## 1. Supplier scoring methodology

A composite 0–100 risk score built from four named, weighted components — a documented formula, never a fitted classifier, per ADR-004/SRS §17's "no black-box outputs":

| Component | Weight | Raw signal |
|---|---:|---|
| On-time reliability | 0.35 | `1 − on_time_rate` |
| Quality | 0.30 | `quality_rejection_rate` |
| Delivery variability | 0.20 | `lead_time_stddev_days` |
| Trend | 0.15 | `max(0, prior_90d_on_time_rate − recent_90d_on_time_rate)` |

**Population-relative min-max normalization.** Each component is normalized to its own observed 0–100 range across the current supplier population *before* weights are applied (`backend/app/decision_support/supplier_scoring.py::_minmax_normalize`). This is not cosmetic: the raw metrics have very different natural scales in this dataset — on-time rate spans 87.0–96.1% (a ~9-point range) while quality rejection spans only 1.64–2.29% (a ~0.65-point range) and lead-time stddev spans 0.59–1.11 days. Applying the stated weights directly to raw values would let variability silently dominate the score regardless of its 0.20 weight, purely from unit scale — a real and easy way for a "documented, explainable" formula to secretly not do what its own documentation claims. Normalizing first means the stated weights are what actually control the score.

**Classification bands**: Low ≤ 33, Medium ≤ 66, High > 66.

**A real dataset finding, disclosed rather than hidden**: `fill_rate` (`received_quantity / ordered_quantity`) is exactly **1.0000 for all 100 suppliers** — zero variance, confirmed directly against the warehouse (`fact_supplier_delivery` only contains lines that were actually delivered; this simulation doesn't model partial shipments). A constant contributes nothing to a weighted score, so it is excluded from scoring — but still reported on every output row, satisfying the "fulfillment performance" requirement as a transparent metric rather than a scored one.

**Trend delta is reported as the real signed value, never floored in the output.** Only the *scoring* input floors decline-vs-improvement at zero (an improving supplier should never earn negative risk, but should also never look identical to a flat one). `on_time_rate_trend_delta` on every row is the true `prior − recent` value — negative for genuine improvement, positive for decline — so a Supply Planner reading the detail table sees an accurate number, not a value silently clamped to zero. See §9 for how this was caught.

## 2. Validation report

There is no forecast/ground-truth to backtest a risk score against the way Module A backtests a forecast, so validation instead asks: **does the formula behave the way its own documentation claims?** (`backend/app/decision_support/supplier_validation.py`, using Python 3.10+ stdlib `statistics.correlation` — no new dependency).

Real correlation results, computed against all 100 real suppliers:

| Check | Result | Expected sign | Pass |
|---|---:|:---:|:---:|
| `risk_score` vs. `on_time_rate` | −0.8331 | negative | ✅ |
| `risk_score` vs. `quality_rejection_rate` | +0.2839 | positive | ✅ |
| `risk_score` vs. `lead_time_stddev_days` | +0.7741 | positive | ✅ |
| `risk_score` vs. `on_time_rate_trend_delta` | +0.3318 | positive | ✅ |

**Classification distribution**: 18 Low, 78 Medium, 4 High (of 100 suppliers). **Trend distribution**: 76 stable, 13 degrading, 11 improving.

**Spot-check of the 4 High-risk suppliers** confirms the scores are individually explainable, not just statistically plausible in aggregate:

| Supplier | Score | On-time | Quality rejection | Lead-time stddev | Trend | Triggering metrics |
|---:|---:|---:|---:|---:|---|---|
| 20 | 76.46 | 87.0% | 2.00% | 1.08 | degrading (+6.5%) | on-time decline, top-third variability |
| 27 | 74.57 | 87.8% | 2.09% | 1.10 | stable | quality above threshold, top-third variability |
| 30 | 73.88 | 89.3% | 2.10% | 1.10 | degrading (+7.9%) | quality above threshold, on-time decline, top-third variability |
| 72 | 68.16 | 88.5% | 2.01% | 1.04 | degrading (+5.2%) | quality above threshold, on-time decline, top-third variability |

Every High/Medium-risk supplier's `triggering_metrics` names the exact threshold(s) crossed, independently verifiable against the raw feature values on the same row — the concrete mechanism behind FR-8.2's "specific metrics that triggered the alert."

**Real population ranges** (min–max, all 100 suppliers): on-time rate 87.0–96.1% (avg 92.06%); quality rejection 1.64–2.29%; lead-time stddev 0.59–1.11 days; trend delta −10.33% to +16.13%.

## 3. API integration

Two new read-only endpoints (`backend/app/api/v1/supplier_risk.py`), mounted at `/api/v1/dashboards/planning/supplier-risk/`, role-gated to `supply_planner`/`administrator`, following Module A's `forecast.py` pattern exactly:

| Endpoint | Purpose | Key response fields |
|---|---|---|
| `GET /supplier-risk/summary` | Headline KPIs | Active model + weights, supplier count, average risk score, classification breakdown |
| `GET /supplier-risk/detail` | Paginated supplier rows | Filterable by `risk_classification`; every scoring input plus `triggering_metrics` |

Connects via the dashboard API's existing `atlas_reporting` role (its schema-wide `SELECT` on `atlas_olap` already covers the new `ds_supplier_risk_score` table — no new grant needed). No endpoint accepts a write; scores are populated exclusively by the batch process (§5).

## 4. Dashboard integration report

New route: `frontend/app/(planning)/supplier-risk/page.tsx`, nav-gated to `supply_planner`/`administrator`. Verified end-to-end against the real running stack via headless-browser screenshot (zero console errors, both API calls returned 200):

- KPI tiles: active scoring model + weights, suppliers scored, average risk score, high-risk count.
- A donut chart of the Low/Medium/High classification breakdown.
- A filterable (by classification), paginated detail table showing every scoring input and the human-readable `triggering_metrics` for each supplier.
- Classification filter interaction verified live (selecting "High" correctly re-queries and re-renders).

## 5. Batch process (`backend/app/decision_support/run_module_c.py`)

`python -m app.decision_support.run_module_c` — loads supplier feature views, scores every supplier, validates the scores behave as designed (refusing to persist if any correlation check fails), registers the scoring formula in `ds_model_registry` (`module='supplier_risk_scoring'`), and persists to `ds_supplier_risk_score`. Connects exclusively via `atlas_decision_support`. Idempotent: reruns delete prior scores for the same `model_id` before inserting, the same pattern Module A and `summary_daily_revenue_by_region` use. Runtime: 0.7s for 100 suppliers.

## 6. Warehouse changes

- `etl/warehouse_ddl/54_ds_supplier_risk_score.sql` — new table, grain `(supplier_key, etl_run_id)`, FK to `dim_supplier`, `model_id`/`etl_run_id` on every row.
- `etl/warehouse_ddl/55_ds_supplier_feature_views.sql` — three new read-only views: `v_supplier_delivery_stats`, `v_supplier_trend` (90-day trailing window, `DATE_SUB(MAX(full_date), INTERVAL 90 DAY)`, minimum 5 deliveries per window), `v_supplier_utilization`.
- `atlas_decision_support` granted `SELECT, INSERT, UPDATE, DELETE` on `ds_supplier_risk_score` only (per-table, no schema-wide write grant — matches Module A's pattern exactly).

## 7. Automated tests

17 new tests, all passing, plus a full regression of the existing suite:

- `backend/tests/decision_support/test_supplier_scoring_unit.py` (4 tests): hand-computable expected values — e.g. a uniformly-better supplier scores exactly 0.0 and a uniformly-worse one scores exactly 100.0 with only two data points in the population, and a population-wide constant metric normalizes to exactly 0 (not a divide-by-zero).
- `backend/tests/decision_support/test_supplier_validation_unit.py` (3 tests): correlation signs on a well-behaved population, and a deliberately-broken `ValidationResult` (wrong sign) proving the assertion actually fails loudly.
- `backend/tests/api/test_supplier_risk_api.py` (6 tests): hand-seeded `ds_model_registry`/`ds_supplier_risk_score`/`dim_supplier` rows reconciled against exact expected API responses; classification filtering; ordering; role-based access.

```
backend/tests/ (full suite, incl. Phase 6/7 regression):  157 passed
etl/warehouse_ddl/tests/:                                  17 passed
Total this session:                                       174 passed
```

## 8. Security verification (live, not just code review)

```
atlas_decision_support SELECT on atlas_olap.fact_supplier_delivery:   succeeded (20,493 rows)
atlas_decision_support INSERT/DELETE on ds_supplier_risk_score:       succeeded
atlas_decision_support DELETE on atlas_olap.fact_supplier_delivery:   ERROR 1142 — command denied
atlas_decision_support SELECT on atlas_oltp (any table):              ERROR 1044 — access denied to database
```

`SHOW GRANTS` confirms exactly 4 per-table write grants (`ds_demand_forecast`, `ds_experiment_run`, `ds_model_registry`, `ds_supplier_risk_score`) plus schema-wide `SELECT` — no schema-wide write grant exists.

## 9. Two real bugs found and fixed this session — disclosed in full

**Bug 1 — `trend_direction`'s "improving" branch was unreachable, and `on_time_rate_trend_delta` was silently zeroed for improving suppliers.** The scoring formula correctly floors the trend-risk *input* at zero (`max(0, prior − recent)`) so improvement never earns negative risk — but the original code reused that same floored value for the *reported* `trend_direction` classification and the `on_time_rate_trend_delta` output column. Since the floored value can never be negative, `trend_direction` could never be `"improving"`, and every genuinely-improving supplier's delta was reported as `0.0000` — indistinguishable from a perfectly flat supplier. This was caught by `test_trend_delta_only_penalizes_decline_never_improvement`, a hand-computable unit test written for this module, not discovered by chance. Fixed by computing a separate signed delta used only for reporting/classification, while the floored value continues to feed the score. Re-running against the real 100-supplier population after the fix: **11 suppliers are now correctly classified `"improving"`** (previously that bucket was structurally empty for every supplier in the dataset). Classification bands (Low/Medium/High counts) were unaffected — the scoring formula itself was always correct; only the trend *reporting* was wrong.

**Bug 2 — the backend container was silently running as `root`, not the least-privilege role, for the entire session.** `backend/app/core/config.py`'s `decision_support_db_url` (and `dashboard_db_url`) fall back to the root `DATABASE_URL_OLAP` connection string if their dedicated env var is unset — a deliberate fallback so local dev without the role provisioned doesn't hard-fail. The role *was* provisioned (grants existed and were correct in the database, verified earlier), but `.env` had been updated with `DATABASE_URL_OLAP_DECISION_SUPPORT`/`DATABASE_URL_OLAP_REPORTING` after the running `atlas_backend` container was created — `docker restart` doesn't re-read `env_file`, only `docker compose up` (recreate) does. This meant every dashboard query and every Module A/C batch run this session — despite being architecturally correct, correctly grant-scoped, and passing every test — was actually executing as `root` at runtime, silently defeating the least-privilege design. Fixed via `docker compose up -d --force-recreate backend`; confirmed the container now carries the correct env var, re-ran Module A and Module C end-to-end (byte-identical results to the root-connection runs, as expected — the role only affects permissions, not query results) and the full 174-test regression, then independently verified the role's actual restrictions live (§8). Worth flagging for any future container recreate/redeploy step: this class of bug is invisible to code review and even to grant verification — it only surfaces by checking the *running* container's actual environment.

## 10. Known limitations

1. **`fill_rate` cannot discriminate suppliers in this dataset** — genuinely zero variance (§1), not a formula weakness. Retained as a reported metric per the module's "fulfillment performance" requirement; would become scoring-relevant automatically if the simulation ever models partial shipments.
2. **Trend uses a fixed 90-day window with a minimum-5-delivery guard** — suppliers with too little recent/prior delivery history are excluded from scoring entirely (all 100 real suppliers cleared this bar; the guard exists for correctness on any future, sparser dataset, not because it currently filters anyone out).
3. **No time-series history of a supplier's own risk score** — each run reflects only the current `ds_supplier_risk_score` snapshot for the active model; there's no month-over-month trend-of-the-score-itself view yet (the underlying `on_time_rate_trend_delta` column does capture 90-day directional movement, just not a full score history).
4. **EOQ, safety stock, and reorder point (Module B) are not implemented** — this report is Module C only, per your explicit instruction to stop here.

## 11. Acceptance criteria — assessment

| Criterion | Status |
|---|---|
| Module A's frozen baseline (feature layer, backtesting, MAPE framework, `moving_average_14d`) left unmodified | ✅ — §9's container fix re-ran Module A only to confirm no regression; results are byte-identical to the original run |
| Includes lead-time reliability, fulfillment performance, delivery variability, on-time performance, supplier utilization, risk classification | ✅ — §1; `distinct_products_supplied`/`distinct_warehouses_served`/`total_spend`/`share_of_total_spend` cover utilization, `fill_rate` covers fulfillment (reported, not scored — §1) |
| Deterministic, explainable, reproducible, warehouse-native | ✅ — §1/§5; no ML framework, zero new dependencies, delete-then-insert idempotency |
| Measurable validation metrics | ✅ — §2, four correlation checks against real data, all passing |
| Supplier scoring methodology, validation report, API integration, dashboard integration, completion doc | ✅ — this document, §1–§4 |
| Read-only analytics layer, least-privilege write role | ✅ — §8, verified live; §9 discloses and fixes a real gap between grant design and runtime enforcement |

**Module C is complete.** Per your instruction, stopping here — Module D does not begin until you review these supplier intelligence results and approve.
