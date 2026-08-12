"""etl_extract_staging writer (ADR-015, ADR-017).

Accepted (validated) rows are upserted here, keyed on
(source_table, source_id) — re-staging the same row (e.g. on a rerun
after a partial-batch failure) overwrites in place rather than
duplicating, which is what makes this durable-before-watermark-advances
design idempotent (ADR-017).
"""

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.row import RowMapping


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Cannot JSON-serialize {type(value)}")


def stage_row(
    olap_conn: Connection,
    etl_run_id: int,
    source_table: str,
    source_id: int,
    row: RowMapping,
    extracted_at: datetime,
) -> None:
    payload = json.dumps(dict(row), default=_json_default)
    olap_conn.execute(
        text(
            "INSERT INTO etl_extract_staging "
            "(etl_run_id, source_table, source_id, payload, extracted_at) "
            "VALUES (:run_id, :t, :sid, :payload, :extracted_at) "
            "ON DUPLICATE KEY UPDATE "
            "etl_run_id = :run_id, payload = :payload, extracted_at = :extracted_at"
        ),
        {
            "run_id": etl_run_id,
            "t": source_table,
            "sid": source_id,
            "payload": payload,
            "extracted_at": extracted_at,
        },
    )
