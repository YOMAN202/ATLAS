# etl/

Batch ETL pipeline: extract (OLTP) → validate/DQ → transform → load (OLAP) → audit & score.

Populated in **Phase 5** (`etl/extract/`, `etl/validate/`, `etl/transform/`, `etl/load/`, `etl/pipeline.py`, `etl/tests/`) per `docs/ATLAS-Roadmap.md`. The OLAP DDL (`etl/warehouse_ddl/`) arrives in **Phase 4**, ahead of the pipeline that populates it.

Skeleton only for Phase 0 — see `docs/ATLAS-ClaudeCode-MasterPrompt.md` §8 for ETL standards.
