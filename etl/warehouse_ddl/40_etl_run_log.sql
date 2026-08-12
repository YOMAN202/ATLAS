-- etl_run_log (TDD §6 stage 5 "Audit & Score"; DQ-6; ADR-015)
--
-- One row per pipeline invocation. Lives in atlas_olap because the ETL
-- process has no write access to atlas_oltp (Master Prompt §3
-- communication matrix) — see ADR-015 for the full location rationale.
--
-- `stage` records which stage(s) actually ran in this invocation —
-- meaningful right now while only Stage A exists (always 'STAGE_A'),
-- and later distinguishes a Stage-A-only run from a full Stage A+B run
-- once Stage B is built, without needing a schema change.
--
-- `dq_score` (DQ-7) is NULL until Stage B's scoring exists — Stage A has
-- nothing to compute a data-quality score from yet (scoring is defined
-- against loaded/transformed data, not just extraction/validation).

CREATE TABLE etl_run_log (
    id                 INT           NOT NULL AUTO_INCREMENT,
    started_at         DATETIME      NOT NULL,
    completed_at       DATETIME      NULL,
    status             VARCHAR(20)   NOT NULL,  -- RUNNING / SUCCEEDED / FAILED
    stage              VARCHAR(20)   NOT NULL,  -- STAGE_A (today); STAGE_A_B once Stage B exists
    dq_score           DECIMAL(5,2)  NULL,      -- DQ-7; populated by Stage B
    duration_seconds   DECIMAL(10,2) NULL,
    CONSTRAINT pk_etl_run_log PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
