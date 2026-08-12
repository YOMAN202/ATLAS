-- Composite indexes (TDD §4.3) — the two explicitly named indexes only.
--
-- Every FK column already has a supporting single-column index (declared
-- inline with each fact's CREATE TABLE, or auto-created by InnoDB where
-- not explicit). This file is genuinely only the *additional* composite
-- indexes TDD §4.3 names by name for common dashboard filter patterns:
--
--   "(warehouse_id, date_id) on fact_inventory_snapshot,
--    (supplier_id, delivery_date) on fact_supplier_delivery"
--
-- Covering indexes are explicitly deferred (TDD §4.3: "considered for the
-- highest-traffic dashboard queries once query patterns are known from
-- FR-7.x dashboards; documented per-query in an ADR rather than
-- speculatively indexed everywhere") — none are added here.

ALTER TABLE fact_inventory_snapshot
    ADD INDEX ix_fact_inventory_snapshot_warehouse_date (warehouse_key, snapshot_date_key);

ALTER TABLE fact_supplier_delivery
    ADD INDEX ix_fact_supplier_delivery_supplier_date (supplier_key, delivery_date_key);
