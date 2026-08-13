"""Surrogate key resolution (ADR-021): natural id -> Kimball surrogate
key, differently for Type 1 vs. SCD2 dimensions. Every resolver bulk-
fetches once per batch into an in-memory dict — never one query per row.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection


def resolve_type1(olap_conn: Connection, dim_table: str, natural_id_column: str) -> dict[int, int]:
    """{natural_id: surrogate_key} for every row currently in a Type 1
    dimension. Table/column names come only from this module's own
    callers (hardcoded per dimension), never external input.
    """

    key_column = f"{dim_table[4:]}_key"  # dim_product -> product_key, etc.
    rows = olap_conn.execute(
        text(f"SELECT {natural_id_column}, {key_column} FROM {dim_table}")
    ).all()
    return {row[0]: row[1] for row in rows}


def resolve_scd2_as_of(
    olap_conn: Connection,
    dim_table: str,
    natural_id_column: str,
    queries: list[tuple[int, int, date]],
) -> dict[int, int | None]:
    """Resolves a batch of (row_id, natural_id, business_date) queries
    against an SCD2 dimension, each to the version whose
    [effective_from, effective_to) range covers *that specific query's*
    business date — not unconditionally the current version (ADR-021).

    Keyed by row_id, not natural_id: two fact rows can reference the same
    natural_id (e.g. the same supplier) with different business dates and
    legitimately resolve to different surrogate keys if a tracked
    attribute changed in between — a dict keyed by natural_id alone
    cannot represent that. Returns {row_id: surrogate_key_or_None}; None
    means no version covers that date (a DQ-3 failure for the caller to
    quarantine).

    Bulk-fetches every version of every touched natural id in one query
    (not one query per row), then resolves each query in Python.
    """

    if not queries:
        return {}

    key_column = f"{dim_table[4:]}_key"
    natural_ids = tuple({nid for _, nid, _ in queries})
    placeholder = ",".join(f":id{i}" for i in range(len(natural_ids)))
    params = {f"id{i}": nid for i, nid in enumerate(natural_ids)}

    rows = olap_conn.execute(
        text(
            f"SELECT {natural_id_column}, {key_column}, effective_from, effective_to "
            f"FROM {dim_table} WHERE {natural_id_column} IN ({placeholder})"
        ),
        params,
    ).all()

    versions_by_natural_id: dict[int, list[tuple]] = {}
    for natural_id, surrogate_key, effective_from, effective_to in rows:
        versions_by_natural_id.setdefault(natural_id, []).append(
            (surrogate_key, effective_from, effective_to)
        )

    resolved: dict[int, int | None] = {}
    for row_id, natural_id, business_date in queries:
        match = None
        for surrogate_key, effective_from, effective_to in versions_by_natural_id.get(
            natural_id, []
        ):
            if effective_from <= business_date and (
                effective_to is None or business_date < effective_to
            ):
                match = surrogate_key
                break
        resolved[row_id] = match

    return resolved


def date_key_for(business_date: date) -> int:
    """dim_date's surrogate key is deterministically YYYYMMDD (Phase 4,
    01_dim_date.sql) — computed directly, no DB lookup, since the two
    are guaranteed to agree by construction (ADR-021)."""

    return int(business_date.strftime("%Y%m%d"))
