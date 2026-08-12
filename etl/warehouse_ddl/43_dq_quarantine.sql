-- dq_quarantine (TDD §6 stage 2 "Validate"; SRS §7 DQ-1..DQ-6; BR-6; ADR-015)
--
-- Records failing DQ-1 through DQ-6 checks, one row per (source row,
-- rule violated) — never silently dropped (BR-6). Generic across every
-- source table (not one quarantine table per source), since the shape
-- of "what went wrong" is the same regardless of which table it came
-- from: which rule, what detail, and a snapshot of the offending data.
--
-- source_id is nullable: most DQ rules (DQ-1 completeness, DQ-3
-- referential integrity, DQ-5 invalid values) identify a specific
-- source row; DQ-4 (duplicate detection) may not have one canonical id
-- to point to (e.g. "these two rows share a business key").
--
-- UNIQUE(source_table, source_id, rule_violated): re-validating the same
-- row against the same rule (e.g. on a rerun) upserts the existing
-- quarantine entry rather than duplicating it — idempotent by
-- construction. MySQL treats each NULL source_id as distinct, so this
-- constraint does not dedupe DQ-4's source_id-less entries; accepted,
-- since that is an inherently rarer, harder-to-key case.

CREATE TABLE dq_quarantine (
    id              INT          NOT NULL AUTO_INCREMENT,
    etl_run_id      INT          NOT NULL,  -- most recent run that (re-)recorded this entry
    source_table    VARCHAR(64)  NOT NULL,
    source_id       INT          NULL,
    rule_violated   VARCHAR(20)  NOT NULL,  -- DQ-1 .. DQ-6
    rule_detail     VARCHAR(500) NOT NULL,
    raw_data        JSON         NULL,      -- snapshot of the offending row/fields
    quarantined_at  DATETIME     NOT NULL,
    CONSTRAINT pk_dq_quarantine PRIMARY KEY (id),
    CONSTRAINT uq_dq_quarantine_table_id_rule UNIQUE (source_table, source_id, rule_violated),
    CONSTRAINT fk_dq_quarantine_etl_run_id_etl_run_log
        FOREIGN KEY (etl_run_id) REFERENCES etl_run_log (id),
    KEY ix_dq_quarantine_etl_run_id (etl_run_id),
    KEY ix_dq_quarantine_rule_violated (rule_violated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
