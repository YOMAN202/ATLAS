-- Supplier feature views (Phase 7 Module C, docs/phase7-module-c-completion.md)
--
-- Read-only, computed directly from fact_supplier_delivery/fact_procurement
-- — no new data, no ETL work. Unlike Module A's per-SKU demand series
-- (sparse: avg 52.7 non-zero days of 365), supplier delivery data is
-- dense (100 suppliers, avg 204.9 deliveries each across the full year,
-- confirmed directly against fact_supplier_delivery) — every metric
-- below is computed from real sample sizes, not a handful of points.

CREATE VIEW v_supplier_delivery_stats AS
SELECT
    fsd.supplier_key,
    COUNT(*) AS n_deliveries,
    AVG(CAST(fsd.is_on_time AS DECIMAL(10,4))) AS on_time_rate,
    SUM(fsd.quality_rejected_quantity) / NULLIF(SUM(fsd.received_quantity), 0) AS quality_rejection_rate,
    SUM(fsd.received_quantity) / NULLIF(SUM(fsd.ordered_quantity), 0) AS fill_rate,
    AVG(fsd.lead_time_variance_days) AS avg_lead_time_variance_days,
    STDDEV_SAMP(fsd.lead_time_variance_days) AS lead_time_stddev_days
FROM fact_supplier_delivery fsd
GROUP BY fsd.supplier_key;

-- Trend: on-time rate in the trailing 90 days vs. everything before
-- that, computed relative to the latest delivery in the data (not a
-- hardcoded calendar date) so this stays correct if the dataset's date
-- range ever changes. A supplier with too few deliveries in either
-- window (< 5) gets NULL rates rather than a rate computed from a
-- handful of points presented with false confidence.
CREATE VIEW v_supplier_trend AS
WITH bounds AS (
    SELECT DATE_SUB(MAX(dd.full_date), INTERVAL 90 DAY) AS split_date
    FROM fact_supplier_delivery fsd
    JOIN dim_date dd ON dd.date_key = fsd.delivery_date_key
),
windowed AS (
    SELECT
        fsd.supplier_key,
        CASE WHEN dd.full_date > b.split_date THEN 'recent' ELSE 'prior' END AS period,
        fsd.is_on_time
    FROM fact_supplier_delivery fsd
    JOIN dim_date dd ON dd.date_key = fsd.delivery_date_key
    CROSS JOIN bounds b
)
SELECT
    supplier_key,
    MAX(CASE WHEN period = 'recent' THEN n END) AS n_recent,
    MAX(CASE WHEN period = 'prior' THEN n END) AS n_prior,
    MAX(CASE WHEN period = 'recent' AND n >= 5 THEN on_time_rate END) AS recent_on_time_rate,
    MAX(CASE WHEN period = 'prior' AND n >= 5 THEN on_time_rate END) AS prior_on_time_rate
FROM (
    SELECT
        supplier_key,
        period,
        COUNT(*) AS n,
        AVG(CAST(is_on_time AS DECIMAL(10,4))) AS on_time_rate
    FROM windowed
    GROUP BY supplier_key, period
) per_period
GROUP BY supplier_key;

CREATE VIEW v_supplier_utilization AS
SELECT
    fp.supplier_key,
    SUM(fp.extended_cost) AS total_spend,
    SUM(fp.extended_cost) / NULLIF((SELECT SUM(extended_cost) FROM fact_procurement), 0) AS share_of_total_spend,
    COUNT(DISTINCT fp.product_key) AS distinct_products_supplied,
    COUNT(DISTINCT fp.warehouse_key) AS distinct_warehouses_served
FROM fact_procurement fp
GROUP BY fp.supplier_key;
