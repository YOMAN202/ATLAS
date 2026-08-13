-- ds_demand_forecast (Phase 7 Module A, docs/phase7-architecture.md §5)
--
-- Three grains in one table, distinguished by grain_type: 'sku_warehouse'
-- (product_key + warehouse_key populated), 'category' (category
-- populated), 'region' (region_key populated) — the other grain
-- columns are NULL for a given row. No UNIQUE constraint spans these
-- nullable columns: MySQL never enforces uniqueness across a tuple
-- containing a NULL (each NULL compares as distinct from every other
-- NULL), so a mixed-nullable-column UNIQUE key here would silently
-- fail to prevent duplicates for the category/region grains. Idempotent
-- reruns are instead achieved the same way summary_daily_revenue_by_region
-- already does it (etl/stage_b.py's process_summary_daily_revenue_by_region):
-- DELETE the prior rows for a given (grain_type, model_id) before
-- INSERTing the fresh set, not an upsert.
--
-- confidence_interval_low/high derive from the model's own historical
-- residual distribution (docs/phase7-architecture.md §5) — never a
-- fabricated number.
--
-- etl_run_id ties a forecast to the exact warehouse state it was
-- computed from, the same "as of" discipline every Phase 6 API
-- response already uses (backend/app/api/schemas.py's AsOf).

CREATE TABLE ds_demand_forecast (
    id                       INT           NOT NULL AUTO_INCREMENT,
    grain_type               VARCHAR(20)   NOT NULL,  -- 'sku_warehouse' | 'category' | 'region'
    product_key              INT           NULL,
    warehouse_key            INT           NULL,
    category                 VARCHAR(100)  NULL,
    region_key               INT           NULL,
    forecast_date            DATE          NOT NULL,
    predicted_quantity       DECIMAL(12,2) NOT NULL,
    confidence_interval_low  DECIMAL(12,2) NULL,
    confidence_interval_high DECIMAL(12,2) NULL,
    model_id                 INT           NOT NULL,
    etl_run_id               INT           NOT NULL,
    generated_at             DATETIME      NOT NULL,
    CONSTRAINT pk_ds_demand_forecast PRIMARY KEY (id),
    CONSTRAINT fk_ds_demand_forecast_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_demand_forecast_etl_run_id_etl_run_log
        FOREIGN KEY (etl_run_id) REFERENCES etl_run_log (id),
    CONSTRAINT fk_ds_demand_forecast_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_ds_demand_forecast_warehouse_key_dim_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_ds_demand_forecast_region_key_dim_region
        FOREIGN KEY (region_key) REFERENCES dim_region (region_key),
    KEY ix_ds_demand_forecast_grain_model (grain_type, model_id),
    KEY ix_ds_demand_forecast_forecast_date (forecast_date),
    KEY ix_ds_demand_forecast_product_warehouse (product_key, warehouse_key),
    KEY ix_ds_demand_forecast_category (category),
    KEY ix_ds_demand_forecast_region_key (region_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
