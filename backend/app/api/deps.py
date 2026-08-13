"""Shared FastAPI dependencies for the dashboard API: a read-only OLAP
connection (via the atlas_reporting role — see
backend/app/core/config.py's dashboard_db_url, SEC-3) and the current
ETL run id, which every cached dashboard query keys off (§3 of
docs/phase6-dashboard-proposal.md: dashboards refresh once per ETL
cycle, not per request).

No SQLAlchemy ORM models exist for the OLAP warehouse (it's raw DDL in
etl/warehouse_ddl/, no Alembic chain — see that directory's README) —
every dashboard query in backend/app/api/v1/ uses SQLAlchemy Core
(`text()`), not the ORM, deliberately consistent with how the ETL
pipeline itself reads/writes the warehouse.
"""

from collections.abc import Generator

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import settings

_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.dashboard_db_url, pool_pre_ping=True)
    return _engine


def get_olap_connection() -> Generator[Connection, None, None]:
    with _get_engine().connect() as conn:
        yield conn


def get_current_etl_run_id(conn: Connection) -> int:
    """The most recent SUCCEEDED run — every dashboard's cache key and
    every "as of" framing in a response refers to this run, never to
    "now" (this is a batch-analytics system over data that only changes
    once per ETL run, per ATLAS-TDD.md §8)."""

    row = conn.execute(
        text("SELECT id FROM etl_run_log WHERE status = 'SUCCEEDED' ORDER BY id DESC LIMIT 1")
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=503, detail="No successful ETL run found yet.")
    return row[0]
