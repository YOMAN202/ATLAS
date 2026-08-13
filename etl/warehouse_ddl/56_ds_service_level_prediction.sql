-- ds_service_level_prediction (Phase 7 Module D, docs/phase7-module-d-completion.md)
--
-- One row per (product, warehouse): three closed-form, statistically
-- derived probabilities — stockout, backorder, and inbound fulfillment
-- delay — each carrying its own contributing-factor breakdown and
-- confidence marker, per FR-8.1/FR-8.4 ("no black-box outputs").
--
-- "Calculation methodology" (a required field per the module brief) is
-- NOT duplicated as text on every row — it lives once, structured, in
-- ds_model_registry.parameters for this row's model_id, the same
-- pattern Module A's ActiveModelInfo.parameters and Module C's
-- scoring_weights already use. Dereference model_id to read it.
--
-- source_forecast_model_id / source_supplier_model_id are literally
-- "source forecast version" / "source supplier score version" from the
-- module brief: the exact ds_model_registry.id of the Module A and
-- Module C models whose outputs fed this row, so a prediction is
-- traceable to the upstream model that produced its inputs even after
-- either upstream model is later replaced.
--
-- fulfillment_delay_* columns are nullable: not every (product,
-- warehouse) pair resolves to a primary supplier with enough delivery
-- history (see run_module_d.py's MIN_DELIVERIES_FOR_DELAY_PREDICTION
-- guard) — excluded, not silently defaulted.

CREATE TABLE ds_service_level_prediction (
    id                                  INT           NOT NULL AUTO_INCREMENT,
    product_key                         INT           NOT NULL,
    warehouse_key                       INT           NOT NULL,
    stockout_probability                 DECIMAL(6,5)  NOT NULL,
    stockout_confidence                  VARCHAR(10)   NOT NULL,  -- 'high' | 'medium' | 'low'
    stockout_contributing_factors        JSON          NOT NULL,
    backorder_probability                DECIMAL(6,5)  NOT NULL,
    backorder_confidence                 VARCHAR(10)   NOT NULL,
    backorder_contributing_factors       JSON          NOT NULL,
    fulfillment_delay_probability        DECIMAL(6,5)  NULL,
    fulfillment_delay_confidence         VARCHAR(10)   NULL,
    fulfillment_delay_contributing_factors JSON        NULL,
    primary_supplier_key                 INT          NULL,
    source_forecast_model_id             INT           NOT NULL,
    source_supplier_model_id             INT          NULL,
    model_id                             INT           NOT NULL,  -- this module's own registered formula (module='service_level_prediction')
    etl_run_id                           INT           NOT NULL,
    generated_at                          DATETIME      NOT NULL,
    CONSTRAINT pk_ds_service_level_prediction PRIMARY KEY (id),
    CONSTRAINT uq_ds_service_level_prediction_grain UNIQUE (product_key, warehouse_key, model_id),
    CONSTRAINT fk_ds_service_level_prediction_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_ds_service_level_prediction_warehouse_key_dim_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_ds_service_level_prediction_primary_supplier_key_dim_supplier
        FOREIGN KEY (primary_supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_ds_service_level_prediction_source_forecast_model_id
        FOREIGN KEY (source_forecast_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_service_level_prediction_source_supplier_model_id
        FOREIGN KEY (source_supplier_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_service_level_prediction_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_service_level_prediction_warehouse_key (warehouse_key),
    KEY ix_ds_service_level_prediction_model_id (model_id),
    KEY ix_ds_service_level_prediction_stockout_probability (stockout_probability)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
