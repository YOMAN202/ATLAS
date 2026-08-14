"""Test session/schema fixtures for the Simulation Engine — same pattern
as backend/tests/conftest.py (migrations applied once per session via the
real Alembic chain, one test = one rolled-back transaction), pointed at
the same atlas_oltp_test schema, since simulation and backend share one
OLTP schema (Decision 1: single source of truth).
"""

import os
import subprocess
from pathlib import Path

import pytest
from app.seed.reference_data import seed_reference_data
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

_CONTAINER_BACKEND_DIR = Path("/backend")
BACKEND_DIR = (
    _CONTAINER_BACKEND_DIR
    if _CONTAINER_BACKEND_DIR.is_dir()
    else Path(__file__).resolve().parent.parent.parent / "backend"
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL_OLTP",
    "mysql+pymysql://root:changeme_root@mysql:3306/atlas_oltp_test",
)


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
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


@pytest.fixture
def seeded_lookups(db_session):
    """Simulation's world_init assumes backend's reference lookups
    (statuses, regions, vehicle types) already exist — same idempotent
    seed function backend/tests/conftest.py's `lookups` fixture uses."""

    seed_reference_data(db_session)
    return db_session
