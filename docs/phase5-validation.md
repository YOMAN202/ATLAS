# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 5 — ETL Pipeline: Validation Record

**Status: PHASE 5 APPROVED — 2026-08-13**
*Sources of truth: ATLAS-TDD.md §6 (FROZEN), ATLAS-Roadmap.md Phase 5 (FROZEN), ADR-008, ADR-015 through ADR-022, `docs/phase5-stage-a-completion.md`, `docs/phase5-stage-b-completion.md`*

This document is the authoritative, permanent validation record for the ATLAS warehouse: it rolls up Stage A (extraction) and Stage B (transform/load) into one final reconciliation and Definition of Done assessment. It supersedes nothing — the two completion reports remain the record of *what was built and when*; this is the record of *what was checked, against the live database, after both stages ran against the real, validated 365-day dataset*. Every number below was re-queried directly against `atlas_oltp`/`atlas_olap` while writing this document, not carried forward from memory of earlier runs.

---

## 1. OLTP vs OLAP reconciliation summary

Every warehouse table's row count traced back to its OLTP source, queried directly against both databases in the same sitting:

| OLTP source | OLTP rows | OLAP target | OLAP rows | Match |
|---|---:|---|---:|---|
| `regions` | 5 | `dim_region` | 5 | ✅ |
| `products` | 5,000 | `dim_product` | 5,000 | ✅ |
| `carriers` | 25 | `dim_carrier` | 25 | ✅ |
| `customers` | 2,000 | `dim_customer` | 2,000 | ✅ |
| `suppliers` | 100 | `dim_supplier` | 100 (natural ids); 100 (rows, 1 version each) | ✅ |
| `warehouses` | 8 | `dim_warehouse` | 8 (natural ids); 8 (rows, 1 version each) | ✅ |
| `order_lines` | 732,549 | `fact_orders` | 732,549 | ✅ |
| `orders` (distinct, via `fact_orders.order_number`) | 292,925 | `fact_orders` distinct orders | 292,925 | ✅ |
| `shipments` | 696,747 | `fact_shipments` | 696,747 | ✅ |
| `purchase_order_lines` | 21,189 | `fact_procurement` | 21,189 | ✅ |
| `purchase_order_lines` (delivered, `actual_delivery_date IS NOT NULL`) | 20,493 | `fact_supplier_delivery` | 20,493 | ✅ |
| `return_lines` | 33,764 | `fact_returns` | 33,764 | ✅ |
| `inventory_transactions` (745,763 rows) / `inventory_positions` (5,000 rows) → rollup | — | `fact_inventory_snapshot` | 1,825,000 (= 5,000 products × 365 days) | ✅ |

**Monetary reconciliation** (fact-to-summary, not just row counts — the two are computed independently: `fact_orders` per-line, `summary_daily_revenue_by_region` via a separate `GROUP BY` aggregation query):

```
fact_orders:                       total_revenue = 414,858,410.46   total_margin = 210,074,493.78
summary_daily_revenue_by_region:   total_revenue = 414,858,410.46   total_margin = 210,074,493.78   total_lines = 732,549
```

Exact match to the cent, and `total_lines` matches `fact_orders`' row count exactly.

`dim_date` (396 rows, Phase 4-generated, no ETL) and the ETL process-metadata tables (`etl_watermark`, `etl_extract_staging`, `dq_quarantine`, `etl_run_log`, `etl_run_table_metrics`) are out of scope for OLTP reconciliation by design (they have no single OLTP source table).

## 2. Row-count reconciliation

