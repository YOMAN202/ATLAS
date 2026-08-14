"""Dimension loading: upsert transformed rows into the warehouse.

Both Type 1 and SCD2 loaders bulk-fetch existing state once per batch
and classify each candidate row as new/changed/unchanged in Python
*before* writing — the same pattern already proven for Stage A's
FK-validation lookups and Phase 3's bulk domain services — so
inserted/updated/unchanged counts are exact, not estimated from
MySQL's ambiguous multi-row `ON DUPLICATE KEY UPDATE` affected-rows
arithmetic (per the Stage A review requirement, carried into Stage B).
"""

from datetime import date
from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.load.bulk import bulk_upsert

# ADR-016 addendum: a dimension's very first version cannot use the
# source row's updated_at as effective_from. In this dataset, OLTP
# created_at/updated_at are stamped at data-generation/load wall-clock
# time (e.g. 2026-08-08), completely decoupled from the simulated
# business dates the facts carry (2021 onward) — suppliers/warehouses
# never actually change during the simulation, so every one has exactly
# one version, and dating it to "now" makes it unresolvable against any
# earlier business date. A fixed epoch sentinel, well before the
# earliest possible business date in this dataset, keeps a first
# version visible to all simulated history while staying deterministic
# across reruns (a constant, not wall-clock "now"). Only version 1 uses
# this; a genuine later change still versions off source_updated_at,
# per the original ADR-016 rule.
_SCD2_EPOCH = date(2000, 1, 1)


class LoadCounts(NamedTuple):
    inserted: int
    updated: int
    unchanged: int


def upsert_type1_dimension(
    olap_conn: Connection, table: str, natural_id_column: str, rows: list[dict]
) -> LoadCounts:
    if not rows:
        return LoadCounts(0, 0, 0)

    existing = {
        row[natural_id_column]: dict(row)
        for row in olap_conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
    }
    # existing rows also carry the surrogate key + source_updated_at
    # column from SELECT * — comparison below only inspects the columns
    # a candidate row actually specifies.

    inserted = updated = unchanged = 0
    to_write: list[dict] = []
    for row in rows:
        natural_id = row[natural_id_column]
        current = existing.get(natural_id)
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


def upsert_scd2_dimension(
    olap_conn: Connection,
    table: str,
    natural_id_column: str,
    tracked_columns: tuple[str, ...],
    candidates: list[dict],
) -> LoadCounts:
    """SCD2 load per ADR-016: new version if tracked attributes changed
    (or no current version exists), in-place update if only non-tracked
    attributes changed, same-day coalesce if a new version would land on
    the same effective_from as the version already current, no-op if
    nothing changed at all.
    """

    if not candidates:
        return LoadCounts(0, 0, 0)

    key_column = f"{table[4:]}_key"
    natural_ids = tuple(c[natural_id_column] for c in candidates)
    placeholder = ",".join(f":id{i}" for i in range(len(natural_ids)))
    params = {f"id{i}": nid for i, nid in enumerate(natural_ids)}
    current_rows = (
        olap_conn.execute(
            text(
                f"SELECT * FROM {table} WHERE {natural_id_column} IN ({placeholder}) "
                f"AND is_current = 1"
            ),
            params,
        )
        .mappings()
        .all()
    )
    current_by_natural_id = {row[natural_id_column]: dict(row) for row in current_rows}

    inserted = updated = unchanged = 0

    for candidate in candidates:
        natural_id = candidate[natural_id_column]
        current = current_by_natural_id.get(natural_id)

        if current is None:
            effective_from = _SCD2_EPOCH
            olap_conn.execute(
                text(
                    f"INSERT INTO {table} "
                    f"({', '.join(candidate.keys())}, effective_from, effective_to, is_current) "
                    f"VALUES ({', '.join(f':{c}' for c in candidate.keys())}, "
                    f":effective_from, NULL, 1)"
                ),
                {**candidate, "effective_from": effective_from},
            )
            inserted += 1
            continue

        tracked_changed = any(current.get(col) != candidate[col] for col in tracked_columns)
        non_tracked_changed = any(
            current.get(col) != candidate[col]
            for col in candidate
            if col not in tracked_columns and col != "source_updated_at"
        )

        if not tracked_changed and not non_tracked_changed:
            unchanged += 1
            continue

        if not tracked_changed:
            # Only non-tracked attributes changed — update the current
            # version in place, no new version (hybrid Type1/Type2 row).
            _update_current_row(olap_conn, table, key_column, current[key_column], candidate)
            updated += 1
            continue

        # A genuine tracked-attribute change on an existing dimension —
        # unlike version 1, this really is a business-time event, so it
        # versions off the source row's own updated_at (ADR-016).
        effective_from: date = candidate["source_updated_at"].date()

        if effective_from == current["effective_from"]:
            # Same-day coalesce (ADR-016): a second real change on the
            # same calendar day updates the current version in place
            # rather than colliding on UNIQUE(natural_id, effective_from).
            _update_current_row(olap_conn, table, key_column, current[key_column], candidate)
            updated += 1
            continue

        # Tracked attribute changed on a new day: close the current
        # version, insert a new one — both in this same transaction.
        olap_conn.execute(
            text(
                f"UPDATE {table} SET effective_to = :effective_from, is_current = 0 "
                f"WHERE {key_column} = :key"
            ),
            {"effective_from": effective_from, "key": current[key_column]},
        )
        olap_conn.execute(
            text(
                f"INSERT INTO {table} "
                f"({', '.join(candidate.keys())}, effective_from, effective_to, is_current) "
                f"VALUES ({', '.join(f':{c}' for c in candidate.keys())}, "
                f":effective_from, NULL, 1)"
            ),
            {**candidate, "effective_from": effective_from},
        )
        inserted += 1

    return LoadCounts(inserted, updated, unchanged)


def _update_current_row(
    olap_conn: Connection, table: str, key_column: str, key_value: int, candidate: dict
) -> None:
    set_clause = ", ".join(f"{c} = :{c}" for c in candidate)
    olap_conn.execute(
        text(f"UPDATE {table} SET {set_clause} WHERE {key_column} = :key"),
        {**candidate, "key": key_value},
    )
