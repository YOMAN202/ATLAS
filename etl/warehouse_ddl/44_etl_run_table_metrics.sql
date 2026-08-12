-- etl_run_table_metrics (TDD §6 stage 5 "Audit & Score"; DQ-6; ADR-015)
--
-- One row per (run, source table): the full operational audit
-- breakdown, per the Phase 5 review requirement — every count is a
-- real, separately-tracked column, not folded into a vague "loaded"
-- total.
--
-- inserted/updated/unchanged are exact counts from a bulk-fetch-then-
-- compare step before load (not derived from MySQL's ambiguous
-- multi-row ON DUPLICATE KEY UPDATE affected-rows arithmetic) — see
-- etl/load/ once Stage B exists. In Stage A (no load stage yet), these
-- three columns are always 0; only extracted/quarantined/rejected/
-- duration/rows_per_second are meaningful for now (documented in
-- etl/README.md and the Stage A completion report, not hidden).
--
-- rejected_count: passed validation but a subsequent step still failed
-- for a genuine system/constraint reason — distinct from quarantined
-- (failed a DQ-1..DQ-6 check), per DQ-6's own three-way accepted /
-- quarantined / rejected distinction. Expected to be zero in normal
-- operation.
--
-- rows_per_second = extracted_count / duration_seconds, the same value
-- emitted via structured logging (one computation, not two that could
-- drift) — the pipeline-observability requirement.

CREATE TABLE etl_run_table_metrics (
    id                 INT           NOT NULL AUTO_INCREMENT,
    etl_run_id         INT           NOT NULL,
    source_table       VARCHAR(64)   NOT NULL,
    extracted_count    INT           NOT NULL DEFAULT 0,
    inserted_count     INT           NOT NULL DEFAULT 0,
    updated_count      INT           NOT NULL DEFAULT 0,
    unchanged_count    INT           NOT NULL DEFAULT 0,
    quarantined_count  INT           NOT NULL DEFAULT 0,
    rejected_count     INT           NOT NULL DEFAULT 0,
    duration_seconds   DECIMAL(10,2) NOT NULL,
    rows_per_second    DECIMAL(12,2) NULL,
    CONSTRAINT pk_etl_run_table_metrics PRIMARY KEY (id),
    CONSTRAINT uq_etl_run_table_metrics_run_table UNIQUE (etl_run_id, source_table),
    CONSTRAINT fk_etl_run_table_metrics_etl_run_id_etl_run_log
        FOREIGN KEY (etl_run_id) REFERENCES etl_run_log (id),
    KEY ix_etl_run_table_metrics_source_table (source_table)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
