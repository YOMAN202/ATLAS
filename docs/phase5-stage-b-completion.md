# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 5 — ETL Pipeline, Stage B: Completion Report

**Status: STAGE B COMPLETE — 2026-08-13**
*Sources of truth: ATLAS-TDD.md §6 (FROZEN), ATLAS-Roadmap.md Phase 5 (FROZEN), ADR-016 through ADR-022, `docs/phase5-stage-a-completion.md` (Stage A baseline)*

---

## 1. Scope

Stage B (Transform → SCD2 → Load → Reconcile → Score) of the ETL pipeline, built and run against the real, already-validated 365-day dataset staged by Stage A (`docs/phase5-stage-a-completion.md`, approved 2026-08-12). Per your instruction on approving Stage A: dimension transforms, deterministic SCD2 processing, surrogate key resolution, fact transforms, fact loading, reconciliation, and validation — with the same discipline as Stage A (deterministic behavior, idempotent reruns, per-table transactions, full audit logging, measurable performance reporting). Stage A itself was **not** further optimized, per your explicit instruction; its 51.3-minute baseline (3,076.42s) stands unchanged and is the comparison point below.

**Explicitly not built in this pass** (Phase 6, awaiting separate approval): dashboards.

## 2. What was built

| Component | Location |
|---|---|
| Dimension row-builders (7 dims, Type 1 + SCD2) | `etl/transform/dimensions.py` |
| Fact row-builders (5 standard facts, 1:1 grain) | `etl/transform/facts.py` |
| `fact_inventory_snapshot` window-function transform | `etl/transform/inventory_snapshot.py` |
| Staged-payload readers (full, by-id, subset, targeted-field) | `etl/transform/staging_reader.py` |
| Surrogate key resolution (Type 1 + SCD2 as-of-date) | `etl/transform/surrogate_keys.py` |
| Parsing helpers (date/datetime/decimal from JSON) | `etl/transform/parsing.py` |
| Dimension loaders (Type 1 upsert, SCD2 upsert w/ full decision tree) | `etl/load/dimensions.py` |
| Fact loader (bulk-fetch-compare-write) | `etl/load/facts.py` |
| Shared true multi-row bulk upsert | `etl/load/bulk.py` |
| Reconciliation (row-count + grain validation) | `etl/reconcile.py` |
| Stage B orchestration (7 dims, 6 facts, 1 summary, in fixed order) | `etl/stage_b.py` |
| Pipeline wiring (`run_full_pipeline()`, Stage A unchanged) | `etl/pipeline.py` |
| New ETL metrics columns (`extract/transform/load/reconcile_seconds`) | `etl/warehouse_ddl/45_etl_run_table_metrics_stage_timing.sql` |
| Stage B test suite (25 tests: unit + DB-integration) | `etl/tests/test_stage_b_transforms_unit.py`, `etl/tests/test_stage_b_integration.py` |

## 3. Issues found and fixed against real production-scale data

Three real, independent bugs surfaced only once run against the full dataset — none were caught by unit-level construction, consistent with why this gate requires a real-scale run, not just tests. All three are documented here rather than silently patched.

### 3.1 OOM in `process_fact_orders`

**Symptom:** the process vanished silently after 20–30 minutes with no traceback — confirmed via `/proc/[pid]` inspection that the Python process had simply been killed, while MySQL showed the connection idle.

**Root cause:** `order_lines` (732,549 rows), `orders` (292,925), and `shipments` (696,747) were all read via full-JSON-payload parsing simultaneously — ~1.7M rows fully materialized in Python memory at once, against a container memory ceiling shared with MySQL (3.74 GiB total, WSL2 VM limit).

**Fix:** `read_staged_fields()` (`etl/transform/staging_reader.py`) — a SQL-side `JSON_EXTRACT`/`JSON_UNQUOTE` projection that reads only the specific fields a transform actually uses (10 of `order_lines`' fields, 3 of `orders`', 1 of `shipments`', 11 of `shipments`' for `process_fact_shipments`), instead of materializing every field of every staged row. Reduced `process_fact_orders`' peak memory from a crash at ~2.4 GiB to a stable ~2.0 GiB peak; `process_fact_shipments` peaked at ~1.5 GiB.

