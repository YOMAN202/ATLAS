-- fact_supplier_delivery (TDD §4.2/§4.2.1)
--
-- GRAIN: exactly one row per delivery event. Idempotency/grain key:
-- source_po_line_id (UNIQUE) — same source row as fact_procurement, but
-- this fact only gets a row once that line has actually been received
-- (delivery_date_key is NOT NULL — a delivery event without a date isn't
-- an event).
--
-- ============================================================
-- fact_supplier_delivery vs. fact_procurement (see 13_fact_procurement.sql
-- for the full statement — repeated here for whichever file is read
-- first):
--
--   fact_procurement       = THE PURCHASE-ORDER EVENT (what was ordered).
--   fact_supplier_delivery = THE RECEIPT/DELIVERY EVENT (what arrived).
--
-- Both are sourced 1:1 from atlas_oltp.purchase_order_lines (there is no
-- separate OLTP delivery-event table — "a PO line's receipt IS the
-- delivery event", per docs/data-dictionary.md), so the two facts will
-- always share the same natural key and, once every ordered line is
-- eventually received, the same eventual row count. The grain distinction
-- is real and Kimball-legitimate (two fact tables can represent two
-- different business processes over the same source rows) — this is not
-- an oversight, see ADR-013.
-- ============================================================
--
-- Dimension links are TDD-silent (the ER diagram doesn't wire this fact
-- to anything) and are designed here, grounded in the real OLTP columns:
-- supplier_key, product_key, warehouse_key (the receiving DC,
-- purchase_orders.warehouse_id), delivery_date_key, expected_delivery_date_key
-- (needed for lead-time variance, this fact's own named KPI). See ADR-013.
--
-- Composite index (supplier_key, delivery_date_key) per TDD §4.3 is added
-- in 30_composite_indexes.sql, not here.

CREATE TABLE fact_supplier_delivery (
    delivery_key                   INT           NOT NULL AUTO_INCREMENT,
    source_po_line_id              INT           NOT NULL,  -- atlas_oltp.purchase_order_lines.id
    po_number                       VARCHAR(30)   NOT NULL,
    po_line_number                   INT           NOT NULL,
    supplier_key                     INT           NOT NULL,  -- SCD2-resolved as of delivery_date_key
    product_key                      INT           NOT NULL,
    warehouse_key                    INT           NOT NULL,  -- SCD2-resolved as of delivery_date_key; receiving DC
    delivery_date_key                 INT           NOT NULL,  -- NOT NULL: a delivery event without a date isn't an event
    expected_delivery_date_key       INT           NOT NULL,
    ordered_quantity                 INT           NOT NULL,
    received_quantity                INT           NOT NULL,
    quality_rejected_quantity        INT           NOT NULL,
    quality_accepted_quantity        INT           NOT NULL,  -- additive: received_quantity - quality_rejected_quantity
    is_on_time                      TINYINT(1)    NOT NULL,  -- additive flag: actual_delivery_date <= expected_delivery_date
    lead_time_variance_days           INT           NOT NULL,  -- additive/averageable: actual - expected, in days
    CONSTRAINT pk_fact_supplier_delivery PRIMARY KEY (delivery_key),
    CONSTRAINT uq_fact_supplier_delivery_source_po_line_id UNIQUE (source_po_line_id),
    CONSTRAINT fk_fact_supplier_delivery_supplier_key_dim_supplier
        FOREIGN KEY (supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_fact_supplier_delivery_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_supplier_delivery_warehouse_key_dim_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_fact_supplier_delivery_delivery_date_key_dim_date
        FOREIGN KEY (delivery_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_supplier_delivery_expected_delivery_date_key_dim_date
        FOREIGN KEY (expected_delivery_date_key) REFERENCES dim_date (date_key),
    KEY ix_fact_supplier_delivery_supplier_key (supplier_key),
    KEY ix_fact_supplier_delivery_product_key (product_key),
    KEY ix_fact_supplier_delivery_warehouse_key (warehouse_key),
    KEY ix_fact_supplier_delivery_delivery_date_key (delivery_date_key),
    KEY ix_fact_supplier_delivery_expected_delivery_date_key (expected_delivery_date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
