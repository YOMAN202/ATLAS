"""etl_run_log writer (TDD §6 stage 5 "Audit & Score"; DQ-6)."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def start_run(conn: Connection, stage: str) -> int:
    """Inserts a RUNNING row and returns its id — every other write in
    this run (staging, quarantine, metrics) references this id."""

    result = conn.execute(
        text(
            "INSERT INTO etl_run_log (started_at, status, stage) "
            "VALUES (NOW(), 'RUNNING', :stage)"
        ),
        {"stage": stage},
    )
    return result.lastrowid


def complete_run(conn: Connection, etl_run_id: int, status: str, duration_seconds: float) -> None:
    conn.execute(
        text(
            "UPDATE etl_run_log "
            "SET status = :status, completed_at = NOW(), duration_seconds = :duration "
            "WHERE id = :run_id"
        ),
        {"status": status, "duration": duration_seconds, "run_id": etl_run_id},
    )
