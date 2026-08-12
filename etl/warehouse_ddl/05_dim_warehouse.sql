-- dim_warehouse (TDD §4.2, conformed dimension; ADR-011 surrogate-key
-- convention; ADR-012 SCD2 column convention)
--
-- SCD Type 2 (TDD §4.2, ADR-006: "capacity changes over time"). Tracked
-- attribute is total_capacity_units.
--
-- Grain: one row per warehouse PER VERSION — warehouse_id intentionally
-- repeats across rows; only (warehouse_id, effective_from) is unique.
-- Same MySQL partial-unique-index limitation as dim_supplier (ADR-012):
-- "exactly one is_current = 1 row per warehouse_id" is ETL-enforced.
--
-- Source: atlas_oltp.warehouses — see docs/data-dictionary.md.
-- FK to dim_region (outrigger — see 02_dim_region.sql).

CREATE TABLE dim_warehouse (
    warehouse_key           INT           NOT NULL AUTO_INCREMENT,
    warehouse_id            INT           NOT NULL,  -- OLTP warehouses.id; repeats across versions
    warehouse_code          VARCHAR(20)   NOT NULL,
    warehouse_name          VARCHAR(150)  NOT NULL,
    address_line1           VARCHAR(200)  NULL,
    city                    VARCHAR(100)  NULL,
    state_province          VARCHAR(100)  NULL,
    postal_code             VARCHAR(20)   NULL,
    country                 VARCHAR(100)  NULL,
    region_key              INT           NOT NULL,
    total_capacity_units    INT           NOT NULL,  -- tracked attribute (TDD §4.2)
    is_active               TINYINT(1)    NOT NULL,
    effective_from          DATE          NOT NULL,
    effective_to            DATE          NULL,
    is_current              TINYINT(1)    NOT NULL,
    source_updated_at       DATETIME      NOT NULL,
    CONSTRAINT pk_dim_warehouse PRIMARY KEY (warehouse_key),
    CONSTRAINT uq_dim_warehouse_warehouse_id_effective_from
        UNIQUE (warehouse_id, effective_from),
    CONSTRAINT fk_dim_warehouse_region_key_dim_region
        FOREIGN KEY (region_key) REFERENCES dim_region (region_key),
    KEY ix_dim_warehouse_warehouse_id (warehouse_id),
    KEY ix_dim_warehouse_is_current (is_current),
    KEY ix_dim_warehouse_region_key (region_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
