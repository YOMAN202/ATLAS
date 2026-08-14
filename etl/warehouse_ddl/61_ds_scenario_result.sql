-- ds_scenario_result (Phase 7.2 Module E, docs/phase7-module-e-completion.md)
--
-- One row per scenario: aggregate projected outcomes vs. the real
-- baseline (Module D/B's already-persisted, unperturbed outputs),
-- across the same 2,290 qualifying (product, warehouse) pairs
-- Modules A/D/B already evaluate. Aggregate, not per-pair, by design
-- (docs/phase7-2-architecture.md §1.3): the required outputs
-- (projected stockouts, backorders, investment, service level,
-- procurement volume, supplier utilization) are comparison-level
-- metrics — what a "What-if Comparison" view actually needs is
-- baseline-vs-scenario at the scenario grain, not a 2,290-row-per-
-- scenario breakdown. Per-pair detail is available in each row's
-- key_drivers JSON (the most-affected pairs), not a separate table.
--
-- source_forecast_model_id / source_supplier_model_id /
-- source_service_level_model_id / source_inventory_policy_model_id are
-- literally "forecast version" / "supplier score version" /
-- "service-level prediction version" / "inventory policy version"
-- from the module brief.

CREATE TABLE ds_scenario_result (
    id                              INT           NOT NULL AUTO_INCREMENT,
    scenario_id                     INT           NOT NULL,
    baseline_avg_stockout_probability     DECIMAL(6,5)  NOT NULL,
    scenario_avg_stockout_probability     DECIMAL(6,5)  NOT NULL,
    baseline_n_high_stockout_risk         INT           NOT NULL,
    scenario_n_high_stockout_risk         INT           NOT NULL,
    baseline_avg_backorder_probability    DECIMAL(6,5)  NOT NULL,
    scenario_avg_backorder_probability    DECIMAL(6,5)  NOT NULL,
    baseline_inventory_investment         DECIMAL(14,2) NOT NULL,
    scenario_inventory_investment         DECIMAL(14,2) NOT NULL,
    baseline_avg_service_level            DECIMAL(6,5)  NOT NULL,
    scenario_avg_service_level            DECIMAL(6,5)  NOT NULL,
    baseline_procurement_volume           DECIMAL(14,2) NOT NULL,
    scenario_procurement_volume           DECIMAL(14,2) NOT NULL,
    baseline_n_suppliers_utilized         INT           NOT NULL,
    scenario_n_suppliers_utilized         INT           NOT NULL,
    changed_assumptions             JSON          NOT NULL,
    affected_modules                JSON          NOT NULL,
    key_drivers                     JSON          NOT NULL,
    confidence                      VARCHAR(10)   NOT NULL,
    sensitivity_indicators          JSON          NOT NULL,
    n_pairs_evaluated                INT           NOT NULL,
    source_forecast_model_id        INT           NOT NULL,
    source_supplier_model_id        INT          NULL,
    source_service_level_model_id   INT          NULL,
    source_inventory_policy_model_id INT         NULL,
    etl_run_id                       INT           NOT NULL,
    generated_at                      DATETIME      NOT NULL,
    CONSTRAINT pk_ds_scenario_result PRIMARY KEY (id),
    CONSTRAINT uq_ds_scenario_result_scenario UNIQUE (scenario_id),
    CONSTRAINT fk_ds_scenario_result_scenario_id
        FOREIGN KEY (scenario_id) REFERENCES ds_scenario (id),
    CONSTRAINT fk_ds_scenario_result_source_forecast_model_id
        FOREIGN KEY (source_forecast_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_scenario_result_source_supplier_model_id
        FOREIGN KEY (source_supplier_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_scenario_result_source_service_level_model_id
        FOREIGN KEY (source_service_level_model_id) REFERENCES ds_model_registry (id),
    CONSTRAINT fk_ds_scenario_result_source_inv_policy_model_id
        FOREIGN KEY (source_inventory_policy_model_id) REFERENCES ds_model_registry (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
