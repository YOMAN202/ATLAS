import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models import Customer, Product, Region, Supplier, Warehouse, WarehouseZone

BACKEND_DIR = Path(__file__).resolve().parent.parent

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL_OLTP",
    "mysql+pymysql://root:changeme_root@mysql:3306/atlas_oltp_test",
)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Build the schema once per test session via the real Alembic
    migration chain (not Base.metadata.create_all) — this is what
    actually proves "migrations apply cleanly", per the Phase 1
    Definition of Done, rather than just proving the models are valid."""

    env = os.environ.copy()
    env["DATABASE_URL_OLTP"] = TEST_DATABASE_URL
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=BACKEND_DIR, env=env)
    yield
    subprocess.run(["alembic", "downgrade", "base"], check=True, cwd=BACKEND_DIR, env=env)


@pytest.fixture(scope="session")
def engine(apply_migrations):
    eng = create_engine(TEST_DATABASE_URL)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """One test = one transaction, rolled back afterward, so constraint
    tests (including ones that deliberately trigger a violation) never
    leak state into the next test.

    Uses the SQLAlchemy-recommended SAVEPOINT pattern rather than a plain
    outer transaction: a test that triggers a constraint violation causes
    the ORM to end its own inner transaction, which would otherwise
    deassociate the outer transaction from the connection before our
    teardown rollback runs.
    """

    connection = engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(session, transaction):
        if transaction.nested and not transaction._parent.nested:
            session.begin_nested()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


# Shared master-data fixtures, used across constraint tests (tests/) and
# domain-service tests (tests/domains/) alike — defined once here rather
# than duplicated per test module.


@pytest.fixture
def region(db_session):
    region = Region(code="TEST", name="Test Region")
    db_session.add(region)
    db_session.flush()
    return region


@pytest.fixture
def warehouse(db_session, region):
    warehouse = Warehouse(
        warehouse_code="WH-TEST",
        name="Test Warehouse",
        region_id=region.id,
        total_capacity_units=10000,
    )
    db_session.add(warehouse)
    db_session.flush()
    return warehouse


@pytest.fixture
def warehouse_zone(db_session, warehouse):
    zone = WarehouseZone(
        warehouse_id=warehouse.id,
        zone_code="A1",
        name="Zone A1",
        zone_capacity_units=1000,
    )
    db_session.add(zone)
    db_session.flush()
    return zone


@pytest.fixture
def product(db_session):
    product = Product(
        sku="SKU-TEST",
        name="Test Product",
        unit_cost=Decimal("10.00"),
        unit_price=Decimal("19.99"),
    )
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def supplier(db_session):
    supplier = Supplier(supplier_code="SUP-TEST", name="Test Supplier", default_lead_time_days=7)
    db_session.add(supplier)
    db_session.flush()
    return supplier


@pytest.fixture
def customer(db_session, region):
    customer = Customer(customer_code="CUST-TEST", name="Test Customer", region_id=region.id)
    db_session.add(customer)
    db_session.flush()
    return customer


@pytest.fixture
def lookups(db_session):
    """Seed every constrained-enumeration lookup table (status codes,
    reason/disposition codes, transaction types, vehicle types) that
    Domain Services resolve by business code. Domain-service tests depend
    on this fixture explicitly rather than it being autouse, so plain
    constraint tests don't pay for lookup rows they don't need."""

    from app.seed.reference_data import seed_reference_data

    seed_reference_data(db_session)
    return db_session
