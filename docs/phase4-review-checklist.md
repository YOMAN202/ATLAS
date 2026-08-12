# Phase 4 Review Checklist — Grain/Schema Review Gate

Per `docs/ATLAS-Roadmap.md`'s Phase 4 Definition of Done: **"Warehouse
DDL creates cleanly; star schema diagram + OLAP data dictionary
complete; summary-table shells exist. → GRAIN/SCHEMA REVIEW GATE before
Phase 5."** This is that gate, with actual verification results, not a
speculative template. Separated from the design documentation
(`docs/diagrams/star-schema.md`, `docs/data-dictionary.md`) per explicit
instruction — this file is proof of correctness, not a description of
the design.

Verified 2026-08-12 against `atlas_olap_test` (containerized MySQL 8,
same pattern as the OLTP test suite).

## 1. DDL applies cleanly

| Check | Result |
|---|---|
| `apply_ddl.py` against a clean schema | ✅ 15/15 files applied without error |
| Object count after apply | ✅ 14 tables (7 dimensions + 6 facts + 1 summary) |
| `teardown_ddl.py` | ✅ 14 objects dropped, no error |
| `teardown_ddl.py` run twice in a row (idempotency) | ✅ second run is a clean no-op |
| `apply_ddl.py` → `teardown_ddl.py` → `apply_ddl.py` (up/down/up) | ✅ produces the identical 14-object schema |

## 2. `dim_date` populated correctly

| Check | Result |
|---|---|
| Row count | ✅ 396 (2021-01-01 through 2022-01-31) |
| Range covers the full validated Phase 3 dataset | ✅ every date-bearing OLTP column's actual min/max (`docs/phase3-validation.md`'s dataset) falls within range, including `purchase_orders.expected_delivery_date`'s max of 2022-01-21 |
| Spot check (2021-12-25 = Saturday, weekend flag) | ✅ correct |

## 3. Foreign-key resolution (fact → dimension)

Automated: `warehouse_ddl/tests/test_fk_resolution.py`, one test per fact table (6/6).

| Fact table | Valid insert succeeds | Bogus surrogate key rejected (IntegrityError) |
|---|---|---|
| fact_orders | ✅ | ✅ |
| fact_shipments | ✅ | ✅ |
| fact_inventory_snapshot | ✅ | ✅ |
| fact_procurement | ✅ | ✅ |
| fact_supplier_delivery | ✅ | ✅ |
| fact_returns | ✅ | ✅ |

## 4. Grain enforcement (duplicate logical rows rejected)

Automated: `warehouse_ddl/tests/test_grain_uniqueness.py`, one test per fact table (6/6) — confirms each fact's stated grain is a real DB constraint, not just a comment.

| Fact table | Stated grain | Enforced by | Duplicate-grain insert rejected |
|---|---|---|---|
| fact_orders | One row per order line | `UNIQUE(source_order_line_id)` | ✅ |
| fact_shipments | One row per shipment | `UNIQUE(source_shipment_id)` | ✅ |
| fact_inventory_snapshot | One row per product, per warehouse, per snapshot date | `UNIQUE(product_key, warehouse_key, snapshot_date_key)` | ✅ |
| fact_procurement | One row per PO line | `UNIQUE(source_po_line_id)` | ✅ |
| fact_supplier_delivery | One row per delivery event | `UNIQUE(source_po_line_id)` | ✅ |
| fact_returns | One row per return line | `UNIQUE(source_return_line_id)` | ✅ |

## 5. SCD2 structure

Automated: `warehouse_ddl/tests/test_scd2_structure.py`.

| Check | Result |
|---|---|
| `dim_supplier` has `effective_from`/`effective_to`/`is_current` | ✅ |
| `dim_warehouse` has `effective_from`/`effective_to`/`is_current` | ✅ |
| No other dimension has SCD2 columns (ADR-006 boundary) | ✅ confirmed absent on `dim_date`, `dim_region`, `dim_product`, `dim_carrier`, `dim_customer` |
| Two-version insert for the same natural `supplier_id` | ✅ both rows insert; `COUNT(*) = 2` |

## 6. Indexing (TDD §4.3)

| Check | Result |
|---|---|
| `ix_fact_inventory_snapshot_warehouse_date (warehouse_key, snapshot_date_key)` exists | ✅ |
| `ix_fact_supplier_delivery_supplier_date (supplier_key, delivery_date_key)` exists | ✅ |
| Every FK column has a supporting index | ✅ (explicit `KEY` per FK, or InnoDB auto-index) |
| No speculative covering indexes added | ✅ confirmed — none exist; deferred to Phase 7 per TDD §4.3 |

## 7. Star schema diagram matches the implemented DDL

`docs/diagrams/star-schema.md` was rebuilt from the actual DDL (not the Phase-0 draft) — every FK relationship in `etl/warehouse_ddl/*.sql` is reflected in its ER diagram, including the flagged additions beyond TDD §4.2's original diagram (`fact_orders.fulfillment_warehouse_key`, `fact_procurement.warehouse_key`, and all `fact_supplier_delivery`/`fact_returns` links). Cross-checked table-by-table: ✅ match confirmed.

## 8. Data dictionary complete

`docs/data-dictionary.md`'s new `## OLAP Data Warehouse (Phase 4)` section covers all 14 objects (7 dimensions, 6 facts, 1 summary table), same per-table format as the existing OLTP sections, with grain stated explicitly for every fact. ✅ complete.

## 9. Test suite / lint / format

| Check | Result |
|---|---|
| `pytest warehouse_ddl/tests/` | ✅ 17/17 passed |
| `ruff check .` | ✅ clean |
| `black --check .` | ✅ clean |
| CI job (`warehouse_ddl`) wired in `.github/workflows/ci.yml` | ✅ mirrors the `backend`/`simulation` jobs' pattern |

## 10. Scope boundary confirmed

| Check | Result |
|---|---|
| No `atlas_oltp` schema changes | ✅ |
| No simulation engine changes | ✅ |
| No simulation run | ✅ |
| No Phase 5 (ETL) code | ✅ |
| No dashboards | ✅ |
| Summary tables limited to `summary_daily_revenue_by_region` only | ✅ — no other aggregate tables created |

## Gate outcome

**PASS.** All checks above are satisfied with real, reproducible results (not template placeholders). Phase 5 (ETL) may begin against this schema once separately approved — this checklist does not itself authorize starting Phase 5.