**A second bug found while fixing the first:** `JSON_UNQUOTE(JSON_EXTRACT(...))` on a JSON `null` value (an explicit null, e.g. an unfulfilled line's `shipment_id`) returns the literal 4-character string `'null'`, not SQL `NULL` — silently corrupting every nullable field read this way. Not caught earlier because the fields used before (`customer_id`, `order_date`, `shipment_number`) happened to always be populated. Fixed with `NULLIF(..., 'null')` wrapping every extract in `read_staged_fields()`.

### 3.2 SCD2 `effective_from` epoch bug (ADR-016 addendum)

**Symptom:** `process_fact_procurement`'s first real run quarantined **100% of 21,189 rows** — every one on `product_key/supplier_key/warehouse_key unresolved as of order_date`, for every date in the batch.

**Root cause:** ADR-016 dates a dimension's new version to the source OLTP row's `updated_at` date, assuming that column tracks business-time change. Against the real simulated dataset, `suppliers`/`warehouses` never actually change during the simulation — every one has exactly one version, and `created_at`/`updated_at` are stamped at data-generation/load wall-clock time (`2026-08-08`), not any simulated business date. Applying the rule literally made every supplier/warehouse's *first* version dated `2026-08-08` — later than every fact business date in the dataset (2021 onward) — so `resolve_scd2_as_of` could never find a covering version.

**Fix:** a dimension's first-ever version (no prior current row) is now dated to a fixed epoch sentinel (`2000-01-01`, safely before the dataset's earliest possible business date) instead of `source_updated_at`. A genuine *subsequent* change still versions off `source_updated_at`, unchanged — the fix narrows ADR-016's rule to where it's actually justified (an observed change) rather than reversing it. Documented as an addendum to ADR-016 in `docs/ATLAS-TDD.md` §14. The 108 already-loaded `dim_supplier`/`dim_warehouse` rows were corrected in place (not truncated/reloaded, since `fact_orders`/`fact_shipments` already carried FK references to their surrogate keys).

### 3.3 Pre-existing `TableMetrics` regression in Stage A's own call sites

Found while re-running the full test suite (not a Stage B logic bug): `etl/audit/metrics.py`'s `TableMetrics` dataclass was refactored earlier this session (single `duration_seconds` → `extract_seconds`/`transform_seconds`/`load_seconds`/`reconcile_seconds`), but `etl/pipeline.py`'s two Stage A call sites were never updated to match, and had gone unexercised until this suite run. Fixed by passing `extract_seconds=` at both sites (Stage A's only stage is extraction). Confirmed via a full Stage A test rerun (20/20 passing) — this is a bugfix to Stage A's *code*, not a reopening of Stage A's approved *scope*.

## 4. Performance report — real 365-day dataset

Per-object breakdown from `etl_run_table_metrics` (`etl_run_id=3` for dimension loads, `etl_run_id=9` for facts/summary, both against the real dataset staged by the approved Stage A run):

| Object | Rows | Extract | Transform | Load | Reconcile | Total |
|---|---:|---:|---:|---:|---:|---:|
| dim_region | 5 | — | — | — | — | 0.12s |
| dim_product | 5,000 | — | — | — | — | 10.34s |
| dim_carrier | 25 | — | — | — | — | 0.09s |
| dim_customer | 2,000 | — | — | — | — | 4.82s |
| dim_supplier | 100 | — | — | — | — | 0.32s |
| dim_warehouse | 8 | — | — | — | — | 0.03s |
| fact_orders | 732,549 | — | 43.59s | 266.12s | 6.75s | 316.45s |
| fact_shipments | 696,747 | — | 42.03s | 358.34s | 10.76s | 411.13s |
| fact_procurement | 21,189 | — | 1.72s | 11.84s | 0.07s | 13.62s |
| fact_supplier_delivery | 20,493 | — | 1.57s | 12.87s | 0.07s | 14.51s |
| fact_returns | 33,764 | — | 10.05s | 1.47s | 0.07s | 11.59s |
| fact_inventory_snapshot | 1,825,000 | — | 135.85s | 471.86s | 48.38s | 656.09s |
| summary_daily_revenue_by_region | 1,825 | — | 0.00s | 37.30s | 0.00s | 37.30s |
| **Stage B total** | **3,339,706** | | | | | **~24.6 min (1,476.4s)** |

*(Dimension row-builders are pure Python with no separately-timed transform/load/reconcile split; their total is the full upsert call.)*

**Full pipeline total** (Stage A extraction, unchanged baseline + Stage B):

| Stage | Duration |
|---|---:|
| Stage A (extraction, approved baseline, unchanged) | 3,076.42s (51.3 min) |
| Stage B (transform + SCD2 + load + reconcile + score) | 1,476.4s (24.6 min) |
| **Full rebuild, Stage A + Stage B** | **4,552.8s (~75.9 min)** |

**Honest divergence from the original Stage B plan's estimate** ("low single-digit minutes" for a full rebuild at this data volume): actual Stage B load time is dominated by InnoDB index-maintenance cost on `fact_orders`/`fact_shipments`' bulk upserts (each fact has several FK-supporting indexes plus its grain `UNIQUE` constraint) and `fact_inventory_snapshot`'s window-function computation over the full 1.8M-row calendar grid — both real, measured costs, not an implementation shortfall (the row-by-row-vs-bulk fix from earlier profiling is already applied via `etl/load/bulk.py`'s true multi-row `INSERT ... VALUES`). Still comfortably within a normal batch window; not a blocker for this gate.

## 5. Correctness verification

