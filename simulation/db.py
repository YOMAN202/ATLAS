"""Database session management for the Simulation Engine.

Backend's app.core.config is the single source of truth for connection
settings (Decision 1: simulation depends on backend as a local editable
package rather than duplicating configuration). Backend itself has no
session-management utility yet — that's a Phase 6 concern for
request-scoped API sessions — so this module owns it for simulation runs.

One session per run. By default, this context manager commits once at
the end if the whole run succeeds, rolling back entirely on any
exception — the atomicity contract the Phase 2 Domain Services rely on
(they validate before mutating and never call commit() themselves; the
caller's transaction is the unit of work).

For long standalone runs, `engine.run()`'s optional `commit_every_n_days`
lets the caller (not the Domain Services, and not this module) commit
periodically instead of holding one multi-day transaction open — a single
multi-hour transaction was found to degrade in throughput as it grew
(more InnoDB undo log, more SQLAlchemy identity-map bookkeeping per
operation). This session_scope() commit remains the final safety net
regardless: it will commit only if run() has not already committed.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_session_factory(database_url: str | None = None) -> sessionmaker:
    engine = create_engine(database_url or settings.database_url_oltp)
    return sessionmaker(bind=engine)


@contextmanager
def session_scope(session_factory: sessionmaker | None = None) -> Iterator[Session]:
    factory = session_factory or make_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