Every table's extracted/loaded count matches its expected count exactly (see §1). No table shows a discrepancy between what Stage A extracted, what Stage B transformed, and what is currently live in the warehouse — confirmed by direct `SELECT COUNT(*)` against `atlas_olap`, not by trusting the ETL's own self-reported `etl_run_table_metrics` alone (that table's numbers are cross-checked against this independent count in `docs/phase5-stage-b-completion.md` §5 and agree).

## 3. Grain validation

Every fact and the summary table's row count equals its distinct-grain-key count, independently queried:

```
fact_orders                       732,549 rows = 732,549 distinct source_order_line_id
fact_shipments                    696,747 rows = 696,747 distinct source_shipment_id
fact_procurement                   21,189 rows =  21,189 distinct source_po_line_id
fact_supplier_delivery              20,493 rows =  20,493 distinct source_po_line_id
fact_returns                        33,764 rows =  33,764 distinct source_return_line_id
fact_inventory_snapshot          1,825,000 rows = 1,825,000 distinct (product_key, warehouse_key, snapshot_date_key)
summary_daily_revenue_by_region      1,825 rows =   1,825 distinct (date_key, region_key)
```

Zero grain violations across every fact/summary object.

## 4. Surrogate key validation

**Required FK resolution — zero unresolved keys** where a key is required by the fact's own semantics (checked directly, not inferred from the FK constraint alone):

```
fact_orders.product_key                    0 unresolved
fact_orders.customer_key                   0 unresolved
fact_shipments.carrier_key                 0 unresolved
fact_shipments.origin_warehouse_key        0 unresolved
fact_procurement.supplier_key              0 unresolved
fact_procurement.warehouse_key             0 unresolved
fact_supplier_delivery.supplier_key        0 unresolved
fact_returns.product_key                   0 unresolved
fact_inventory_snapshot.product_key        0 unresolved
```

**Referential integrity** is additionally guaranteed structurally by every fact's FK constraint to its dimension (Phase 4 DDL) — a dangling surrogate key reference is not possible to insert at all, not just unlikely.

**Type 1 vs. SCD2 resolution correctness**: Type 1 dimensions (`dim_region`, `dim_product`, `dim_carrier`, `dim_customer`) resolve via direct natural-id → surrogate-key lookup; SCD2 dimensions (`dim_supplier`, `dim_warehouse`) resolve via `resolve_scd2_as_of()`, keyed by `(row_id, natural_id, business_date)` so two fact rows referencing the same supplier/warehouse with different business dates can legitimately resolve to different surrogate keys if history existed. In this dataset, no supplier/warehouse ever actually changed (§9 below), so every resolution in the live data trivially picked the single existing version — the *as-of-date* resolution logic itself (picking the version whose `[effective_from, effective_to)` range covers the query date, not unconditionally the current version) is proven correct via `etl/tests/test_stage_b_integration.py::test_scd2_genuine_tracked_change_versions_and_resolves_by_business_date`, not by live-data evidence, since live data never exercises the multi-version branch. Stated plainly rather than implied.

## 5. SCD2 validation

```
dim_supplier:   100 rows, 100 distinct supplier_id, 100 current (is_current=1)
dim_warehouse:    8 rows,   8 distinct warehouse_id,   8 current (is_current=1)
```

- **Exactly one current version per natural id**: `GROUP BY supplier_id HAVING COUNT(*) <> 1` (filtered to `is_current=1`) returns zero rows for both dimensions — no natural id has zero or more than one current version.
- **Version structure**: every one of the 108 rows has `effective_from = 2000-01-01`, `effective_to = NULL`, `is_current = 1` — i.e., every supplier and warehouse has exactly one version, dated to the ADR-016-addendum epoch sentinel (`docs/ATLAS-TDD.md` §14) rather than to source `updated_at`, because none of them has a genuine tracked-attribute change in this simulated dataset (Phase 3's simulation does not model supplier-terms or warehouse-capacity changes over time).
- **No overlapping or gapped ranges**: trivially true with exactly one open-ended version per natural id.
- **Multi-version branches** (genuine tracked change, same-day coalesce, non-tracked in-place update) are proven only via `etl/tests/test_stage_b_integration.py` against constructed data, not live data — see §9 (known limitations).

## 6. Idempotency validation

**Real-scale evidence**: dimension loads were run twice against the real dataset with no intervening OLTP changes (`etl_run_id=3` then `etl_run_id=4`). The second run's `etl_run_table_metrics` shows `inserted_count=0`, `updated_count=0`, `unchanged_count` equal to the full row count for every one of the 6 dimensions (`dim_region` 5/5 unchanged, `dim_product` 5,000/5,000, `dim_carrier` 25/25, `dim_customer` 2,000/2,000, `dim_supplier` 100/100, `dim_warehouse` 8/8) — a true no-op, not an estimate.

**Test-scale evidence**: `test_scd2_unchanged_candidate_is_a_true_noop` and `test_idempotent_rerun_of_scd2_and_type1_loads_produces_no_new_rows` (`etl/tests/test_stage_b_integration.py`) prove the same property directly against the load functions, and Stage A's own `test_no_change_rerun_extracts_zero_additional_rows` / `test_quarantine_revalidation_is_idempotent_not_duplicated` (`etl/tests/test_pipeline_integration.py`) prove it for extraction.

**Not re-verified in this pass**: idempotency of the 7 fact/summary loaders at real scale was not re-run as part of writing this document, per the explicit instruction not to modify or re-run the pipeline further this pass. It is covered by `test_idempotent_rerun_of_scd2_and_type1_loads_produces_no_new_rows`'s equivalent pattern for dimensions and by `upsert_fact`'s identical bulk-fetch-compare-write mechanism (`etl/load/facts.py`) — the same code path already proven idempotent for dimensions — but this is a reasoned inference from shared implementation, not a direct real-scale fact-table observation. Stated plainly as a gap, not silently assumed.

## 7. Quarantine summary

```
SELECT COUNT(*) FROM dq_quarantine;   →   0
```

`dq_quarantine` is empty in the current, final warehouse state. This reflects a clean source dataset (Stage A's DQ-1 through DQ-5 checks and Stage B's DQ-3 FK-resolution check found nothing to reject in this specific 365-day run) — **not** an untested code path: every DQ rule's actual detection logic is proven against deliberately constructed bad data in `etl/tests/test_dq_rules_unit.py` (9 tests) and `etl/tests/test_stage_b_transforms_unit.py` (quarantine-on-unresolved-FK cases for all 5 standard facts), since the real OLTP schema's own constraints mean most rule violations can't reach a live run to be observed there.

One real quarantine event *did* occur during Stage B development — `process_fact_procurement`'s first attempt quarantined 100% of 21,189 rows due to the SCD2 epoch bug (`docs/phase5-stage-b-completion.md` §3.2). Those entries were deleted after the fix (they were superseded within the same `etl_run_id` by a clean rerun) so the final quarantine table reflects the warehouse's actual current state, not a stale failed attempt. This is disclosed here for completeness, not hidden by the cleanup.

## 8. Pipeline runtime breakdown

| Stage | Duration | Notes |
|---|---:|---|
| Stage A — extraction (13 tables) | 3,076.42s (51.3 min) | Approved baseline (`docs/phase5-stage-a-completion.md`); unmodified this pass |
| Stage B — dimensions (6 dims) | 15.72s | `etl_run_id=3` |
| Stage B — facts + summary (7 objects) | 1,460.69s (24.3 min) | `etl_run_id=9`, see per-object breakdown below |
| **Stage B total** | **~1,476.4s (24.6 min)** | |
| **Full pipeline (Stage A + Stage B)** | **~4,552.8s (~75.9 min)** | |

Per-object Stage B breakdown (`etl_run_table_metrics`, `etl_run_id=9` for facts/summary):

| Object | Rows | Transform | Load | Reconcile | Total |
|---|---:|---:|---:|---:|---:|
| fact_orders | 732,549 | 43.59s | 266.12s | 6.75s | 316.45s |
| fact_shipments | 696,747 | 42.03s | 358.34s | 10.76s | 411.13s |
| fact_procurement | 21,189 | 1.72s | 11.84s | 0.07s | 13.62s |
| fact_supplier_delivery | 20,493 | 1.57s | 12.87s | 0.07s | 14.51s |
| fact_returns | 33,764 | 10.05s | 1.47s | 0.07s | 11.59s |
| fact_inventory_snapshot | 1,825,000 | 135.85s | 471.86s | 48.38s | 656.09s |
| summary_daily_revenue_by_region | 1,825 | 0.00s | 37.30s | 0.00s | 37.30s |

**Bookkeeping caveat, disclosed rather than silently left**: `etl_run_log` rows for `etl_run_id=3` and `4` (dimension loads, run via the one-off `etl/run_one_fact.py` helper — not part of the pipeline's public API, used to build up real numbers incrementally given repeated local Docker/WSL2 instability during this work) were never marked complete (`status=RUNNING`, `completed_at=NULL`) — that helper script intentionally does not call `complete_run()`, since each invocation processes a single object, not a full run. `etl_run_id=9`'s logged `duration_seconds` (0.00) is similarly a bookkeeping artifact of being finalized via a direct `complete_run()` call after the fact rather than the normal in-process path. The authoritative total pipeline time above is computed by summing `etl_run_table_metrics` (which every invocation, including the one-off helper, always writes correctly), not by trusting `etl_run_log.duration_seconds`. The full, un-interrupted production entry point (`run_full_pipeline()` / `run_stage_b_only.py`) does call `complete_run()` correctly and was not the code path used to build the real-data numbers in this pass, for the operational reasons above.

## 9. Inventory snapshot validation

`fact_inventory_snapshot` (1,825,000 rows = 5,000 products × 365 days) received targeted, independent validation beyond row-count/grain checks, since it is a rollup (not 1:1 with any single OLTP source row) and the single largest table in the warehouse:

- **No negative balances**: `quantity_on_hand < 0` → 0 rows; `quantity_available < 0` → 0 rows.
- **`is_stockout` flag correctness**: the actual rule (`etl/transform/inventory_snapshot.py`) is `is_stockout = (quantity_on_hand == 0)`, not `quantity_available <= 0` — verified `is_stockout <> (quantity_on_hand = 0)` → 0 rows across all 1,825,000. (17,708 rows have `quantity_on_hand = 0`, all correctly flagged.)
- **Ledger spot-check against the running-balance window function**: for `product_id=1, warehouse_id=3`, manually summing `quantity_delta` from `inventory_transactions` through `2021-04-11` gives `2`; `fact_inventory_snapshot` for that exact `(product_key=1, warehouse_key=3, snapshot_date_key=20210411)` also shows `quantity_on_hand=2` — exact match.
- **Last-day reconciliation against OLTP's authoritative current state**: for the same pair, `inventory_positions` (the live, authoritative current-state table) shows `quantity_on_hand=18, quantity_reserved=1`; `fact_inventory_snapshot`'s last day (`2021-12-31`) shows the identical `18`/`1` — the ledger-derived history correctly converges to the source-of-truth current position on the final day.
- **`quantity_reserved` historical limitation, confirmed empirically**: `inventory_transactions` is documented as not recording reservations (`backend/app/domains/inventory/service.py`: "Reserving does not append to the transaction ledger, because nothing physically moved yet"), so every historical day's `quantity_reserved` is `0` by construction, with only the final day using the real current value from `inventory_positions`. Confirmed directly: all 3,786 rows with `quantity_reserved <> 0` fall exclusively on `snapshot_date_key=20211231` (the last day) — zero on any earlier day, exactly matching the documented behavior.
- **Coverage**: 5,000 distinct products × 8 distinct warehouses is the DDL's addressable space, but only products/warehouses that ever had ledger activity appear (`active_pairs` CTE) — 5,000 distinct `product_key` and all 8 `warehouse_key` values are present, and the date range is exactly `2021-01-01` through `2021-12-31` (365 distinct days), matching the full simulated year.

## 10. Performance findings

- **Full rebuild, both stages: ~75.9 minutes** against the real 365-day dataset (292,925 orders / 732,549 order lines / 696,747 shipments / 21,189 PO lines / 33,764 return lines / 745,763 inventory transactions). Comfortably within a normal batch window; Stage A's extraction (51.3 min) remains the dominant cost, unchanged from its approved baseline.
- **Stage B load time is dominated by InnoDB index-maintenance cost**, not query planning or transform logic: `fact_orders` and `fact_shipments` (the two largest, most heavily-indexed facts) account for 624.46s of Stage B's 1,460.69s fact/summary total (43%), consistent with prior profiling that isolated this to per-row index upkeep across each fact's several FK-supporting indexes plus its grain `UNIQUE` constraint, not the bulk-upsert mechanism itself (already fixed from a true row-by-row bug earlier in Stage B development — see `docs/phase5-stage-b-completion.md` §3.1 lineage in `etl/load/bulk.py`).
- **`fact_inventory_snapshot`'s window-function transform (135.85s) is cheap relative to its load (471.86s)** — the single set-based SQL query computing a 1.8M-row running balance is fast; writing that volume through the same index-maintenance cost as any other bulk load is what dominates.
- **Operational finding, not a pipeline defect**: this development environment's Docker Desktop/WSL2 VM has only ~3.74 GiB total memory shared across all containers. A Python ETL process combined with MySQL's own usage repeatedly crashed the Docker VM itself (not a clean OOM-kill) during Stage B development before the memory-footprint fix in §3.1 of the Stage B completion report. Reproducing a full real-data run in a similarly memory-constrained environment should budget accordingly; the fix (targeted SQL-side field projection instead of full-JSON-payload materialization) is now part of the production code path, not a workaround left in place only for this run.

## 11. Known limitations

Stated plainly, as the authoritative record should, rather than left implicit:

1. **`quantity_reserved` has no historical ledger** (§9) — every historical day's reserved quantity in `fact_inventory_snapshot` is `0` by construction; only the most recent day reflects a real value. This is a genuine source-data limitation (Phase 2's own domain design), not an ETL shortcoming, and is documented directly in `etl/transform/inventory_snapshot.py`.
2. **SCD2 multi-version behavior is untested at real-data scale.** No supplier or warehouse actually changes during the 365-day simulation, so every SCD2 dimension in the live warehouse has exactly one version. The version-transition logic (new version, same-day coalesce, non-tracked in-place update, as-of-date resolution across versions) is proven correct only via `etl/tests/test_stage_b_integration.py`'s constructed scenarios, not by observing it happen in this dataset.
3. **The epoch sentinel (`2000-01-01`) is a modeling convention, not a real historical date.** It exists specifically so a dimension's first version is resolvable against every business date in this dataset (ADR-016 addendum); it does not represent when any supplier or warehouse actually began existing in reality.
4. **Single-warehouse-per-product model** — the real, validated dataset's product/warehouse relationship (5,000 products, each active in at most a small number of warehouses per the simulation's own design) diverges from the original TDD's implicit 5-year/multi-warehouse-spread assumption, as already noted in the original Stage B plan. `fact_inventory_snapshot`'s 1,825,000-row size (5,000 × 365) reflects the real model, not the original estimate.
5. **`fact_inventory_snapshot` recomputes full history every run**, not incrementally (ADR-020) — a deliberate, cost-justified exception given the table's true measured scale (1.8M rows recomputed in 135.85s), not a scalability plan for materially larger data volumes without revisiting that decision.
6. **Day-level SCD2 granularity** — `effective_from`/`effective_to` are `DATE`, not `DATETIME` (a frozen Phase 4 schema decision), so two genuine tracked-attribute changes to the same natural key within one calendar day coalesce into a single version; only the latest same-day state survives as history.
7. **`etl_run_log` bookkeeping gaps for one-off single-object runs** (§8) — a tooling/operational artifact of how the real-data numbers were built up under repeated local Docker instability, not a defect in the production `run_full_pipeline()` entry point.
8. **Idempotency at real scale was directly observed for dimension loads, not fact loads** (§6) — fact-load idempotency rests on the same proven code path (`upsert_fact` shares its bulk-fetch-compare-write mechanism with the dimension loader) plus test-level proof, not a direct real-scale re-run of the fact loaders in this pass, per this pass's explicit "do not modify/re-run the pipeline" instruction.
9. **This development environment's ~3.74 GiB Docker memory ceiling** (§10) is specific to the machine this work was done on, not a general ATLAS deployment constraint — noted for anyone reproducing this validation run locally.

## 12. Final Phase 5 Definition of Done assessment

| Gate condition | Status | Evidence |
|---|---|---|
| Extraction, watermark-based, per table | ✅ | `docs/phase5-stage-a-completion.md` §4.2; `etl_watermark`, all 13 tables advanced correctly (§8 above) |
| Durable staging (`etl_extract_staging`) | ✅ | Stage A completion report |
| DQ-1 through DQ-6 validation | ✅ | 9 unit tests + 5 quarantine-trigger tests (Stage B); 0 real violations this run (§7) |
| Quarantine | ✅ | `dq_quarantine` correctly empty in final state; historical event correctly recorded then correctly cleaned up (§7) |
| Audit logging + observability (`etl_run_log`, `etl_run_table_metrics`) | ✅ (with disclosed bookkeeping caveat, §8) | |
| Failure-recovery (all 4 fault-injection scenarios) | ✅ | Stage A completion report |
| Dimension transforms (Type 1 + SCD2, 7 dims) | ✅ | §1, §5 |
| Deterministic SCD2 processing | ✅ | §5; ADR-016 + addendum |
| Surrogate key resolution (Type 1 + as-of-date SCD2) | ✅ | §4 |
| Fact transforms (5 standard + 1 rollup) | ✅ | §1, §3, §9 |
| Fact loading (exact inserted/updated/unchanged counts) | ✅ | §1, §8 |
| Reconciliation (row-count + grain, all 7 fact/summary objects) | ✅ | §2, §3 |
| Per-object transactions | ✅ | `docs/phase5-stage-b-completion.md` §2 |
| Idempotent reruns | ✅ (dimensions: real-scale; facts: code-path + test-level, §6) | §6 |
| OLTP vs OLAP reconciliation | ✅ | §1 |
| Full run against the real, validated 365-day dataset | ✅ | 0 quarantine in final state, all row counts and monetary totals reconcile exactly |
| Complete test suite | ✅ 45/45 (20 Stage A + 25 Stage B) | `docs/phase5-stage-b-completion.md` §6 |
| Known limitations documented | ✅ | §11 |

**Phase 5 is complete and validated.** This document, together with `docs/phase5-stage-a-completion.md` and `docs/phase5-stage-b-completion.md`, is the permanent record. Per your instruction, the ETL pipeline was not modified and not further optimized while producing this document — every figure above was obtained via read-only queries against the already-loaded warehouse and the already-committed test suite. Phase 6 (dashboards) awaits your review of the accompanying architecture proposal and separate approval before implementation begins.
