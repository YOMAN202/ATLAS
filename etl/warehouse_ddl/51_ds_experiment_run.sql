-- ds_experiment_run (Phase 7, docs/phase7-architecture.md §5/§7)
--
-- One row per backtest: a model evaluated over a walk-forward
-- train/test split against real historical fact_orders data (never
-- synthetic). baseline_metric_value (the seasonal-naive model's MAPE
-- over the same test window) is recorded alongside the candidate's own
-- metric_value so "this model is actually better than doing nothing"
-- is provable by comparing two columns on one row, not asserted in a
-- comment (docs/phase7-review-checklist.md §E).

CREATE TABLE ds_experiment_run (
    id                    INT           NOT NULL AUTO_INCREMENT,
    model_id              INT           NOT NULL,
    train_start_date      DATE          NOT NULL,
    train_end_date        DATE          NOT NULL,
    test_start_date       DATE          NOT NULL,
    test_end_date         DATE          NOT NULL,
    series_scope          VARCHAR(64)   NOT NULL,  -- e.g. 'aggregate_total', 'top_20_products_by_volume'
    metric_name           VARCHAR(32)   NOT NULL,  -- 'MAPE' (SRS §15's named Planning KPI)
    metric_value          DECIMAL(10,4) NOT NULL,
    baseline_metric_value DECIMAL(10,4) NULL,
    n_observations        INT           NOT NULL,
    run_at                DATETIME      NOT NULL,
    notes                 VARCHAR(255)  NULL,
    CONSTRAINT pk_ds_experiment_run PRIMARY KEY (id),
    CONSTRAINT fk_ds_experiment_run_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_experiment_run_model_id (model_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
