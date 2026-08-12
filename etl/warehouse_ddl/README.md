# etl/warehouse_ddl/

Phase 4 deliverable: the OLAP star-schema warehouse DDL (`atlas_olap`),
built ahead of the Phase 5 ETL pipeline that populates it. Raw SQL, not
SQLAlchemy ORM models and not the existing `backend/alembic/` chain —
that chain targets `atlas_oltp` only (see `docker/mysql/init/01-init-schemas.sql`'s
own comment: schema objects are owned by Alembic for OLTP, and by this
directory for OLAP).

Design reference: `docs/ATLAS-TDD.md` §4.2/§4.2.1/§4.3, `docs/diagrams/star-schema.md`,
`docs/data-dictionary.md` (OLAP section), and ADR-011 through ADR-014
(`docs/ATLAS-TDD.md` §14).

## Apply order

Files are numbered and applied in ascending order — the numbering has
gaps so later phases can add files without renumbering:

| Range | Contents |
|---|---|
| `01`-`09` | Dimension tables (conformed, per TDD §4.2) |
| `10`-`19` | Fact tables (at their defined grains, per TDD §4.2/§4.2.1) |
| `20`-`29` | Physical summary table shells (structure only — Phase 5 populates) |
| `30`-`39` | Cross-cutting indexing passes beyond what FK constraints already create |

FK constraints are declared inline with each fact's `CREATE TABLE`
(the dimension it references always exists earlier in the numbering),
so MySQL auto-creates the supporting single-column index for every FK.
`30_composite_indexes.sql` adds only the *extra* composite indexes TDD
§4.3 names by name — it is not "the" indexing, just the addition beyond
what FK constraints already provide.

## Running it

```
python apply_ddl.py       # applies all NN_*.sql files, in order, to $DATABASE_URL_OLAP
python teardown_ddl.py    # drops every warehouse object, in reverse dependency order
```

Both read connection settings from `app.core.config.settings`
(`DATABASE_URL_OLAP` / `OLAP_SCHEMA`), same as the rest of the codebase
— override via `TEST_DATABASE_URL_OLAP` for the `atlas_olap_test` schema
(see `tests/conftest.py`).

## Scope boundary (Phase 4 Definition of Done)

This directory creates **structure only** — dimension tables, fact
tables at their defined grains, one named summary-table shell
(`summary_daily_revenue_by_region` — the only one TDD §10 names; no
others are added speculatively), and the indexing strategy from TDD
§4.3. No data is loaded (that's Phase 5), no covering indexes are added
(explicitly deferred to Phase 7 per TDD §4.3, once real dashboard query
patterns exist), and `fact_inventory_snapshot` is not date-partitioned
(TDD §10 calls this optional "if row counts warrant it" — the actual
Phase 3 dataset is 365 days, not the TDD's original 5-year assumption,
so it doesn't yet — see ADR-014).

`dim_date` is the one exception to "structure only": it has no OLTP
source to extract from (it's generated calendar arithmetic, not a
data load), so it is built *and* populated here — otherwise every
other dimension/fact would be untestable by the FK-resolution smoke
test this phase requires.
