-- etl_watermark (TDD §6 stage 1 "Extract"; ADR-008; ADR-015; ADR-017)
--
-- One row per OLTP source table, tracking the incremental-extraction
-- cursor (ADR-008). `last_extracted_at` is NULL until a table's first
-- successful batch — extraction then pulls WHERE updated_at > watermark
-- (or everything, if NULL, per ADR-008's "since the last watermark").
--
-- Advancement rule (ADR-017, stated in full there): advances only to
-- the maximum updated_at among rows durably accounted for this run
-- (staged or quarantined) — never to the extraction cutoff timestamp,
-- and never past a row that failed mid-batch.

CREATE TABLE etl_watermark (
    source_table       VARCHAR(64) NOT NULL,
    last_extracted_at  DATETIME    NULL,
    updated_at         DATETIME    NOT NULL,  -- when this watermark row itself last changed
    CONSTRAINT pk_etl_watermark PRIMARY KEY (source_table)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
