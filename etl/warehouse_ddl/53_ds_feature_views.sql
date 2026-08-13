-- Feature views (Phase 7 Module A, docs/phase7-architecture.md §4)
--
-- Read-only SQL views computed directly from the frozen warehouse —
-- no new tables, no data duplication, no ETL work. Every forecasting
-- model reads the same, consistently-defined series instead of each
-- reimplementing "what's daily demand" slightly differently.
--
-- Deliberate modeling choice, refined during implementation from the
-- architecture doc's initial wording: demand is measured as
-- ordered_quantity, NOT allocated_quantity. allocated_quantity is
-- capped by what inventory was actually available to fulfill — using
-- it as the demand signal would make a stockout period look like a
-- demand *drop* instead of a supply constraint, teaching every
-- downstream model exactly the wrong lesson (under-forecast, under-
-- stock, stay stocked out). ordered_quantity is what the customer
-- actually wanted, independent of whether the warehouse could fill it
-- — the correct definition of "demand" for forecasting purposes.
--
-- fulfillment_warehouse_key is nullable in fact_orders (a line not yet
-- assigned to a fulfillment warehouse) — excluded from the
-- sku_warehouse grain view (a NULL warehouse isn't a real forecasting
-- series) but naturally included in the category/region rollups, which
-- don't key off it.

CREATE VIEW v_daily_demand AS
SELECT
    fo.product_key,
    fo.fulfillment_warehouse_key AS warehouse_key,
    fo.order_date_key,
    dd.full_date,
    dd.day_of_week,
    dd.is_weekend,
    dd.month_number,
    SUM(fo.ordered_quantity) AS demand_quantity
FROM fact_orders fo
JOIN dim_date dd ON dd.date_key = fo.order_date_key
WHERE fo.fulfillment_warehouse_key IS NOT NULL
GROUP BY fo.product_key, fo.fulfillment_warehouse_key, fo.order_date_key,
         dd.full_date, dd.day_of_week, dd.is_weekend, dd.month_number;

CREATE VIEW v_daily_demand_by_category AS
SELECT
    dp.category,
    fo.order_date_key,
    dd.full_date,
    dd.day_of_week,
    dd.is_weekend,
    dd.month_number,
    SUM(fo.ordered_quantity) AS demand_quantity
FROM fact_orders fo
JOIN dim_product dp ON dp.product_key = fo.product_key
JOIN dim_date dd ON dd.date_key = fo.order_date_key
WHERE dp.category IS NOT NULL
GROUP BY dp.category, fo.order_date_key, dd.full_date, dd.day_of_week, dd.is_weekend, dd.month_number;

CREATE VIEW v_daily_demand_by_region AS
SELECT
    dc.region_key,
    fo.order_date_key,
    dd.full_date,
    dd.day_of_week,
    dd.is_weekend,
    dd.month_number,
    SUM(fo.ordered_quantity) AS demand_quantity
FROM fact_orders fo
JOIN dim_customer dc ON dc.customer_key = fo.customer_key
JOIN dim_date dd ON dd.date_key = fo.order_date_key
GROUP BY dc.region_key, fo.order_date_key, dd.full_date, dd.day_of_week, dd.is_weekend, dd.month_number;

-- v_lead_time_stats / v_supplier_performance_trend (docs/phase7-architecture.md
-- §4) are Module C's feature views, not Module A's — deliberately not
-- created here; added when Module C is authorized, per the incremental
-- scope your Phase 7A approval set.
