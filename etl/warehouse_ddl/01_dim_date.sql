-- dim_date (TDD §4.2, conformed dimension; ADR-011 surrogate-key convention)
--
-- Type 1 (not SCD2 — a date's attributes are immutable by definition).
-- Grain: one row per calendar day.
--
-- No OLTP source table exists for this dimension (there is no "dates"
-- table to extract from) — it is generated calendar arithmetic, not a
-- data load, so unlike every other table in this directory it is both
-- created AND populated here rather than left empty for Phase 5 (see
-- etl/warehouse_ddl/README.md's "Scope boundary" section).
--
-- Range: 2021-01-01 through 2022-01-31 — covers every date-bearing OLTP
-- column's actual min/max in the validated 365-day Phase 3 dataset
-- (docs/phase3-validation.md), including purchase_orders.expected_delivery_date,
-- which trails as late as 2022-01-21 due to supplier lead times on
-- late-December orders. Not an arbitrary/open-ended calendar — sized to
-- what the real data needs.

CREATE TABLE dim_date (
    date_key        INT          NOT NULL,  -- YYYYMMDD, e.g. 20210615
    full_date       DATE         NOT NULL,
    day_of_week     TINYINT      NOT NULL,  -- 1=Sunday .. 7=Saturday (MySQL DAYOFWEEK convention)
    day_name        VARCHAR(10)  NOT NULL,
    day_of_month    TINYINT      NOT NULL,
    day_of_year     SMALLINT     NOT NULL,
    week_of_year    TINYINT      NOT NULL,
    month_number    TINYINT      NOT NULL,
    month_name      VARCHAR(10)  NOT NULL,
    quarter         TINYINT      NOT NULL,
    year            SMALLINT     NOT NULL,
    is_weekend      TINYINT(1)   NOT NULL,
    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_full_date UNIQUE (full_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Recursive CTE generation (MySQL 8+, per ADR-010's own stated rationale
-- for choosing MySQL 8 — recursive CTEs were named as a demonstrated
-- feature). No external numbers table needed.
INSERT INTO dim_date (
    date_key, full_date, day_of_week, day_name, day_of_month, day_of_year,
    week_of_year, month_number, month_name, quarter, year, is_weekend
)
WITH RECURSIVE calendar AS (
    SELECT DATE('2021-01-01') AS d
    UNION ALL
    SELECT d + INTERVAL 1 DAY FROM calendar WHERE d < '2022-01-31'
)
SELECT
    CAST(DATE_FORMAT(d, '%Y%m%d') AS UNSIGNED),
    d,
    DAYOFWEEK(d),
    DATE_FORMAT(d, '%W'),
    DAYOFMONTH(d),
    DAYOFYEAR(d),
    WEEK(d, 3),
    MONTH(d),
    DATE_FORMAT(d, '%M'),
    QUARTER(d),
    YEAR(d),
    IF(DAYOFWEEK(d) IN (1, 7), 1, 0)
FROM calendar;
