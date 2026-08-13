"""The decision-support module's one and only database connection —
via the atlas_decision_support role (docs/phase7-architecture.md §6):
read on all of atlas_olap, write only on its own ds_* tables. Same
lazy-singleton-engine pattern as backend/app/api/deps.py, deliberately
not shared code with it — that module is the dashboard API's read-only
atlas_reporting connection, a structurally different role with a
different contract, and the two must never be conflated.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from app.core.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.decision_support_db_url, pool_pre_ping=True)
    return _engine


def get_connection() -> Generator[Connection, None, None]:
    with get_engine().connect() as conn:
        yield conn
