"""Fact loading: bulk upsert transformed rows into a fact table, keyed
on its grain (the same `UNIQUE` constraint that enforces the grain
statement in each fact's DDL — loading and grain enforcement share one
mechanism, not two). Same bulk-fetch-then-compare-then-write shape as
etl/load/dimensions.py's Type 1 loader; the actual write goes through
the same true multi-row bulk_upsert() both loaders share.
"""

from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.load.bulk import bulk_upsert


class LoadCounts(NamedTuple):
    inserted: int
    updated: int
    unchanged: int


def upsert_fact(
    olap_conn: Connection, table: str, grain_columns: tuple[str, ...], rows: list[dict]
) -> LoadCounts:
    if not rows:
        return LoadCounts(0, 0, 0)

    existing = {
        tuple(row[c] for c in grain_columns): dict(row)
        for row in olap_conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
    }

    inserted = updated = unchanged = 0
    to_write: list[dict] = []
    for row in rows:
        grain_key = tuple(row[c] for c in grain_columns)
        current = existing.get(grain_key)
        if current is None:
            inserted += 1
            to_write.append(row)
        elif any(current.get(col) != value for col, value in row.items()):
            updated += 1
            to_write.append(row)
        else:
            unchanged += 1

    bulk_upsert(olap_conn, table, to_write)
    return LoadCounts(inserted, updated, unchanged)
