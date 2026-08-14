-- ds_policy_sensitivity (Phase 7 Module B, docs/phase7-module-b-completion.md)
--
-- The "policy sensitivity analysis" deliverable, stored: aggregate
-- outcomes of running the SAME reorder-point/safety-stock formula at
-- several target service levels (90%/95%/99%), each validated via the
-- same walk-forward inventory simulation used for §validation
-- (backend/app/decision_support/inventory_policy_simulation.py) — one
-- mechanism serving both the validation report and the sensitivity
-- curve. Shows the real, expected tradeoff: a higher target service
-- level costs more safety stock and inventory investment, in exchange
-- for a higher achieved service level.
--
-- achieved_service_level (from simulation) is the per-scenario
-- validation result; also recorded per-scenario in ds_experiment_run
-- (metric_name='ACHIEVED_SERVICE_LEVEL') for consistency with every
-- other Phase 7 module's shared validation-metric table — this table
-- is the richer aggregate (inventory cost, average safety stock) that
-- table's narrow schema can't hold.

CREATE TABLE ds_policy_sensitivity (
    id                        INT           NOT NULL AUTO_INCREMENT,
    model_id                  INT           NOT NULL,
    target_service_level      DECIMAL(5,4)  NOT NULL,
    avg_safety_stock          DECIMAL(12,2) NOT NULL,
    avg_reorder_point         DECIMAL(12,2) NOT NULL,
    total_inventory_investment DECIMAL(14,2) NOT NULL,  -- SUM(safety_stock * current_unit_cost)
    achieved_service_level    DECIMAL(6,5)  NOT NULL,
    n_pairs                   INT           NOT NULL,
    etl_run_id                 INT           NOT NULL,
    generated_at                DATETIME      NOT NULL,
    CONSTRAINT pk_ds_policy_sensitivity PRIMARY KEY (id),
    CONSTRAINT uq_ds_policy_sensitivity_grain UNIQUE (model_id, target_service_level),
    CONSTRAINT fk_ds_policy_sensitivity_model_id_ds_model_registry
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
