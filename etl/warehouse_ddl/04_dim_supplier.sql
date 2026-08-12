-- dim_supplier (TDD §4.2, conformed dimension; ADR-011 surrogate-key
-- convention; ADR-012 SCD2 column convention)
--
-- SCD Type 2 (TDD §4.2, ADR-006: "contract terms and lead times change
-- over time and history matters for supplier performance trend
-- analysis"). Tracked/version-triggering attributes are payment_terms_days
-- and default_lead_time_days — the exact two the TDD's own justification
-- names.
--
-- Grain: one row per supplier PER VERSION (i.e. per period during which
-- its tracked attributes held a given value) — not one row per supplier.
-- supplier_id therefore intentionally repeats across rows; it is NOT
-- unique here (only (supplier_id, effective_from) is).
--
-- MySQL 8 limitation, documented rather than silently assumed away
-- (ADR-012): there is no partial/filtered unique index, so "exactly one
-- is_current = 1 row per supplier_id" cannot be enforced at the DB level
-- — it is an ETL-load invariant (Phase 5), not a constraint here.
--
-- Source: atlas_oltp.suppliers — see docs/data-dictionary.md.

CREATE TABLE dim_supplier (
    supplier_key            INT           NOT NULL AUTO_INCREMENT,
    supplier_id             INT           NOT NULL,  -- OLTP suppliers.id; repeats across versions
    supplier_code           VARCHAR(30)   NOT NULL,
    supplier_name           VARCHAR(150)  NOT NULL,
    contact_email           VARCHAR(150)  NULL,
    contact_phone           VARCHAR(30)   NULL,
    address_line1           VARCHAR(200)  NULL,
    city                    VARCHAR(100)  NULL,
    state_province          VARCHAR(100)  NULL,
    postal_code             VARCHAR(20)   NULL,
    country                 VARCHAR(100)  NULL,
    payment_terms_days      INT           NOT NULL,  -- tracked attribute (TDD §4.2)
    default_lead_time_days  INT           NOT NULL,  -- tracked attribute (TDD §4.2)
    is_active               TINYINT(1)    NOT NULL,
    effective_from          DATE          NOT NULL,
    effective_to            DATE          NULL,
    is_current               TINYINT(1)    NOT NULL,
    source_updated_at       DATETIME      NOT NULL,
    CONSTRAINT pk_dim_supplier PRIMARY KEY (supplier_key),
    CONSTRAINT uq_dim_supplier_supplier_id_effective_from
        UNIQUE (supplier_id, effective_from),
    KEY ix_dim_supplier_supplier_id (supplier_id),
    KEY ix_dim_supplier_is_current (is_current)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