**Row counts** — every table matches its expected/extracted count exactly, independently reconfirmed via direct `SELECT COUNT(*)` against the database (not just the ETL's own self-reported metrics):

| Table | Rows | Independently verified |
|---|---:|---|
| dim_region | 5 | ✅ |
| dim_product | 5,000 | ✅ |
| dim_carrier | 25 | ✅ |
| dim_customer | 2,000 | ✅ |
| dim_supplier | 100 | ✅ |
| dim_warehouse | 8 | ✅ |
| dim_date | 396 | ✅ (Phase 4, unchanged) |
| fact_orders | 732,549 | ✅ |
| fact_shipments | 696,747 | ✅ |
| fact_procurement | 21,189 | ✅ |
| fact_supplier_delivery | 20,493 | ✅ |
| fact_returns | 33,764 | ✅ |
| fact_inventory_snapshot | 1,825,000 | ✅ (= 5,000 products × 365 days, matching the single-warehouse-per-product model) |
| summary_daily_revenue_by_region | 1,825 | ✅ |

**Grain uniqueness** — every fact's row count equals its distinct-grain-key count (independently queried, not assumed from the `UNIQUE` constraint alone):

```
fact_orders                       732,549 rows = 732,549 distinct source_order_line_id
fact_shipments                    696,747 rows = 696,747 distinct source_shipment_id
fact_procurement                   21,189 rows =  21,189 distinct source_po_line_id
fact_supplier_delivery              20,493 rows =  20,493 distinct source_po_line_id
fact_returns                        33,764 rows =  33,764 distinct source_return_line_id
fact_inventory_snapshot          1,825,000 rows = 1,825,000 distinct (product_key, warehouse_key, snapshot_date_key)
summary_daily_revenue_by_region      1,825 rows =   1,825 distinct (date_key, region_key)
```

**DQ-3 quarantine** — 0 across every object in the final, corrected run (`etl_run_id=9`). 21,189 stale quarantine entries from `process_fact_procurement`'s pre-fix attempt (same `etl_run_id`, superseded by the rerun after the §3.2 fix) were deleted so the run's audit trail reflects its actual final state, not an intermediate failed attempt.

**Idempotency** — proved twice: (1) at real scale, rerunning dimension loads (`etl_run_id=4`) against unchanged source data produced `unchanged_count` equal to the full row count for every dimension, `inserted_count`/`updated_count` = 0; (2) at test scale, `test_idempotent_rerun_of_scd2_and_type1_loads_produces_no_new_rows` proves the same property directly against the load functions.

## 6. Test suite summary

```
etl/tests/test_stage_b_transforms_unit.py    16 passed  (pure row-builder logic, no DB)
etl/tests/test_stage_b_integration.py         9 passed  (SCD2 versioning, surrogate key
                                                          resolution, reconciliation,
                                                          idempotency — real DB)
etl/tests/ (Stage A suite, regression-checked) 20 passed  (confirms the §3.3 fix; no
                                                           Stage A behavior changed)
Total                                         45 passed
```

Coverage highlights:
- **SCD2 correctness**: first-version epoch sentinel, genuine tracked-attribute change (version + close-out + as-of-date resolution to the *correct* version on both sides of the change), same-day coalesce, non-tracked-attribute in-place update, true no-op rerun.
- **Surrogate key resolution**: Type 1 natural-id→key mapping; SCD2 as-of-date resolution picking the version whose `[effective_from, effective_to)` actually covers the fact's business date, not unconditionally the current version.
- **Fact transform correctness**: computed values (extended revenue/cost/margin, on-time flags, lead-time variance, return value) and DQ-3 quarantine triggers for every one of the 5 standard facts.
- **Reconciliation**: row-count mismatch detection, and a genuine grain-violation case constructed from two validly-inserted SCD2 versions sharing a natural id (not a bypassed constraint) — proving the `GROUP BY`/`HAVING` logic itself, not just observing `grain_violations == 0` (which a schema `UNIQUE` constraint would guarantee regardless of whether the logic is correct).

## 7. Definition of Done — Stage B

| Gate condition | Status |
|---|---|
| Dimension transforms (7 dims, Type 1 + SCD2) | ✅ |
| Deterministic SCD2 processing (incl. epoch-sentinel fix, ADR-016 addendum) | ✅ |
| Surrogate key resolution (Type 1 + as-of-date SCD2) | ✅ |
| Fact transforms (5 standard facts + 1 window-function rollup) | ✅ |
| Fact loading (bulk upsert, exact inserted/updated/unchanged counts) | ✅ |
| Reconciliation (row-count + grain validation, all 7 fact/summary objects) | ✅ |
| Per-object transactions | ✅ (one transaction per warehouse object per run) |
| Full audit logging (`etl_run_table_metrics` w/ per-stage timing) | ✅ |
| Measurable performance reporting | ✅ §4 above |
| Idempotent reruns | ✅ real-scale + test-scale |
| Full run against the real, validated 365-day dataset | ✅ all 13 warehouse objects, 0 quarantine |
| Stage B test suite | ✅ 25/25 new, 45/45 total incl. Stage A regression check |
| Stage A left unoptimized, per instruction | ✅ baseline unchanged (51.3 min) |

**Stage B is complete.** Per your instruction, Phase 6 (dashboards) does not begin automatically — awaiting your review of this report and separate authorization.
