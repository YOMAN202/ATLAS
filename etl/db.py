"""Database engines for the ETL pipeline.

Two engines, matching the ETL role's actual access per the Master
Prompt's communication matrix: read-only intent against atlas_oltp,
read/write against atlas_olap (ADR-015). Both default to
app.core.config.settings, same single-source-of-truth pattern
simulation/db.py already established for OLTP; test overrides
(TEST_DATABASE_URL_OLTP / TEST_DATABASE_URL_OLAP) follow the same
env-var convention already used throughout the test suites.

SQLAlchemy Core (Connection), not ORM Session — there is no ORM model
layer for either side of the ETL pipeline's own tables (OLTP is read via
raw SELECT for extraction; OLAP's ETL-process tables have no ORM models,
matching the warehouse's own no-ORM design from Phase 4).
"""

import os

from app.core.config import settings
from sqlalchemy import Engine, create_engine


def oltp_engine() -> Engine:
    url = os.environ.get("TEST_DATABASE_URL_OLTP", settings.database_url_oltp)
    return create_engine(url)


def olap_engine() -> Engine:
    url = os.environ.get("TEST_DATABASE_URL_OLAP", settings.database_url_olap)
    return create_engine(url)
