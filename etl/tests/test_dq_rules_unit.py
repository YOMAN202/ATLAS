"""Direct tests of every DQ-1 through DQ-5 rule function (etl/validate/rules.py).

Why unit-level, not only end-to-end: atlas_oltp's own schema already
enforces NOT NULL, UNIQUE, CHECK, and FK constraints matching almost
every rule registered in etl/extract/registry.py — genuinely bad data
usually can't even be inserted into the real OLTP test schema to reach
Stage A's validation. That is Stage A's validation working as defense-
in-depth against a well-constrained source, not a gap — but it means the
rule LOGIC has to be proven directly against constructed rows, not only
via OLTP round-trips. test_pipeline_integration.py covers the (smaller)
set of columns OLTP does not already constrain, end-to-end.
"""

from etl.extract.registry import REGISTRY_BY_NAME
from etl.validate.rules import (
    check_completeness,
    check_duplicate_rows,
    check_invalid_values,
    check_referential_integrity,
    check_uniqueness_within_batch,
)


def test_dq1_completeness_catches_null_required_column():
    spec = REGISTRY_BY_NAME["products"]
    row = {"sku": "SKU-1", "name": None, "unit_of_measure": "EA", "unit_cost": 1, "unit_price": 2}

    violations = check_completeness(row, spec)

    assert ("DQ-1", "required column 'name' is null") in violations


def test_dq1_completeness_passes_when_all_required_present():
    spec = REGISTRY_BY_NAME["products"]
    row = {
        "sku": "SKU-1",
        "name": "Widget",
        "unit_of_measure": "EA",
        "unit_cost": 1,
        "unit_price": 2,
    }

    assert check_completeness(row, spec) == []


def test_dq2_uniqueness_catches_duplicate_business_key_within_batch():
    spec = REGISTRY_BY_NAME["products"]
    seen: dict[str, set] = {"sku": set()}

    row_a = {"sku": "SKU-DUP"}
    row_b = {"sku": "SKU-DUP"}

    assert check_uniqueness_within_batch(row_a, spec, seen) == []
    violations_b = check_uniqueness_within_batch(row_b, spec, seen)

    assert ("DQ-2", "duplicate value for unique column 'sku': 'SKU-DUP'") in violations_b


def test_dq3_referential_integrity_catches_unresolvable_fk():
    spec = REGISTRY_BY_NAME["warehouses"]
    row = {"region_id": 9999}
    valid_ids = {"regions": {1, 2, 3}}

    violations = check_referential_integrity(row, spec, valid_ids)

    assert len(violations) == 1
    assert violations[0][0] == "DQ-3"
    assert "9999" in violations[0][1]


def test_dq3_referential_integrity_passes_when_fk_resolves():
    spec = REGISTRY_BY_NAME["warehouses"]
    row = {"region_id": 2}
    valid_ids = {"regions": {1, 2, 3}}

    assert check_referential_integrity(row, spec, valid_ids) == []


def test_dq4_duplicate_rows_catches_exact_duplicate():
    spec = REGISTRY_BY_NAME["order_lines"]
    seen_hashes: set = set()
    row_a = {"id": 1, "order_id": 5, "product_id": 7, "ordered_quantity": 3}
    row_b = dict(row_a)  # exact duplicate content

    assert check_duplicate_rows(row_a, spec, seen_hashes) == []
    violations = check_duplicate_rows(row_b, spec, seen_hashes)

    assert violations == [("DQ-4", "exact duplicate row within this extraction batch")]


def test_dq4_duplicate_rows_passes_for_distinct_rows():
    spec = REGISTRY_BY_NAME["order_lines"]
    seen_hashes: set = set()
    row_a = {"id": 1, "ordered_quantity": 3}
    row_b = {"id": 2, "ordered_quantity": 5}

    assert check_duplicate_rows(row_a, spec, seen_hashes) == []
    assert check_duplicate_rows(row_b, spec, seen_hashes) == []


def test_dq5_invalid_values_catches_out_of_range():
    spec = REGISTRY_BY_NAME["order_lines"]
    row = {"ordered_quantity": -5}

    violations = check_invalid_values(row, spec)

    assert len(violations) == 1
    assert violations[0][0] == "DQ-5"
    assert "ordered_quantity" in violations[0][1]


def test_dq5_invalid_values_passes_for_valid_value():
    spec = REGISTRY_BY_NAME["order_lines"]
    row = {"ordered_quantity": 10}

    assert check_invalid_values(row, spec) == []
