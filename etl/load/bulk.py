"""Shared bulk-upsert primitive for both dimension and fact loading: one
`INSERT ... VALUES (...), (...), ... ON DUPLICATE KEY UPDATE` statement
per chunk (true multi-row SQL, not N single-row round trips) — the same
lesson already proven in Phase 3's bulk domain services and explicitly
cited in this module's callers' docstrings, now actually implemented
that way rather than only chunked-but-still-row-by-row.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

_CHUNK_SIZE = 5000


def bulk_upsert(olap_conn: Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    update_clause = ", ".join(f"{c} = VALUES({c})" for c in columns)

    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        values_clause = ", ".join(
            "(" + ", ".join(f":r{row_idx}_{c}" for c in columns) + ")"
            for row_idx in range(len(chunk))
        )
        params = {
            f"r{row_idx}_{c}": row[c] for row_idx, row in enumerate(chunk) for c in columns
        }
        stmt = text(
            f"INSERT INTO {table} ({col_list}) VALUES {values_clause} "
            f"ON DUPLICATE KEY UPDATE {update_clause}"
        )
        olap_conn.execute(stmt, params)
