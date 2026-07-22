-- ADR-001 (docs/ATLAS-TDD.md §14): one MySQL 8 instance, two logically
-- separate schemas — atlas_oltp (3NF operational) and atlas_olap
-- (Kimball star-schema warehouse). No tables are created here; schema
-- objects are owned by Alembic (OLTP, Phase 1) and the ETL warehouse
-- DDL (OLAP, Phase 4).
CREATE DATABASE IF NOT EXISTS atlas_oltp CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS atlas_olap CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

-- Phase 1 test suite runs real Alembic migrations against a dedicated
-- schema (never atlas_oltp itself), so constraint tests can freely
-- create/rollback data without touching dev data.
CREATE DATABASE IF NOT EXISTS atlas_oltp_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
