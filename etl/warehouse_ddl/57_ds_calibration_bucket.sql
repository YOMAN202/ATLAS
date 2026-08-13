-- ds_calibration_bucket (Phase 7 Module D, docs/phase7-module-d-completion.md)
--
-- The "calibration analysis" deliverable's raw material: a reliability
-- diagram, stored. For each of the three prediction types, historical
-- (product, warehouse) pairs are walk-forward backtested (train on data
-- up to a cutoff, predict the next 30 days, check what actually
-- happened in that real, already-elapsed window) and grouped into
-- probability deciles. A well-calibrated model's bucket 7 (70-80%
-- predicted) should show an actual outcome rate near 70-80% — this
-- table is what makes that comparison queryable rather than asserted.
--
-- Overall Brier score per prediction_type is NOT duplicated here — it
-- is stored in the existing, already-module-agnostic ds_experiment_run
-- (metric_name='BRIER_SCORE', series_scope=prediction_type), the same
-- table Module A's MAPE backtests already use. This table is the
-- per-bucket detail that single summary number is computed from.

CREATE TABLE ds_calibration_bucket (
    id                         INT           NOT NULL AUTO_INCREMENT,
    model_id                   INT           NOT NULL,
    prediction_type            VARCHAR(20)   NOT NULL,  -- 'stockout' | 'backorder' | 'fulfillment_delay'
    bucket_index                INT           NOT NULL,  -- 0-9, decile of predicted probability
    predicted_probability_mean DECIMAL(6,5)  NOT NULL,
    actual_outcome_rate        DECIMAL(6,5)  NOT NULL,
    n_observations              INT           NOT NULL,
    etl_run_id                  INT           NOT NULL,
    generated_at                 DATETIME      NOT NULL,
    CONSTRAINT pk_ds_calibration_bucket PRIMARY KEY (id),
    CONSTRAINT uq_ds_calibration_bucket_grain UNIQUE (model_id, prediction_type, bucket_index),
    CONSTRAINT fk_ds_calibration_bucket_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_calibration_bucket_prediction_type (prediction_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
