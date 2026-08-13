"""Reads etl_extract_staging — Stage B's input. Transform reads from
this durable, validated snapshot, never by re-querying OLTP directly:
Stage A already captured and validated exactly what should be
transformed, and OLTP may have moved on since.
"""

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection


def read_staged(olap_conn: Connection, source_table: str) -> list[dict]:
    rows = olap_conn.execute(
        text(
            "SELECT source_id, payload FROM etl_extract_staging WHERE source_table = :t "
            "ORDER BY source_id"
        ),
        {"t": source_table},
    ).all()
    return [{"source_id": source_id, **json.loads(payload)} for source_id, payload in rows]


def read_staged_by_id(olap_conn: Connection, source_table: str) -> dict[int, dict]:
    return {row["source_id"]: row for row in read_staged(olap_conn, source_table)}


_CHUNK_SIZE = 2000


def read_staged_fields(
    olap_conn: Connection, source_table: str, fields: tuple[str, ...]
) -> dict[int, tuple]:
    """Reads only specific JSON fields (via JSON_UNQUOTE/JSON_EXTRACT,
    evaluated in MySQL, not Python) for every staged row of a table —
    for a large lookup table where a caller needs just one or two fields
    per row, not the whole payload (e.g. fact_orders needs shipments'
    shipment_number alone, not all of a shipment's ~15 columns). Avoids
    materializing hundreds of thousands of full-payload dicts in Python
    memory just to read a couple of fields out of each.

    Returns {source_id: (field1_value, field2_value, ...)}, matching the
    order of `fields`. Values come back as strings (JSON_UNQUOTE) or NULL
    — callers that need them typed should parse (see etl/transform/parsing.py).

    NULLIF(..., 'null') matters here: JSON_EXTRACT on a JSON null value
    (not a missing key — an explicit null, e.g. an unfulfilled line's
    shipment_id) returns the JSON null scalar, and JSON_UNQUOTE of that
    is the literal 4-character string 'null', not SQL NULL. Without this,
    every nullable field silently becomes the string 'null' instead of
    None.
    """

    extracts = ", ".join(
        f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.{f}')), 'null')" for f in fields
    )
    rows = olap_conn.execute(
        text(f"SELECT source_id, {extracts} FROM etl_extract_staging WHERE source_table = :t"),
        {"t": source_table},
    ).all()
    return {row[0]: tuple(row[1:]) for row in rows}


def read_staged_subset_by_id(
    olap_conn: Connection, source_table: str, source_ids: set[int]
) -> dict[int, dict]:
    """Same as read_staged_by_id, but only the given source_ids — for a
    lookup table that's far larger than what a caller actually needs
    (e.g. fact_returns needs ~34k specific order_lines out of 732k
    staged, not the whole table). Chunked (not one IN-clause with tens of
    thousands of placeholders, which risks becoming its own bottleneck)."""

    if not source_ids:
        return {}

    result: dict[int, dict] = {}
    id_list = list(source_ids)
    for i in range(0, len(id_list), _CHUNK_SIZE):
        chunk = id_list[i : i + _CHUNK_SIZE]
        placeholder = ",".join(f":id{i}" for i in range(len(chunk)))
        params = {f"id{i}": sid for i, sid in enumerate(chunk)}
        rows = olap_conn.execute(
            text(
                f"SELECT source_id, payload FROM etl_extract_staging "
                f"WHERE source_table = :t AND source_id IN ({placeholder})"
            ),
            {"t": source_table, **params},
        ).all()
        for source_id, payload in rows:
            result[source_id] = {"source_id": source_id, **json.loads(payload)}
    return result
