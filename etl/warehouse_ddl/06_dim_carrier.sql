-- dim_carrier (TDD §4.2, conformed dimension; ADR-011 surrogate-key convention)
--
-- Type 1 (TDD §4.2: "... and carrier dimension[s] are treated as Type 1
-- (overwrite) for MVP"). Grain: one row per carrier.
--
-- Source: atlas_oltp.carriers, denormalized with its vehicle_types lookup
-- row (vehicle_types is a small reference table, not one of the 7 named
-- conformed dimensions, so it is collapsed into dim_carrier rather than
-- snowflaked out) — see docs/data-dictionary.md.

CREATE TABLE dim_carrier (
    carrier_key            INT           NOT NULL AUTO_INCREMENT,
    carrier_id             INT           NOT NULL,  -- OLTP carriers.id (natural key, not reused as PK)
    carrier_code            VARCHAR(20)   NOT NULL,
    carrier_name            VARCHAR(150)  NOT NULL,
    vehicle_type_code      VARCHAR(20)   NOT NULL,
    vehicle_type_name      VARCHAR(100)  NOT NULL,
    vehicle_capacity_units INT           NOT NULL,
    vehicle_cost_per_mile  DECIMAL(12,2) NOT NULL,
    is_active              TINYINT(1)    NOT NULL,
    source_updated_at      DATETIME      NOT NULL,
    CONSTRAINT pk_dim_carrier PRIMARY KEY (carrier_key),
    CONSTRAINT uq_dim_carrier_carrier_id UNIQUE (carrier_id),
    CONSTRAINT uq_dim_carrier_carrier_code UNIQUE (carrier_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
