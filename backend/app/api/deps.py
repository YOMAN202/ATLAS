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

from cachetools import TTLCache
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.core.config import settings

_engine: Engine | None = None

# get_current_etl_run_id() runs on every dashboard request, including
# cache hits (app/api/cache.py's cache key needs it before the lookup
# even happens) -- without this, every "cached" response still paid for
# a DB round trip just to compute its own cache key. A 5s TTL bounds
# staleness to "at most 5 seconds behind the newest completed ETL run"
# (never a partial/in-progress run -- the WHERE status = 'SUCCEEDED'
# clause is unchanged), which is safe here because ETL runs complete on
# the order of minutes, not seconds (docs/ATLAS-v1.0-final-report.md
# §15) -- a request landing in that 5s window would key its cache
# lookup off the previous run's id rather than update it in real time
# either way, per the fixed-per-run refresh model above.
_etl_run_id_cache: TTLCache = TTLCache(maxsize=1, ttl=5)
_ETL_RUN_ID_CACHE_KEY = "current"


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

    cached = _etl_run_id_cache.get(_ETL_RUN_ID_CACHE_KEY)
    if cached is not None:
        return cached

    row = conn.execute(
        text("SELECT id FROM etl_run_log WHERE status = 'SUCCEEDED' ORDER BY id DESC LIMIT 1")
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=503, detail="No successful ETL run found yet.")
    _etl_run_id_cache[_ETL_RUN_ID_CACHE_KEY] = row[0]
    return row[0]
