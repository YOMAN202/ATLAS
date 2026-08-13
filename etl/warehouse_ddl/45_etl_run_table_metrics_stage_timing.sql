-- etl_run_table_metrics: per-stage timing columns (ADR-022)
--
-- ALTER, not a fresh CREATE TABLE — the first schema change in this
-- project's history to a table that already holds real data (Stage A's
-- run against the validated 365-day dataset). Additive and nullable:
-- existing Stage A rows keep their meaning (duration_seconds unchanged,
-- these four new columns NULL for them); Stage B populates all four for
-- every table it processes.
--
-- teardown_ddl.py drops the whole table via DROP TABLE, so no separate
-- rollback script is needed for the disposable dev/test schemas this
-- project uses — noted for completeness, not because it's exercised here.

ALTER TABLE etl_run_table_metrics
    ADD COLUMN extract_seconds   DECIMAL(10,2) NULL AFTER rows_per_second,
    ADD COLUMN transform_seconds DECIMAL(10,2) NULL AFTER extract_seconds,
    ADD COLUMN load_seconds      DECIMAL(10,2) NULL AFTER transform_seconds,
    ADD COLUMN reconcile_seconds DECIMAL(10,2) NULL AFTER load_seconds;
