-- fact_procurement (TDD §4.2/§4.2.1)
--
-- GRAIN: exactly one row per purchase-order line. Idempotency/grain key:
-- source_po_line_id (UNIQUE).
--
-- ============================================================
-- fact_procurement vs. fact_supplier_delivery (stated explicitly, per
-- Phase 4 review requirement — both are sourced from the same OLTP
-- table, atlas_oltp.purchase_order_lines, which is exactly why this
-- needs to be unambiguous):
--
--   fact_procurement       = THE PURCHASE-ORDER EVENT. What was ordered,
--                            from whom, at what cost. One row per PO
--                            line, populated as soon as the line exists —
--                            regardless of whether it has been received.
--
--   fact_supplier_delivery = THE RECEIPT/DELIVERY EVENT. What actually
--                            arrived, when, and in what condition. One
--                            row per PO line's receipt only — a PO line
--                            not yet delivered has a fact_procurement row
--                            but no fact_supplier_delivery row yet (see
--                            14_fact_supplier_delivery.sql).
-- ============================================================
--
-- FKs per TDD §4.2's ER diagram: supplier_key, product_key. warehouse_key
-- is an addition beyond the literal diagram, grounded in the real
-- purchase_orders.warehouse_id column (the receiving DC) — needed for any
-- warehouse-level procurement-spend cut, one of this fact's own named KPIs.
-- supplier_key resolves to the dim_supplier row whose SCD2 version was
-- current as of order_date (Phase 5 concern, not a Phase 4 DDL concern).

CREATE TABLE fact_procurement (
    po_line_key                  INT           NOT NULL AUTO_INCREMENT,
    source_po_line_id            INT           NOT NULL,  -- atlas_oltp.purchase_order_lines.id
    po_number                     VARCHAR(30)   NOT NULL,
    po_line_number                 INT           NOT NULL,
    po_status_code                 VARCHAR(20)   NOT NULL,  -- snapshot of po_statuses.code at load time
    supplier_key                   INT           NOT NULL,  -- SCD2-resolved as of order_date_key
    product_key                    INT           NOT NULL,
    warehouse_key                  INT           NOT NULL,  -- addition beyond TDD's literal ER diagram; see header
    order_date_key                  INT           NOT NULL,
    expected_delivery_date_key    INT          NULL,
    ordered_quantity               INT           NOT NULL,
    unit_cost                       DECIMAL(12,2) NOT NULL,
    extended_cost                   DECIMAL(12,2) NOT NULL,  -- additive: ordered_quantity * unit_cost (procurement spend)
    received_quantity              INT           NOT NULL,
    quality_rejected_quantity      INT           NOT NULL,
    CONSTRAINT pk_fact_procurement PRIMARY KEY (po_line_key),
    CONSTRAINT uq_fact_procurement_source_po_line_id UNIQUE (source_po_line_id),
    CONSTRAINT fk_fact_procurement_supplier_key_dim_supplier
        FOREIGN KEY (supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_fact_procurement_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_procurement_warehouse_key_dim_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_fact_procurement_order_date_key_dim_date
        FOREIGN KEY (order_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_procurement_expected_delivery_date_key_dim_date
        FOREIGN KEY (expected_delivery_date_key) REFERENCES dim_date (date_key),
    KEY ix_fact_procurement_supplier_key (supplier_key),
    KEY ix_fact_procurement_product_key (product_key),
    KEY ix_fact_procurement_warehouse_key (warehouse_key),
    KEY ix_fact_procurement_order_date_key (order_date_key),
    KEY ix_fact_procurement_expected_delivery_date_key (expected_delivery_date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
