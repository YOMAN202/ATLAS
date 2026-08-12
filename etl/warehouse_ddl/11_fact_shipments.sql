-- fact_shipments (TDD §4.2/§4.2.1)
--
-- GRAIN: exactly one row per shipment. Idempotency/grain key:
-- source_shipment_id (UNIQUE).
--
-- FKs per TDD §4.2's ER diagram: carrier_key, origin_warehouse_key.
-- ship_date_key is an unavoidable addition (every fact needs its date);
-- destination_warehouse_key/destination_customer_key mirror OLTP's own
-- shipments table exactly (FR-2.3 transfer vs FR-3.2 delivery, XOR by
-- design there) — the CHECK constraint below enforces the same
-- invariant here rather than silently dropping it.
--
-- Non-additive ratios (cost-per-mile, on-time %) are deliberately NOT
-- stored — is_on_time is stored as an additive flag instead, and ratios
-- are computed from it (and shipping_cost/distance_miles) at query time.

CREATE TABLE fact_shipments (
    shipment_key                 INT           NOT NULL AUTO_INCREMENT,
    source_shipment_id           INT           NOT NULL,  -- atlas_oltp.shipments.id
    shipment_number                VARCHAR(30)   NOT NULL,
    status_code                   VARCHAR(20)   NOT NULL,  -- snapshot of shipment_statuses.code at load time
    carrier_key                   INT           NOT NULL,
    origin_warehouse_key          INT           NOT NULL,
    destination_warehouse_key    INT          NULL,
    destination_customer_key     INT          NULL,
    ship_date_key                 INT           NOT NULL,
    estimated_delivery_date_key  INT          NULL,
    actual_delivery_date_key     INT          NULL,
    distance_miles                 DECIMAL(10,2) NULL,
    shipping_cost                  DECIMAL(12,2) NULL,
    is_on_time                    TINYINT(1)    NULL,      -- additive flag; NULL until actual_delivery_date_key is known
    transit_days                   INT          NULL,
    CONSTRAINT pk_fact_shipments PRIMARY KEY (shipment_key),
    CONSTRAINT uq_fact_shipments_source_shipment_id UNIQUE (source_shipment_id),
    CONSTRAINT ck_fact_shipments_destination_xor
        CHECK (
            (destination_warehouse_key IS NOT NULL AND destination_customer_key IS NULL)
            OR (destination_warehouse_key IS NULL AND destination_customer_key IS NOT NULL)
        ),
    CONSTRAINT fk_fact_shipments_carrier_key_dim_carrier
        FOREIGN KEY (carrier_key) REFERENCES dim_carrier (carrier_key),
    CONSTRAINT fk_fact_shipments_origin_warehouse_key_dim_warehouse
        FOREIGN KEY (origin_warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_fact_shipments_destination_warehouse_key_dim_warehouse
        FOREIGN KEY (destination_warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_fact_shipments_destination_customer_key_dim_customer
        FOREIGN KEY (destination_customer_key) REFERENCES dim_customer (customer_key),
    CONSTRAINT fk_fact_shipments_ship_date_key_dim_date
        FOREIGN KEY (ship_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_shipments_estimated_delivery_date_key_dim_date
        FOREIGN KEY (estimated_delivery_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_shipments_actual_delivery_date_key_dim_date
        FOREIGN KEY (actual_delivery_date_key) REFERENCES dim_date (date_key),
    KEY ix_fact_shipments_carrier_key (carrier_key),
    KEY ix_fact_shipments_origin_warehouse_key (origin_warehouse_key),
    KEY ix_fact_shipments_destination_warehouse_key (destination_warehouse_key),
    KEY ix_fact_shipments_destination_customer_key (destination_customer_key),
    KEY ix_fact_shipments_ship_date_key (ship_date_key),
    KEY ix_fact_shipments_estimated_delivery_date_key (estimated_delivery_date_key),
    KEY ix_fact_shipments_actual_delivery_date_key (actual_delivery_date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
