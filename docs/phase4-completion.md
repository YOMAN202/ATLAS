# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 4 — OLAP Data Warehouse: Completion Report

**Status: COMPLETE — 2026-08-12**
*Sources of truth: ATLAS-TDD.md §4.2/§4.2.1/§4.3 (FROZEN), ATLAS-Roadmap.md Phase 4 (FROZEN)*

---

## 1. Scope

Phase 4 built the OLAP star-schema warehouse (`atlas_olap`) that Phase 5's
ETL will populate from the completed, validated 365-day Phase 3 dataset
(`docs/phase3-validation.md`). Structure only, per the phase's own
boundary: 7 conformed dimensions, 6 fact tables at their TDD-defined
grains, one named summary-table shell, and the TDD §4.3 indexing
strategy. No data was loaded, no simulation engine code was touched, and
the simulation was not re-run.

## 2. What was built

| Object | Count | Location |
|---|---|---|
| Dimension tables | 7 (`dim_date`, `dim_region`, `dim_product`, `dim_supplier`, `dim_warehouse`, `dim_carrier`, `dim_customer`) | `etl/warehouse_ddl/01`-`07_*.sql` |
| Fact tables | 6 (`fact_orders`, `fact_shipments`, `fact_inventory_snapshot`, `fact_procurement`, `fact_supplier_delivery`, `fact_returns`) | `etl/warehouse_ddl/10`-`15_*.sql` |
| Summary tables | 1 (`summary_daily_revenue_by_region`) | `etl/warehouse_ddl/20_*.sql` |
| Composite indexes (TDD §4.3-named) | 2 | `etl/warehouse_ddl/30_composite_indexes.sql` |
| Apply/teardown tooling | `apply_ddl.py`, `teardown_ddl.py` | `etl/warehouse_ddl/` |
| Tests | 17 (DDL apply/teardown, FK resolution ×6, grain uniqueness ×6, SCD2 structure ×3) | `etl/warehouse_ddl/tests/` |
| CI job | `warehouse_ddl` (lint, format, DDL up/down/up, pytest) | `.github/workflows/ci.yml` |

14 warehouse objects total (7 + 6 + 1).

## 3. Key design decisions

The TDD names dimensions/facts and their grains but leaves column-level
schema, SCD2 mechanics, and two facts' dimension links unspecified.
Every decision made to fill those gaps is documented as an ADR
(`docs/ATLAS-TDD.md` §14), not left implicit:

- **ADR-011** — Kimball surrogate key (`<dim>_key`) on all 7 dimensions, not just the two SCD2 ones, for a uniform fact→dim FK pattern.
- **ADR-012** — SCD2 column convention (`effective_from`/`effective_to`/`is_current`), and the honest MySQL limitation that "exactly one current row per natural key" is ETL-enforced, not DB-enforced (no partial unique index in MySQL 8).
- **ADR-013** — `fact_supplier_delivery`/`fact_returns` dimension links (TDD-silent, designed from real OLTP columns), and the explicit statement that `fact_procurement` (the purchase-order event) and `fact_supplier_delivery` (the receipt/delivery event) share the same OLTP source row and natural key, since no separate delivery-event table exists in OLTP.
- **ADR-014** — `fact_inventory_snapshot` date-partitioning deferred: the actual Phase 3 dataset (365 days) is far below the volume the TDD's original 5-year assumption anticipated would warrant it.

## 4. Verification

Full results in `docs/phase4-review-checklist.md`. Summary:

- DDL applies cleanly; apply → teardown → apply is idempotent.
- `dim_date` populated (396 rows, 2021-01-01 to 2022-01-31) covering every date-bearing column in the real Phase 3 dataset.
- All 6 facts: FK resolution proven (valid insert succeeds, bogus surrogate key rejected).
- All 6 facts: grain enforcement proven (duplicate logical row rejected by the grain's `UNIQUE` constraint) — including the explicit `fact_inventory_snapshot` (product, warehouse, date) grain and the `fact_procurement`/`fact_supplier_delivery` distinction called for in review.
- SCD2 structure confirmed present only on `dim_supplier`/`dim_warehouse`, absent elsewhere.
- Both TDD §4.3-named composite indexes confirmed present; no speculative covering indexes added.
- 17/17 tests pass; lint (`ruff`) and format (`black`) clean; CI job wired.
- `docs/diagrams/star-schema.md` and `docs/data-dictionary.md` (OLAP section) both rebuilt from the actual implemented DDL, not the Phase-0 draft.

## 5. Known limitations

- **Column-level design beyond the TDD's names/grains is this phase's own design work**, not pre-specified — flagged explicitly via ADR-011 through ADR-014 rather than presented as if the TDD dictated every detail. Reviewable and revisable before Phase 5 begins.
- **No data exists in the warehouse yet** — by design. `fact_*`/`summary_*` tables are empty shells; `dim_date` is the sole exception (generated calendar, not an OLTP extract). Phase 5 populates everything else.
- **Summary tables are limited to the one TDD-named example** (`summary_daily_revenue_by_region`) — per explicit instruction, no additional aggregate tables were built even where the KPI table might suggest plausible ones (e.g. daily inventory turnover). Revisit only once Phase 7 dashboard query patterns are known, symmetric with the covering-index deferral.
- **Date-partitioning of `fact_inventory_snapshot` not implemented** (ADR-014) — genuinely not warranted at the current (365-day) data volume; revisit if a future run produces materially more data.

## 6. Definition of Done — Final Assessment

| Gate (Roadmap Phase 4) | Status |
|---|---|
| Dimension tables (7, with SCD2 flags per ADR-006) | ✅ |
| Fact tables at defined grains (TDD §4.2.1) | ✅ |
| Physical summary-table shells | ✅ (`summary_daily_revenue_by_region` only) |
| Indexing strategy implemented (TDD §4.3) | ✅ |
| Star schema diagram finalized | ✅ |
| OLAP data dictionary extended | ✅ |
| DDL apply/teardown tested in CI | ✅ |
| FK-resolution + SCD2-structure smoke tests | ✅ |
| Grain-uniqueness tests (added per review) | ✅ |
| No OLTP / simulation-engine changes | ✅ |
| No simulation re-run | ✅ |

**Phase 4 is complete.** The grain/schema review gate (`docs/phase4-review-checklist.md`) has passed. Per your instructions, implementation stops here — no Phase 5 (ETL) code, no dashboards, and no additional summary tables were built.
