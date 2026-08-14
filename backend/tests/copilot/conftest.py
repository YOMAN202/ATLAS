"""Test harness for the copilot tool layer. Applies the real warehouse
DDL to atlas_olap_test and exposes the app's real FastAPI TestClient --
the exact same fixture shape tests/api/conftest.py uses, duplicated
here rather than shared across sibling test directories (the same
per-module-independence tradeoff already accepted for the run_module_*
orchestration scripts, docs/final-architecture-review.md §2's
maintainability note).
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[2]
WAREHOUSE_DDL_DIR = BACKEND_DIR.parent / "etl" / "warehouse_ddl"
sys.path.insert(0, str(WAREHOUSE_DDL_DIR))

from apply_ddl import apply_all  # noqa: E402
from teardown_ddl import teardown_all  # noqa: E402

TEST_DATABASE_URL_OLAP = os.environ.get(
    "TEST_DATABASE_URL_OLAP", "mysql+pymysql://root:changeme_root@mysql:3306/atlas_olap_test"
)
os.environ["TEST_DATABASE_URL_OLAP"] = TEST_DATABASE_URL_OLAP

_TABLES_TO_RESET = [
    "ds_optimization_recommendation",
    "ds_scenario_result",
    "ds_scenario",
    "ds_policy_sensitivity",
    "ds_inventory_policy",
    "ds_calibration_bucket",
    "ds_service_level_prediction",
    "ds_supplier_risk_score",
    "ds_demand_forecast",
    "ds_experiment_run",
    "ds_model_registry",
    "etl_run_table_metrics",
    "dq_quarantine",
    "etl_extract_staging",
    "etl_watermark",
    "etl_run_log",
    "summary_daily_revenue_by_region",
    "fact_inventory_snapshot",
    "fact_returns",
    "fact_supplier_delivery",
    "fact_procurement",
    "fact_shipments",
    "fact_orders",
    "dim_warehouse",
    "dim_supplier",
    "dim_customer",
    "dim_carrier",
    "dim_product",
    "dim_region",
]


@pytest.fixture(scope="session", autouse=True)
def _apply_schema():
    teardown_all(TEST_DATABASE_URL_OLAP)
    apply_all(TEST_DATABASE_URL_OLAP)
    yield
    teardown_all(TEST_DATABASE_URL_OLAP)


@pytest.fixture(scope="session")
def olap_engine(_apply_schema):
    eng = create_engine(TEST_DATABASE_URL_OLAP)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _reset_between_tests(olap_engine):
    def _truncate():
        with olap_engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                for table in _TABLES_TO_RESET:
                    conn.execute(text(f"TRUNCATE TABLE {table}"))
                conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    _truncate()
    yield
    _truncate()


@pytest.fixture
def client(olap_engine):
    from app.api.cache import _cache
    from app.api.deps import get_olap_connection
    from app.main import app

    def _override_get_olap_connection():
        with olap_engine.connect() as conn:
            yield conn

    app.dependency_overrides[get_olap_connection] = _override_get_olap_connection
    _cache.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_run(olap_engine):
    with olap_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO etl_run_log (started_at, completed_at, status, stage) "
                    "VALUES (NOW(), NOW(), 'SUCCEEDED', 'STAGE_A_B')"
                )
            )
            return result.lastrowid
