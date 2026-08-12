"""Top-level Stage A validation orchestrator: runs DQ-1, DQ-2, DQ-3,
DQ-4, and DQ-5 against every row in a batch, splitting it into accepted
rows (zero violations) and quarantined rows (one or more violations,
with every violation preserved — not just the first).
"""

from collections import defaultdict

from sqlalchemy.engine.row import RowMapping

from etl.extract.registry import TableSpec
from etl.validate.rules import (
    Violation,
    check_completeness,
    check_duplicate_rows,
    check_invalid_values,
    check_referential_integrity,
    check_uniqueness_within_batch,
)


def validate_batch(
    rows: list[RowMapping], spec: TableSpec, valid_ids_by_table: dict[str, set]
) -> tuple[list[RowMapping], list[tuple[RowMapping, list[Violation]]]]:
    accepted: list[RowMapping] = []
    quarantined: list[tuple[RowMapping, list[Violation]]] = []

    seen_keys: dict[str, set] = defaultdict(set)
    seen_row_hashes: set = set()

    for row in rows:
        violations: list[Violation] = []
        violations += check_completeness(row, spec)
        violations += check_uniqueness_within_batch(row, spec, seen_keys)
        violations += check_referential_integrity(row, spec, valid_ids_by_table)
        violations += check_duplicate_rows(row, spec, seen_row_hashes)
        violations += check_invalid_values(row, spec)

        if violations:
            quarantined.append((row, violations))
        else:
            accepted.append(row)

    return accepted, quarantined
