-- dim_customer (TDD §4.2, conformed dimension; ADR-011 surrogate-key convention)
--
-- Type 1. Grain: one row per customer.
--
-- Source: atlas_oltp.customers — see docs/data-dictionary.md.
-- FK to dim_region (outrigger — see 02_dim_region.sql).

CREATE TABLE dim_customer (
    customer_key      INT           NOT NULL AUTO_INCREMENT,
    customer_id       INT           NOT NULL,  -- OLTP customers.id (natural key, not reused as PK)
    customer_code     VARCHAR(30)   NOT NULL,
    customer_name     VARCHAR(150)  NOT NULL,
    email             VARCHAR(150)  NULL,
    phone             VARCHAR(30)   NULL,
    address_line1     VARCHAR(200)  NULL,
    city              VARCHAR(100)  NULL,
    state_province    VARCHAR(100)  NULL,
    postal_code       VARCHAR(20)   NULL,
    country           VARCHAR(100)  NULL,
    region_key        INT           NOT NULL,
    source_updated_at DATETIME      NOT NULL,
    CONSTRAINT pk_dim_customer PRIMARY KEY (customer_key),
    CONSTRAINT uq_dim_customer_customer_id UNIQUE (customer_id),
    CONSTRAINT uq_dim_customer_customer_code UNIQUE (customer_code),
    CONSTRAINT fk_dim_customer_region_key_dim_region
        FOREIGN KEY (region_key) REFERENCES dim_region (region_key),
    KEY ix_dim_customer_region_key (region_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
