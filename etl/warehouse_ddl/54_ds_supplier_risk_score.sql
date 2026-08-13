-- ds_supplier_risk_score (Phase 7 Module C, docs/phase7-module-c-completion.md)
--
-- Grain: one row per (supplier_key, etl_run_id) — BR-4 ("supplier risk
-- score is warehouse-derived, recomputed per ETL cycle, not real-time").
-- supplier_key is dim_supplier's *current* version (is_current=1) —
-- suppliers are SCD2 but none actually changes attributes during this
-- simulation (docs/phase5-validation.md §5/§11), so "current" and
-- "the only version" coincide in practice; the column still points at
-- whichever version was current when the score was computed, not a
-- natural id, consistent with how every other fact in this warehouse
-- resolves SCD2 dimensions.
--
-- Every input the score's formula uses is its own named column here
-- (on_time_rate, quality_rejection_rate, lead_time_stddev_days,
-- on_time_rate_trend_delta) — never folded away into an opaque number
-- only the score itself reveals — the concrete mechanism behind FR-8.2/
-- FR-8.4 (specific triggering metrics, no black-box outputs).
--
-- Utilization (total_spend, share_of_total_spend, distinct_products,
-- distinct_warehouses) is reported alongside the score as *context*,
-- not folded into the risk formula itself — how much a business relies
-- on a supplier is not, by itself, evidence that the supplier is risky;
-- conflating the two would make an important, heavily-relied-on
-- supplier look artificially risky purely for being large.

CREATE TABLE ds_supplier_risk_score (
    id                          INT           NOT NULL AUTO_INCREMENT,
    supplier_key                INT           NOT NULL,
    risk_score                  DECIMAL(6,2)  NOT NULL,  -- 0-100, higher = more risk
    risk_classification         VARCHAR(10)   NOT NULL,  -- 'Low' | 'Medium' | 'High'
    on_time_rate                DECIMAL(6,4)  NOT NULL,
    quality_rejection_rate      DECIMAL(6,4)  NOT NULL,
    fill_rate                   DECIMAL(6,4)  NOT NULL,  -- received_quantity / ordered_quantity
    avg_lead_time_variance_days DECIMAL(8,2)  NOT NULL,
    lead_time_stddev_days       DECIMAL(8,2)  NOT NULL,  -- delivery variability/predictability
    on_time_rate_trend_delta    DECIMAL(6,4)  NOT NULL,  -- prior-period rate minus recent-period rate; positive = degrading
    trend_direction              VARCHAR(10)   NOT NULL,  -- 'improving' | 'stable' | 'degrading'
    total_spend                  DECIMAL(14,2) NOT NULL,  -- utilization context, not a risk input
    share_of_total_spend         DECIMAL(6,4)  NOT NULL,
    distinct_products_supplied   INT           NOT NULL,
    distinct_warehouses_served   INT           NOT NULL,
    n_deliveries                 INT           NOT NULL,
    triggering_metrics           JSON          NOT NULL,  -- human-readable list of thresholds actually crossed
    model_id                     INT           NOT NULL,  -- FK to ds_model_registry: the scoring formula + weights used
    etl_run_id                   INT           NOT NULL,
    generated_at                 DATETIME      NOT NULL,
    CONSTRAINT pk_ds_supplier_risk_score PRIMARY KEY (id),
    CONSTRAINT fk_ds_supplier_risk_score_supplier_key_dim_supplier
        FOREIGN KEY (supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_ds_supplier_risk_score_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_supplier_risk_score_etl_run_id_etl_run_log
        FOREIGN KEY (etl_run_id) REFERENCES etl_run_log (id),
    KEY ix_ds_supplier_risk_score_supplier_key (supplier_key),
    KEY ix_ds_supplier_risk_score_model_id (model_id),
    KEY ix_ds_supplier_risk_score_classification (risk_classification)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
