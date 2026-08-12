-- fact_inventory_snapshot (TDD §4.2/§4.2.1, ADR-003 periodic snapshot fact)
--
-- ============================================================
-- GRAIN (stated explicitly, per Phase 4 review requirement):
--   Exactly ONE ROW PER PRODUCT, PER WAREHOUSE, PER SNAPSHOT DATE.
--   Not per zone, not per inventory position, not per transaction.
-- ============================================================
--
-- atlas_oltp.inventory_positions is zone-level (one row per product x
-- warehouse x zone); this fact rolls zones up to the warehouse level for
-- the day, one row per (product, warehouse, day) — a periodic snapshot,
-- not a transactional fact (ADR-003: transactional-only inventory makes
-- "what was inventory on day X" an expensive derived query at scale).
--
-- Grain key / idempotency key for Phase 5's upsert: the composite
-- (product_key, warehouse_key, snapshot_date_key), UNIQUE below. This is
-- both what makes the load idempotent and what enforces the grain
-- statement above at the DB level (see test_grain_uniqueness.py).
--
-- Sparsification (TDD §10): only (product, warehouse) pairs with actual
-- activity get a row on a given day — a Phase 5 row-selection decision,
-- not a Phase 4 DDL concern; this table permits sparse rows by design
-- (no requirement that every product x warehouse combination exists for
-- every date).
--
-- Non-additive/derived measures (days_of_supply, overstock value,
-- capacity_utilization) are deliberately NOT stored — they require
-- trailing-demand or threshold business rules not defined anywhere in
-- frozen scope (SRS/TDD), and are computed downstream (Phase 7).

CREATE TABLE fact_inventory_snapshot (
    inventory_snapshot_key  INT           NOT NULL AUTO_INCREMENT,
    snapshot_date_key       INT           NOT NULL,
    product_key             INT           NOT NULL,
    warehouse_key           INT           NOT NULL,
    quantity_on_hand        INT           NOT NULL,  -- additive
    quantity_reserved       INT           NOT NULL,  -- additive
    quantity_available      INT           NOT NULL,  -- additive; materialized quantity_on_hand - quantity_reserved
    inventory_value         DECIMAL(12,2) NOT NULL,  -- additive; quantity_on_hand * dim_product.current_unit_cost at load time
    is_stockout             TINYINT(1)    NOT NULL,  -- additive flag; quantity_on_hand = 0
    CONSTRAINT pk_fact_inventory_snapshot PRIMARY KEY (inventory_snapshot_key),
    CONSTRAINT uq_fact_inventory_snapshot_grain
        UNIQUE (product_key, warehouse_key, snapshot_date_key),
    CONSTRAINT fk_fact_inventory_snapshot_snapshot_date_key_dim_date
        FOREIGN KEY (snapshot_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_inventory_snapshot_product_key_dim_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_inventory_snapshot_warehouse_key_dim_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    KEY ix_fact_inventory_snapshot_snapshot_date_key (snapshot_date_key),
    KEY ix_fact_inventory_snapshot_warehouse_key (warehouse_key)
    -- Composite index (warehouse_key, snapshot_date_key) per TDD §4.3 is
    -- added in 30_composite_indexes.sql, not here — see that file's header.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
