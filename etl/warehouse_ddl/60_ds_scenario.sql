-- ds_scenario (Phase 7.2 Module E, docs/phase7-module-e-completion.md)
--
-- One row per precomputed scenario definition. Per docs/phase7-2-
-- architecture.md §1.2: scenarios are a curated, precomputed library
-- (matching every prior Phase 7 module's batch-compute-then-display
-- pattern), not live user-submitted parameters — this codebase has no
-- write-capable dashboard route anywhere, and adding one is a real
-- architectural expansion this pass deliberately does not make.
--
-- "Calculation methodology" for a scenario type lives in
-- ds_model_registry.parameters for this module's model_id, same as
-- every prior module — this table's own `parameters` column is the
-- SPECIFIC perturbation this one scenario applies (e.g. {"pct": 0.3}
-- for a 30% demand surge), not the methodology itself.

CREATE TABLE ds_scenario (
    id              INT           NOT NULL AUTO_INCREMENT,
    scenario_type   VARCHAR(40)   NOT NULL,  -- 'demand_surge' | 'demand_decline' | 'supplier_disruption' | ...
    scenario_name   VARCHAR(100)  NOT NULL,
    parameters      JSON          NOT NULL,
    description     VARCHAR(500)  NOT NULL,
    model_id        INT           NOT NULL,  -- this module's own registered formula (module='scenario_simulation')
    etl_run_id      INT           NOT NULL,
    generated_at     DATETIME      NOT NULL,
    CONSTRAINT pk_ds_scenario PRIMARY KEY (id),
    CONSTRAINT uq_ds_scenario_name_model UNIQUE (scenario_name, model_id),
    CONSTRAINT fk_ds_scenario_model_id
        FOREIGN KEY (model_id) REFERENCES ds_model_registry (id),
    KEY ix_ds_scenario_scenario_type (scenario_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
