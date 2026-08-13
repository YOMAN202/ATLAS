"""Post-load reconciliation (Phase 5 plan §3): row-count reconciliation
and grain validation, run once per fact after its load step.

Grain validation is defense-in-depth, not a first line of defense — each
fact's `UNIQUE` grain constraint (Phase 4 DDL) already makes a duplicate
grain key impossible to insert. This catches a different failure mode: a
transform bug that computes the *wrong* grain key entirely (a `UNIQUE`
violation on the intended key wouldn't catch that).
"""

from typing import NamedTuple

from sqlalchemy import text
from sqlalchemy.engine import Connection


class ReconciliationResult(NamedTuple):
    table: str
    row_count: int
    expected_count: int
    row_count_matches: bool
    grain_violations: int


def reconcile_fact(
    olap_conn: Connection, table: str, grain_columns: tuple[str, ...], expected_count: int
) -> ReconciliationResult:
    row_count = olap_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()

    group_by = ", ".join(grain_columns)
    violations = olap_conn.execute(
        text(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT {group_by} FROM {table} GROUP BY {group_by} HAVING COUNT(*) > 1"
            f") dup"
        )
    ).scalar_one()

    return ReconciliationResult(
        table=table,
        row_count=row_count,
        expected_count=expected_count,
        row_count_matches=(row_count == expected_count),
        grain_violations=violations,
    )
