"""Bulk FK-target lookups for DQ-3, one query per referenced table per
batch (not one query per row per FK) — the same bulk-fetch-then-compare
shape already proven in Phase 3's domain services and Phase 5's SCD2
design.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.extract.registry import TableSpec


def fetch_valid_ids(oltp_conn: Connection, spec: TableSpec) -> dict[str, set]:
    """Returns {referenced_table: {valid ids}} for every table spec's
    foreign_keys reference — table/column names come only from the
    hardcoded REGISTRY, never external input (safe to interpolate; see
    etl/extract/extract.py's identical note).
    """

    valid_ids_by_table: dict[str, set] = {}
    for fk in spec.foreign_keys:
        if fk.referenced_table in valid_ids_by_table:
            continue
        rows = oltp_conn.execute(
            text(f"SELECT {fk.referenced_column} FROM {fk.referenced_table}")
        ).all()
        valid_ids_by_table[fk.referenced_table] = {row[0] for row in rows}
    return valid_ids_by_table
