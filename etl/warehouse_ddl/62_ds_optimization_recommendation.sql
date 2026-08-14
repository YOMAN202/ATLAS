-- ds_optimization_recommendation (Phase 7.2 Module F, docs/phase7-module-f-completion.md)
--
-- Two recommendation types, one table, distinguished by
-- recommendation_type (mirrors ds_demand_forecast's grain_type
-- convention): 'right_sizing' (one shipment, assigned to a more
-- expensive vehicle type than its quantity requires) and
-- 'consolidation' (multiple same-day/origin/destination shipments
-- that could ship as one). Both are closed-form, deterministic
-- heuristics over dim_carrier.vehicle_cost_per_mile/
-- vehicle_capacity_units and fact_shipments — no external
-- optimization engine, per explicit instruction.
--
-- Scoped to a real, representative 30-day analysis window (the same
-- "recent window, not the full year" convention Module A's/D's own
-- backtests already use), not the full 696,747-shipment history —
-- disclosed explicitly in the completion report, not silently
-- narrowed.

CREATE TABLE ds_optimization_recommendation (
    id                        INT           NOT NULL AUTO_INCREMENT,
    recommendation_type       VARCHAR(20)   NOT NULL,  -- 'right_sizing' | 'consolidation'
    origin_warehouse_key      INT           NOT NULL,
    shipment_date              DATE          NOT NULL,
    shipment_numbers           JSON          NOT NULL,  -- 1 entry for right_sizing, 2+ for consolidation
    total_quantity              INT           NOT NULL,
    distance_miles              DECIMAL(10,2) NOT NULL,
    current_vehicle_type_code  VARCHAR(20)   NOT NULL,
    current_total_cost         DECIMAL(12,2) NOT NULL,
    recommended_vehicle_type_code VARCHAR(20) NOT NULL,
    recommended_total_cost     DECIMAL(12,2) NOT NULL,
    estimated_savings          DECIMAL(12,2) NOT NULL,
    confidence                 VARCHAR(10)   NOT NULL,
    contributing_factors       JSON          NOT NULL,
    business_rationale         VARCHAR(500)  NOT NULL,
    model_id                    INT           NOT NULL,  -- this module's own registered formula (module='route_cost_optimization')
    etl_run_id                  INT           NOT NULL,
    generated_at                 DATETIME      NOT NULL,
    CONSTRAINT pk_ds_optimization_recommendation PRIMARY KEY (id),
    CONSTRAINT fk_ds_opt_rec_origin_warehouse_key
        FOREIGN KEY (origin_warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_ds_opt_rec_model_id
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_opt_rec_type (recommendation_type),
    KEY ix_ds_opt_rec_warehouse (origin_warehouse_key),
    KEY ix_ds_opt_rec_savings (estimated_savings)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
