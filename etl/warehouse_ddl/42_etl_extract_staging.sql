-- etl_extract_staging (ADR-015; ADR-017)
--
-- Durable holding area for accepted (validated, non-quarantined) rows
-- extracted but not yet transformed/loaded — exists specifically so the
-- watermark-advancement rule (ADR-017) can hold with zero exceptions
-- even before Stage B (Transform/Load) exists: a row is only "durably
-- accounted for" once it's here or in dq_quarantine, never while only
-- held in memory mid-run.
--
-- `payload` is a JSON snapshot of the extracted OLTP row (all columns
-- Stage B will eventually need) — not a fixed column set, since this
-- table holds rows from every source table listed in etl_watermark, not
-- one specific shape.
--
-- UNIQUE(source_table, source_id): re-extracting the same row (e.g. on
-- a rerun after a partial-batch failure) upserts in place rather than
-- duplicating — idempotent by construction.

CREATE TABLE etl_extract_staging (
    id             INT       NOT NULL AUTO_INCREMENT,
    etl_run_id     INT       NOT NULL,  -- most recent run that (re-)staged this row
    source_table   VARCHAR(64) NOT NULL,
    source_id      INT       NOT NULL,
    payload        JSON      NOT NULL,
    extracted_at   DATETIME  NOT NULL,  -- source row's own updated_at, not wall-clock (ADR-016 determinism)
    CONSTRAINT pk_etl_extract_staging PRIMARY KEY (id),
    CONSTRAINT uq_etl_extract_staging_table_id UNIQUE (source_table, source_id),
    CONSTRAINT fk_etl_extract_staging_etl_run_id_etl_run_log
        FOREIGN KEY (etl_run_id) REFERENCES etl_run_log (id),
    KEY ix_etl_extract_staging_etl_run_id (etl_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
