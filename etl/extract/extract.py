"""Watermark-based incremental extraction (TDD §6 stage 1; ADR-008).

Pulls rows from one OLTP source table where the watermark column is
strictly greater than the last watermark (or everything, if there is no
prior watermark). Ordered by (watermark_column, pk_column) ascending —
not just for readability, but because that fixed order is what makes
downstream processing, logging, and the watermark-advancement
computation reproducible across reruns when multiple rows share the same
watermark timestamp (ADR-016's process-level determinism guarantee).
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine.row import RowMapping

from etl.extract.registry import TableSpec


def extract_batch(
    oltp_conn: Connection, spec: TableSpec, since: datetime | None
) -> list[RowMapping]:
    """Extract every row from spec.name changed since `since` (exclusive),
    or every row if `since` is None (first-ever extraction for this
    table). Read-only against atlas_oltp — this module never writes.

    Table/column names are interpolated directly (MySQL has no
    parameterized-identifier syntax) — safe here because they only ever
    come from the hardcoded REGISTRY (etl/extract/registry.py), never
    from external/user input.
    """

    if since is None:
        query = text(
            f"SELECT * FROM {spec.name} "
            f"ORDER BY {spec.watermark_column} ASC, {spec.pk_column} ASC"
        )
        params = {}
    else:
        query = text(
            f"SELECT * FROM {spec.name} "
            f"WHERE {spec.watermark_column} > :since "
            f"ORDER BY {spec.watermark_column} ASC, {spec.pk_column} ASC"
        )
        params = {"since": since}

    return list(oltp_conn.execute(query, params).mappings().all())
