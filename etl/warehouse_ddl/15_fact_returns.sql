-- fact_returns (TDD §4.2/§4.2.1)
--
-- GRAIN: exactly one row per return line. Idempotency/grain key:
-- source_return_line_id (UNIQUE).
--
-- Dimension links are TDD-silent (the ER diagram doesn't wire this fact
-- to anything) and are designed here: product_key (via
-- return_lines.order_line_id -> order_lines.product_id), customer_key
-- (via returns.order_id -> orders.customer_id), return_date_key.
--
-- reason_code/disposition_code are kept as degenerate text columns
-- (copied from return_reasons.code / return_dispositions.code) rather
-- than promoted to new conformed dimensions — the frozen dimension list
-- is exactly the 7 named in TDD §4.2; promoting them would silently
-- expand it. disposition_code is nullable because
-- atlas_oltp.return_lines.disposition_id is null until inspected (BR-5).
--
-- is_quality_related is deliberately NOT stored — classifying which
-- reason codes count as "quality-driven" (for the "quality-driven return
-- share" KPI) is a business rule not defined anywhere in frozen scope;
-- left to Phase 5 transform / Phase 7 BI logic operating on the raw
-- reason_code, not invented here.

CREATE TABLE fact_returns (
    return_line_key           INT           NOT NULL AUTO_INCREMENT,
    source_return_line_id     INT           NOT NULL,  -- atlas_oltp.return_lines.id
    return_number               VARCHAR(30)   NOT NULL,
    order_number                 VARCHAR(30)   NOT NULL,
    reason_code                  VARCHAR(20)   NOT NULL,  -- degenerate; not promoted to a junk dimension, see header
    disposition_code             VARCHAR(20)   NULL,       -- degenerate; NULL until inspected (BR-5)
    product_key                  INT           NOT NULL,
    customer_key                  INT           NOT NULL,
    return_date_key                INT           NOT NULL,
    returned_quantity             INT           NOT NULL,
    unit_price                     DECIMAL(12,2) NOT NULL,  -- from the originating order_lines.unit_price
    unit_cost                      DECIMAL(12,2) NOT NULL,  -- from the originating order_lines.unit_cost
    return_value                   DECIMAL(12,2) NOT NULL,  -- additive: returned_quantity * unit_price
    return_cost_value              DECIMAL(12,2) NOT NULL,  -- additive: returned_quantity * unit_cost
    CONSTRAINT pk_fact_returns PRIMARY KEY (return_line_key),
    CONSTRAINT uq_fact_returns_source_return_line_id UNIQUE (source_return_line_id),
    CONSTRAINT fk_fact_returns_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_returns_customer_key_dim_customer
        FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key),
    CONSTRAINT fk_fact_returns_return_date_key_dim_date
        FOREIGN KEY (return_date_key) REFERENCES dim_date (date_key),
    KEY ix_fact_returns_product_key (product_key),
    KEY ix_fact_returns_customer_key (customer_key),
    KEY ix_fact_returns_return_date_key (return_date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
