-- fact_orders (TDD §4.2/§4.2.1)
--
-- GRAIN: exactly one row per order line. Not per order, not per product.
-- Idempotency/grain key: source_order_line_id (UNIQUE) — one order line
-- in atlas_oltp.order_lines produces exactly one row here.
--
-- FKs per TDD §4.2's ER diagram: order_date_key, product_key, customer_key.
-- fulfillment_warehouse_key is an addition beyond the literal diagram,
-- grounded in the real order_lines.fulfillment_warehouse_id column
-- (nullable in source — a line not yet allocated has no warehouse), added
-- because "cost-to-serve" (TDD §4.2.1's own named KPI for this fact) is
-- not location-aware without it.
--
-- Measures are additive only, sourced directly from order_lines; no
-- ratios stored (e.g. no "fulfillment rate" column — that is
-- SUM(allocated_quantity)/SUM(ordered_quantity) computed at query time).

CREATE TABLE fact_orders (
    order_line_key          INT           NOT NULL AUTO_INCREMENT,
    source_order_line_id    INT           NOT NULL,  -- atlas_oltp.order_lines.id
    order_number             VARCHAR(30)   NOT NULL,
    order_line_number        INT           NOT NULL,
    shipment_number           VARCHAR(30)   NULL,      -- drill-through only, no FK (order_lines.shipment_id is nullable)
    order_date_key           INT           NOT NULL,
    product_key               INT           NOT NULL,
    customer_key              INT           NOT NULL,
    fulfillment_warehouse_key INT          NULL,       -- addition beyond TDD's literal ER diagram; see header
    ordered_quantity         INT           NOT NULL,
    allocated_quantity       INT           NOT NULL,
    backordered_quantity     INT           NOT NULL,
    unit_price                DECIMAL(12,2) NOT NULL,
    unit_cost                 DECIMAL(12,2) NOT NULL,
    extended_revenue          DECIMAL(12,2) NOT NULL,  -- additive: allocated_quantity * unit_price
    extended_cost              DECIMAL(12,2) NOT NULL,  -- additive: allocated_quantity * unit_cost
    gross_margin               DECIMAL(12,2) NOT NULL,  -- additive: extended_revenue - extended_cost
    CONSTRAINT pk_fact_orders PRIMARY KEY (order_line_key),
    CONSTRAINT uq_fact_orders_source_order_line_id UNIQUE (source_order_line_id),
    CONSTRAINT fk_fact_orders_order_date_key_dim_date
        FOREIGN KEY (order_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_orders_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_orders_customer_key_dim_customer
        FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key),
    CONSTRAINT fk_fact_orders_fulfillment_warehouse_key_dim_warehouse
        FOREIGN KEY (fulfillment_warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    KEY ix_fact_orders_order_date_key (order_date_key),
    KEY ix_fact_orders_product_key (product_key),
    KEY ix_fact_orders_customer_key (customer_key),
    KEY ix_fact_orders_fulfillment_warehouse_key (fulfillment_warehouse_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
