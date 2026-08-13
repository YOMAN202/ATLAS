-- ds_model_registry (Phase 7, docs/phase7-architecture.md §5)
--
-- "Model" here means a named statistical method plus its parameters
-- (e.g. moving_average / window_days=7, or exponential_smoothing /
-- alpha=0.3) — never a serialized ML artifact. No ML framework is used
-- anywhere in this phase (ADR-004, docs/phase7-architecture.md §1) —
-- this table exists to make a forecast's exact parameterization
-- reproducible and inspectable, the lightweight substitute a fixed
-- family of statistical methods needs in place of MLOps tooling.
--
-- No UNIQUE constraint on (module, model_name, parameters): MySQL
-- can't index a JSON column directly, and enforcing this at the DB
-- level isn't worth a generated-column workaround for an internal
-- metadata table an application-level check-then-insert already
-- protects adequately.

CREATE TABLE ds_model_registry (
    id          INT           NOT NULL AUTO_INCREMENT,
    module      VARCHAR(32)   NOT NULL,  -- 'demand_forecasting' (Module A); future modules add their own values
    model_name  VARCHAR(64)   NOT NULL,  -- e.g. 'seasonal_naive', 'moving_average_7d', 'simple_exponential_smoothing'
    parameters  JSON          NOT NULL,  -- e.g. {"window_days": 7} or {"alpha": 0.3}
    description VARCHAR(255)  NULL,
    is_active   TINYINT(1)    NOT NULL DEFAULT 0,  -- promoted after a backtested ds_experiment_run beats baseline
    created_at  DATETIME      NOT NULL,
    CONSTRAINT pk_ds_model_registry PRIMARY KEY (id),
    KEY ix_ds_model_registry_module (module),
    KEY ix_ds_model_registry_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
