-- ds_inventory_policy (Phase 7 Module B, docs/phase7-module-b-completion.md)
--
-- One row per (product, warehouse): a reorder point, safety stock, and
-- service-level inventory target — classic continuous-review inventory
-- theory (Silver/Pyke/Peterson), never a fitted model. EOQ (order
-- quantity) is deliberately absent: this module answers "when to
-- reorder and how much buffer," not "how much to order," per explicit
-- instruction that EOQ stays blocked until ordering-/holding-cost
-- policy inputs are defined.
--
-- Named ds_inventory_policy, not the longer
-- ds_inventory_policy_recommendation this file's own filename implies:
-- MySQL's 64-character identifier limit rejected the longer name's
-- generated FK constraint names (a real, disclosed naming-length
-- constraint hit while applying this DDL, not a stylistic choice).
--
-- "Calculation methodology" is not duplicated as text on every row —
-- it lives once, structured, in ds_model_registry.parameters for this
-- row's model_id, the same pattern every prior Phase 7 module uses.
--
-- source_forecast_model_id / source_supplier_model_id /
-- source_service_level_model_id are literally "forecast version",
-- "supplier score version", "service-level prediction version" from
-- the module brief: the exact ds_model_registry.id of the Module A/C/D
-- models whose outputs fed this row.

CREATE TABLE ds_inventory_policy (
    id                              INT           NOT NULL AUTO_INCREMENT,
    product_key                     INT           NOT NULL,
    warehouse_key                   INT           NOT NULL,
    safety_stock                    DECIMAL(12,2) NOT NULL,
    reorder_point                   DECIMAL(12,2) NOT NULL,
    service_level_inventory_target  DECIMAL(12,2) NOT NULL,
    current_available_quantity      DECIMAL(12,2) NOT NULL,
    balancing_recommendation        VARCHAR(20)   NOT NULL,  -- 'reorder_now' | 'adequate' | 'excess_inventory'
    confidence                      VARCHAR(10)   NOT NULL,  -- 'high' | 'medium'
    contributing_factors            JSON          NOT NULL,
    business_rationale              VARCHAR(500)  NOT NULL,
    primary_supplier_key            INT          NULL,
    source_forecast_model_id        INT           NOT NULL,
    source_supplier_model_id        INT          NULL,
    source_service_level_model_id   INT          NULL,
    model_id                        INT           NOT NULL,  -- this module's own registered formula (module='inventory_policy')
    etl_run_id                      INT           NOT NULL,
    generated_at                     DATETIME      NOT NULL,
    CONSTRAINT pk_ds_inventory_policy PRIMARY KEY (id),
    CONSTRAINT uq_ds_inventory_policy_grain UNIQUE (product_key, warehouse_key, model_id),
    CONSTRAINT fk_ds_inv_policy_product_key
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_ds_inv_policy_warehouse_key
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_ds_inv_policy_primary_supplier_key
        FOREIGN KEY (primary_supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_ds_inv_policy_source_forecast_model_id
        FOREIGN KEY (source_forecast_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_inv_policy_source_supplier_model_id
        FOREIGN KEY (source_supplier_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_inv_policy_source_service_level_model_id
        FOREIGN KEY (source_service_level_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_inv_policy_model_id
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_inventory_policy_warehouse_key (warehouse_key),
    KEY ix_ds_inventory_policy_model_id (model_id),
    KEY ix_ds_inventory_policy_balancing (balancing_recommendation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
