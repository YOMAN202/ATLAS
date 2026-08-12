"""dq_quarantine writer (BR-6, DQ-6).

Upserted on (source_table, source_id, rule_violated) — re-validating the
same row against the same rule on a rerun overwrites the existing entry
rather than duplicating it (idempotent, per the Stage A completion gate's
"quarantine behavior is verified... idempotent re-validation doesn't
duplicate entries").
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


def quarantine_row(
    olap_conn: Connection,
    etl_run_id: int,
    source_table: str,
    source_id: int | None,
    rule_violated: str,
    rule_detail: str,
    raw_data: RowMapping | None,
    quarantined_at: datetime,
) -> None:
    payload = json.dumps(dict(raw_data), default=_json_default) if raw_data is not None else None
    olap_conn.execute(
        text(
            "INSERT INTO dq_quarantine "
            "(etl_run_id, source_table, source_id, rule_violated, rule_detail, raw_data, "
            " quarantined_at) "
            "VALUES (:run_id, :t, :sid, :rule, :detail, :raw, :qat) "
            "ON DUPLICATE KEY UPDATE "
            "etl_run_id = :run_id, rule_detail = :detail, raw_data = :raw, quarantined_at = :qat"
        ),
        {
            "run_id": etl_run_id,
            "t": source_table,
            "sid": source_id,
            "rule": rule_violated,
            "detail": rule_detail,
            "raw": payload,
            "qat": quarantined_at,
        },
    )
