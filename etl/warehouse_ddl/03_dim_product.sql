-- dim_product (TDD §4.2, conformed dimension; ADR-011 surrogate-key convention)
--
-- Type 1 (TDD §4.2: "Product ... dimension[s] are treated as Type 1
-- (overwrite) for MVP since their attribute changes aren't analytically
-- significant at this scope"). Grain: one row per product.
--
-- Source: atlas_oltp.products — see docs/data-dictionary.md. Empty shell
-- here; Phase 5 populates and refreshes (overwrite) from the OLTP source.

CREATE TABLE dim_product (
    product_key       INT           NOT NULL AUTO_INCREMENT,
    product_id        INT           NOT NULL,  -- OLTP products.id (natural key, not reused as PK)
    sku               VARCHAR(30)   NOT NULL,
    product_name      VARCHAR(200)  NOT NULL,
    category          VARCHAR(100)  NULL,
    unit_of_measure   VARCHAR(10)   NOT NULL,
    current_unit_cost DECIMAL(12,2) NOT NULL,
    current_unit_price DECIMAL(12,2) NOT NULL,
    is_active         TINYINT(1)    NOT NULL,
    source_updated_at DATETIME      NOT NULL,  -- OLTP products.updated_at, Type-1 refresh watermark
    CONSTRAINT pk_dim_product PRIMARY KEY (product_key),
    CONSTRAINT uq_dim_product_product_id UNIQUE (product_id),
    CONSTRAINT uq_dim_product_sku UNIQUE (sku)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
