import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

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
