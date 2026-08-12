"""DQ-1 through DQ-5 rule checks (SRS §7), applied per extracted batch.

Each check function returns a list of (rule_code, detail) violations for
one row — a row can fail more than one rule, and each is recorded as its
own dq_quarantine entry (its UNIQUE constraint is keyed on
(source_table, source_id, rule_violated) specifically to support this),
satisfying DQ-6's "rule-level failure breakdown" rather than only
reporting the first failure found.

DQ-6 (audit logging) and DQ-7 (scoring) are not row-level checks — they
are the orchestration layer's responsibility (etl/audit/), not this
module's.
"""

from sqlalchemy.engine.row import RowMapping

from etl.extract.registry import TableSpec

Violation = tuple[str, str]


def check_completeness(row: RowMapping, spec: TableSpec) -> list[Violation]:
    """DQ-1: required columns must be non-null."""

    violations = []
    for column in spec.required_columns:
        if row.get(column) is None:
            violations.append(("DQ-1", f"required column '{column}' is null"))
    return violations


def check_uniqueness_within_batch(
    row: RowMapping, spec: TableSpec, seen_keys: dict[str, set]
) -> list[Violation]:
    """DQ-2: declared natural/business-key columns must be unique. OLTP
    already enforces this at the DB level (every business key in
    docs/data-dictionary.md is UNIQUE-constrained there), so a real
    violation reaching here would indicate a genuine anomaly — this is
    defense-in-depth, scoped to within-batch since Stage A has nothing
    loaded yet to compare against.
    """

    violations = []
    for column in spec.unique_columns:
        value = row.get(column)
        if value is None:
            continue
        if value in seen_keys[column]:
            violations.append(("DQ-2", f"duplicate value for unique column '{column}': {value!r}"))
        else:
            seen_keys[column].add(value)
    return violations


def check_referential_integrity(
    row: RowMapping, spec: TableSpec, valid_ids_by_table: dict[str, set]
) -> list[Violation]:
    """DQ-3: every FK column must resolve to an existing row in its
    referenced table. valid_ids_by_table is bulk-fetched once per batch
    (etl/validate/fk_lookup.py), not queried per row.
    """

    violations = []
    for fk in spec.foreign_keys:
        value = row.get(fk.column)
        if value is None:
            continue  # nullable FKs are a completeness (DQ-1) concern, not DQ-3
        if value not in valid_ids_by_table.get(fk.referenced_table, set()):
            violations.append(
                (
                    "DQ-3",
                    f"'{fk.column}' = {value!r} does not resolve to any row in "
                    f"'{fk.referenced_table}'",
                )
            )
    return violations


def check_duplicate_rows(row: RowMapping, spec: TableSpec, seen_row_hashes: set) -> list[Violation]:
    """DQ-4: exact full-row duplicates within a batch. Distinct from
    DQ-2 (a specific declared business key repeating) — this catches the
    same row appearing twice verbatim, which OLTP's own PK-based SELECT
    can't produce on its own but is checked here as a real, testable
    safeguard rather than an assumption.
    """

    row_hash = hash(tuple(sorted(row.items())))
    if row_hash in seen_row_hashes:
        return [("DQ-4", "exact duplicate row within this extraction batch")]
    seen_row_hashes.add(row_hash)
    return []


def check_invalid_values(row: RowMapping, spec: TableSpec) -> list[Violation]:
    """DQ-5: domain/range checks on relevant fields."""

    violations = []
    for range_check in spec.range_checks:
        value = row.get(range_check.column)
        if value is not None and not range_check.is_valid(value):
            violations.append(
                ("DQ-5", f"'{range_check.column}' = {value!r}: {range_check.description}")
            )
    return violations
