-- SEC-3 (ATLAS-SRS.md): three distinct MySQL roles, least-privilege per
-- schema. Only atlas_reporting is actually wired into application code
-- as of Phase 6 (backend/app/core/config.py's dashboard_db_url) — the
-- dashboard API's one and only DB connection, deliberately unable to
-- write anything, in either schema. atlas_app/atlas_etl are created here
-- for SEC-3 completeness (the roles the frozen spec names) but the
-- application/ETL connection strings still use the root credentials
-- they were already using before this phase; migrating those is a
-- separate, out-of-scope change, not silently done as a side effect of
-- adding the reporting role dashboards actually need.
--
-- Passwords are placeholder dev values (SEC-4: real deployments must
-- override via environment, never rely on these), consistent with
-- MYSQL_ROOT_PASSWORD's own placeholder in this same init flow.

CREATE USER IF NOT EXISTS 'atlas_app'@'%' IDENTIFIED BY 'changeme_app';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_oltp.* TO 'atlas_app'@'%';

CREATE USER IF NOT EXISTS 'atlas_etl'@'%' IDENTIFIED BY 'changeme_etl';
GRANT SELECT ON atlas_oltp.* TO 'atlas_etl'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.* TO 'atlas_etl'@'%';

-- The dashboard API's only role: read-only on atlas_olap, nothing else.
-- Structurally cannot write to either schema, and cannot even read
-- atlas_oltp — a dashboard endpoint has no legitimate reason to.
CREATE USER IF NOT EXISTS 'atlas_reporting'@'%' IDENTIFIED BY 'changeme_reporting';
GRANT SELECT ON atlas_olap.* TO 'atlas_reporting'@'%';

FLUSH PRIVILEGES;
