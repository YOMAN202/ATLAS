"""Test harness for the Stage A ETL pipeline.

Unlike Phase 4's warehouse_ddl tests (SAVEPOINT-per-test, since those
tests write directly and roll back), etl.pipeline.run() manages its own
real per-table commits — that's the actual behavior under test (watermark
persistence across separate "runs"). So isolation here is TRUNCATE-based:
every test starts from a fully reset OLTP test schema (real backend
tables, via Alembic) and a fully reset OLAP test schema (warehouse +
ETL-process tables, via etl/warehouse_ddl), reseeded with minimal master
data each time.
"""

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "warehouse_ddl"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.models import Customer, Product, Region, Supplier, Warehouse, WarehouseZone  # noqa: E402
from app.seed.reference_data import seed_reference_data  # noqa: E402
from apply_ddl import apply_all  # noqa: E402
from teardown_ddl import teardown_all  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

TEST_DATABASE_URL_OLTP = os.environ.get(
    "TEST_DATABASE_URL_OLTP", "mysql+pymysql://root:changeme_root@mysql:3306/atlas_oltp_test"
)
TEST_DATABASE_URL_OLAP = os.environ.get(
    "TEST_DATABASE_URL_OLAP", "mysql+pymysql://root:changeme_root@mysql:3306/atlas_olap_test"
)
os.environ["TEST_DATABASE_URL_OLTP"] = TEST_DATABASE_URL_OLTP
os.environ["TEST_DATABASE_URL_OLAP"] = TEST_DATABASE_URL_OLAP

# OLTP tables truncated (and reseeded) between tests, in FK-safe order.
_OLTP_TABLES_TRUNCATE_ORDER = [
    "return_lines",
    "returns",
    "shipment_events",
    "shipments",
    "order_lines",
    "orders",
    "purchase_order_lines",
    "purchase_orders",
    "inventory_transactions",
    "inventory_positions",
    "customers",
    "suppliers",
    "products",
    "warehouse_zones",
    "warehouses",
    "carriers",
    "regions",
]

_OLAP_ETL_TABLES_TRUNCATE_ORDER = [
    "etl_run_table_metrics",
    "dq_quarantine",
    "etl_extract_staging",
    "etl_watermark",
    "etl_run_log",
]

# Stage B warehouse tables (dim_date excluded — generated once, never
# written by ETL). FK order doesn't actually matter here since the
# truncate block below runs with FOREIGN_KEY_CHECKS=0, but facts-then-
# dims reads naturally.
_OLAP_WAREHOUSE_TABLES_TRUNCATE_ORDER = [
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
def _apply_schemas():
    env = os.environ.copy()
    env["DATABASE_URL_OLTP"] = TEST_DATABASE_URL_OLTP
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=BACKEND_DIR, env=env)

    teardown_all(TEST_DATABASE_URL_OLAP)
    apply_all(TEST_DATABASE_URL_OLAP)

    yield

    subprocess.run(["alembic", "downgrade", "base"], check=True, cwd=BACKEND_DIR, env=env)
    teardown_all(TEST_DATABASE_URL_OLAP)


@pytest.fixture
def oltp_engine(_apply_schemas):
    eng = create_engine(TEST_DATABASE_URL_OLTP)
    yield eng
    eng.dispose()


@pytest.fixture
def olap_engine(_apply_schemas):
    eng = create_engine(TEST_DATABASE_URL_OLAP)
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _reset_between_tests(oltp_engine, olap_engine):
    """Runs before AND after every test — a clean slate on entry, and
    cleanup on exit so a failed assertion mid-test doesn't leak into the
    next test either."""

    def _truncate():
        with oltp_engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                for table in _OLTP_TABLES_TRUNCATE_ORDER:
                    conn.execute(text(f"TRUNCATE TABLE {table}"))
                conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        with olap_engine.connect() as conn:
            with conn.begin():
                conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
                for table in (
                    _OLAP_ETL_TABLES_TRUNCATE_ORDER + _OLAP_WAREHOUSE_TABLES_TRUNCATE_ORDER
                ):
                    conn.execute(text(f"TRUNCATE TABLE {table}"))
                conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    _truncate()
    yield
    _truncate()


@pytest.fixture
def oltp_session(oltp_engine):
    factory = sessionmaker(bind=oltp_engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def master_data(oltp_session):
    """Minimal, real OLTP master data every extraction/validation test
    can build on: one region, one warehouse (+zone), one product, one
    supplier, one customer, and every lookup table seeded."""

    seed_reference_data(oltp_session)

    region = Region(code="TEST", name="Test Region")
    oltp_session.add(region)
    oltp_session.flush()

    warehouse = Warehouse(
        warehouse_code="WH-TEST",
        name="Test Warehouse",
        region_id=region.id,
        total_capacity_units=10000,
    )
    oltp_session.add(warehouse)
    oltp_session.flush()

    zone = WarehouseZone(
        warehouse_id=warehouse.id, zone_code="A1", name="Zone A1", zone_capacity_units=1000
    )
    oltp_session.add(zone)

    product = Product(
        sku="SKU-TEST", name="Test Product", unit_cost=Decimal("10.00"), unit_price=Decimal("19.99")
    )
    oltp_session.add(product)

    supplier = Supplier(supplier_code="SUP-TEST", name="Test Supplier", default_lead_time_days=7)
    oltp_session.add(supplier)

    customer = Customer(customer_code="CUST-TEST", name="Test Customer", region_id=region.id)
    oltp_session.add(customer)

    oltp_session.flush()
    oltp_session.commit()

    return {
        "region": region,
        "warehouse": warehouse,
        "warehouse_zone": zone,
        "product": product,
        "supplier": supplier,
        "customer": customer,
    }
