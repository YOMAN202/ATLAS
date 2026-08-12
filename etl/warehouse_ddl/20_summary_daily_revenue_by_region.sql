-- summary_daily_revenue_by_region (TDD §10/§15)
--
-- The one summary table TDD §10 names by example ("e.g. daily revenue
-- by region"). Physical table, not a view (ADR confirmed in TDD §15:
-- "Pre-aggregated summary tables: Confirmed as physical tables refreshed
-- during ETL"). Empty shell here — Phase 5's ETL Load stage populates it
-- from fact_orders joined through dim_customer -> dim_region.
--
-- This is the ENTIRE summary-table deliverable for Phase 4. No other
-- aggregate/summary tables are created here, inferred from the KPI
-- table, or added speculatively — symmetric with TDD §4.3's own explicit
-- deferral of covering indexes until real dashboard query patterns are
-- known (Phase 7). Additional summary tables are out of scope for this
-- phase.
--
-- Grain: one row per (region, date) — no separate surrogate key needed
-- for a summary table; the natural grain is the primary key.

CREATE TABLE summary_daily_revenue_by_region (
    region_key           INT           NOT NULL,
    date_key              INT           NOT NULL,
    total_orders           INT           NOT NULL,
    total_order_lines      INT           NOT NULL,
    total_revenue           DECIMAL(12,2) NOT NULL,
    total_gross_margin      DECIMAL(12,2) NOT NULL,
    CONSTRAINT pk_summary_daily_revenue_by_region PRIMARY KEY (region_key, date_key),
    CONSTRAINT fk_summary_daily_revenue_by_region_region_key_dim_region
        FOREIGN KEY (region_key) REFERENCES dim_region (region_key),
    CONSTRAINT fk_summary_daily_revenue_by_region_date_key_dim_date
        FOREIGN KEY (date_key) REFERENCES dim_date (date_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
