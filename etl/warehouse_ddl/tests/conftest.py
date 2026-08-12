"""Test harness for etl/warehouse_ddl/.

Applies the DDL once per test session against a dedicated atlas_olap_test
schema (mirrors backend/tests/conftest.py's apply_migrations pattern,
minus Alembic — this schema has no ORM/migration chain; see
apply_ddl.py's docstring for why). Each test then gets a SAVEPOINT-
isolated connection so synthetic rows never leak between tests — the
same SQLAlchemy-recommended pattern backend/tests/conftest.py uses for
its db_session fixture, adapted to SQLAlchemy Core (no ORM models exist
for OLAP by design — see the Phase 4 plan).
"""

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apply_ddl import apply_all  # noqa: E402
from teardown_ddl import teardown_all  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL_OLAP",
    "mysql+pymysql://root:changeme_root@mysql:3306/atlas_olap_test",
)
os.environ["TEST_DATABASE_URL_OLAP"] = TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def apply_warehouse_ddl():
    teardown_all(TEST_DATABASE_URL)  # clean slate in case a previous run left objects behind
    apply_all(TEST_DATABASE_URL)
    yield
    teardown_all(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def engine(apply_warehouse_ddl):
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db_conn(engine):
    """One test = one transaction, rolled back afterward — see
    backend/tests/conftest.py's db_session fixture for the same pattern
    against the ORM; this is the Core equivalent."""

    connection = engine.connect()
    outer_transaction = connection.begin()
    yield connection
    outer_transaction.rollback()
    connection.close()


# Shared synthetic master-data fixtures — one row per dimension, reused
# across test_fk_resolution.py and test_grain_uniqueness.py so both don't
# each hand-roll the same dim inserts.


@pytest.fixture
def region_key(db_conn):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_region (region_id, region_code, region_name, source_updated_at) "
            "VALUES (9001, 'TEST', 'Test Region', NOW())"
        )
    )
    return result.lastrowid


@pytest.fixture
def product_key(db_conn):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_product "
            "(product_id, sku, product_name, unit_of_measure, current_unit_cost, "
            " current_unit_price, is_active, source_updated_at) "
            "VALUES (9001, 'SKU-TEST', 'Test Product', 'EA', 10.00, 19.99, 1, NOW())"
        )
    )
    return result.lastrowid


@pytest.fixture
def warehouse_key(db_conn, region_key):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_warehouse "
            "(warehouse_id, warehouse_code, warehouse_name, region_key, total_capacity_units, "
            " is_active, effective_from, effective_to, is_current, source_updated_at) "
            "VALUES (9001, 'WH-TEST', 'Test Warehouse', :region_key, 10000, "
            " 1, '2021-01-01', NULL, 1, NOW())"
        ),
        {"region_key": region_key},
    )
    return result.lastrowid


@pytest.fixture
def supplier_key(db_conn):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_supplier "
            "(supplier_id, supplier_code, supplier_name, payment_terms_days, "
            " default_lead_time_days, is_active, effective_from, effective_to, is_current, "
            " source_updated_at) "
            "VALUES (9001, 'SUP-TEST', 'Test Supplier', 30, 7, 1, '2021-01-01', NULL, 1, NOW())"
        )
    )
    return result.lastrowid


@pytest.fixture
def carrier_key(db_conn):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_carrier "
            "(carrier_id, carrier_code, carrier_name, vehicle_type_code, vehicle_type_name, "
            " vehicle_capacity_units, vehicle_cost_per_mile, is_active, source_updated_at) "
            "VALUES (9001, 'CAR-TEST', 'Test Carrier', 'VAN', 'Van', 500, 1.25, 1, NOW())"
        )
    )
    return result.lastrowid


@pytest.fixture
def customer_key(db_conn, region_key):
    result = db_conn.execute(
        text(
            "INSERT INTO dim_customer "
            "(customer_id, customer_code, customer_name, region_key, source_updated_at) "
            "VALUES (9001, 'CUST-TEST', 'Test Customer', :region_key, NOW())"
        ),
        {"region_key": region_key},
    )
    return result.lastrowid


@pytest.fixture
def date_key_a(db_conn):
    """A real date_key already populated by 01_dim_date.sql — dim_date is
    generated, not inserted synthetically like the other dims."""
    return 20210601


@pytest.fixture
def date_key_b(db_conn):
    return 20210602
