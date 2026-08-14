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
-- Its schema-wide SELECT already covers Phase 7's new ds_* tables/views
-- without any additional grant here — nothing to change for Phase 7.
CREATE USER IF NOT EXISTS 'atlas_reporting'@'%' IDENTIFIED BY 'changeme_reporting';
GRANT SELECT ON atlas_olap.* TO 'atlas_reporting'@'%';

-- Phase 7 (docs/phase7-architecture.md §6): the decision-support
-- module's only role. Reads the whole warehouse (it needs every fact/
-- dim to compute anything) but can only write the specific ds_* tables
-- it owns — enumerated per-table, since MySQL has no prefix-wildcard
-- GRANT. Never gets write access to a fact/dim table, ever; extending
-- this role to a new ds_* table means adding one more GRANT line here,
-- not widening the schema-level grant.
CREATE USER IF NOT EXISTS 'atlas_decision_support'@'%' IDENTIFIED BY 'changeme_decision_support';
GRANT SELECT ON atlas_olap.* TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_model_registry TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_experiment_run TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_demand_forecast TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_supplier_risk_score TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_service_level_prediction TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_calibration_bucket TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_inventory_policy TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_policy_sensitivity TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_scenario TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_scenario_result TO 'atlas_decision_support'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON atlas_olap.ds_optimization_recommendation TO 'atlas_decision_support'@'%';

FLUSH PRIVILEGES;
