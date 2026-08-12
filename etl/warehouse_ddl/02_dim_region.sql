-- dim_region (TDD §4.2, conformed dimension; ADR-011 surrogate-key convention)
--
-- Type 1. Grain: one row per region. Not directly linked to any fact in
-- TDD §4.2's ER diagram — reached only through dim_customer/dim_warehouse
-- (a conformed "outrigger" dimension), since region isn't itself a fact
-- attribute anywhere in the OLTP source.
--
-- Source: atlas_oltp.regions (id, code, name) — see docs/data-dictionary.md.
-- Empty shell here; Phase 5 populates from the OLTP source table.

CREATE TABLE dim_region (
    region_key    INT          NOT NULL AUTO_INCREMENT,
    region_id     INT          NOT NULL,  -- OLTP regions.id (natural key, not reused as PK)
    region_code   VARCHAR(20)  NOT NULL,
    region_name   VARCHAR(100) NOT NULL,
    source_updated_at DATETIME NOT NULL,  -- OLTP regions.updated_at, watermark for Type-1 refresh
    CONSTRAINT pk_dim_region PRIMARY KEY (region_key),
    CONSTRAINT uq_dim_region_region_id UNIQUE (region_id),
    CONSTRAINT uq_dim_region_region_code UNIQUE (region_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
