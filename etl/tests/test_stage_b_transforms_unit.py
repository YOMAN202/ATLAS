"""Direct tests of the pure row-building functions in
etl/transform/facts.py and etl/transform/dimensions.py — no DB needed,
since these functions take pre-resolved lookups as plain dicts (per
their own module docstrings). Covers the quarantine-on-unresolved-FK
contract (ADR-019/ADR-021) and the computed-value logic (margins,
on-time flags, variance days) that a pure end-to-end test would only
exercise incidentally.
"""

from datetime import date
from decimal import Decimal

from etl.transform.dimensions import build_scd2_supplier_candidates, build_scd2_warehouse_candidates
from etl.transform.facts import (
    build_fact_orders_rows,
    build_fact_procurement_rows,
    build_fact_returns_rows,
    build_fact_shipments_rows,
    build_fact_supplier_delivery_rows,
)
from etl.transform.surrogate_keys import date_key_for


def _order_line(**overrides):
    row = {
        "source_id": 1,
        "order_id": 100,
        "product_id": 10,
        "line_number": 1,
        "ordered_quantity": 5,
        "allocated_quantity": 5,
        "backordered_quantity": 0,
        "unit_price": "19.99",
        "unit_cost": "10.00",
        "fulfillment_warehouse_id": None,
        "shipment_id": None,
    }
    row.update(overrides)
    return row


def _order(**overrides):
    row = {"customer_id": 1, "order_date": "2021-03-15", "order_number": "ORD-1"}
    row.update(overrides)
    return row


def test_fact_orders_computes_revenue_cost_and_margin():
    rows, quarantine = build_fact_orders_rows(
        [_order_line()], {100: _order()}, {10: 501}, {1: 601}, {}, {}
    )

    assert quarantine == []
    assert len(rows) == 1
    row = rows[0]
    assert row["extended_revenue"] == Decimal("19.99") * 5
    assert row["extended_cost"] == Decimal("10.00") * 5
    assert row["gross_margin"] == row["extended_revenue"] - row["extended_cost"]
    assert row["order_date_key"] == 20210315
    assert row["product_key"] == 501
    assert row["customer_key"] == 601


def test_fact_orders_quarantines_when_order_missing():
    rows, quarantine = build_fact_orders_rows(
        [_order_line(order_id=999)], {100: _order()}, {10: 501}, {1: 601}, {}, {}
    )

    assert rows == []
    assert len(quarantine) == 1
    source_id, rule, detail = quarantine[0]
    assert source_id == 1
    assert rule == "DQ-3"
    assert "999" in detail


def test_fact_orders_quarantines_when_product_or_customer_key_unresolved():
    rows, quarantine = build_fact_orders_rows(
        [_order_line()], {100: _order()}, {}, {1: 601}, {}, {}
    )

    assert rows == []
    assert quarantine[0][1] == "DQ-3"


def test_fact_orders_resolves_shipment_number_only_when_shipped():
    shipped, _ = build_fact_orders_rows(
        [_order_line(shipment_id=55)], {100: _order()}, {10: 501}, {1: 601}, {}, {55: "SHP-1"}
    )
    unshipped, _ = build_fact_orders_rows(
        [_order_line(shipment_id=None)], {100: _order()}, {10: 501}, {1: 601}, {}, {55: "SHP-1"}
    )

    assert shipped[0]["shipment_number"] == "SHP-1"
    assert unshipped[0]["shipment_number"] is None


def _shipment(**overrides):
    row = {
        "source_id": 1,
        "carrier_id": 20,
        "origin_warehouse_id": 30,
        "shipment_number": "SHP-1",
        "status_id": 1,
        "ship_date": "2021-03-01",
        "destination_warehouse_id": None,
        "destination_customer_id": None,
        "estimated_delivery_date": None,
        "actual_delivery_date": None,
        "distance_miles": None,
        "shipping_cost": None,
    }
    row.update(overrides)
    return row


def test_fact_shipments_is_on_time_true_when_delivered_by_estimate():
    rows, _ = build_fact_shipments_rows(
        [_shipment(estimated_delivery_date="2021-03-05", actual_delivery_date="2021-03-04")],
        {20: 701},
        {30: 801},
        {},
        {1: "DELIVERED"},
    )
    assert rows[0]["is_on_time"] is True
    assert rows[0]["transit_days"] == 3


def test_fact_shipments_is_on_time_false_when_delivered_late():
    rows, _ = build_fact_shipments_rows(
        [_shipment(estimated_delivery_date="2021-03-05", actual_delivery_date="2021-03-08")],
        {20: 701},
        {30: 801},
        {},
        {1: "DELIVERED"},
    )
    assert rows[0]["is_on_time"] is False


def test_fact_shipments_is_on_time_none_when_not_yet_delivered():
    rows, _ = build_fact_shipments_rows(
        [_shipment(estimated_delivery_date="2021-03-05", actual_delivery_date=None)],
        {20: 701},
        {30: 801},
        {},
        {1: "DELIVERED"},
    )
    assert rows[0]["is_on_time"] is None
    assert rows[0]["transit_days"] is None


def test_fact_shipments_quarantines_when_carrier_or_origin_unresolved():
    rows, quarantine = build_fact_shipments_rows([_shipment()], {}, {30: 801}, {}, {1: "DELIVERED"})
    assert rows == []
    assert quarantine[0][1] == "DQ-3"


def _po_line(**overrides):
    row = {
        "source_id": 1,
        "purchase_order_id": 900,
        "product_id": 10,
        "line_number": 1,
        "ordered_quantity": 100,
        "received_quantity": 100,
        "quality_rejected_quantity": 0,
        "unit_cost": "5.00",
        "actual_delivery_date": None,
    }
    row.update(overrides)
    return row


def _po(**overrides):
    row = {
        "po_number": "PO-1",
        "order_date": "2021-02-01",
        "status_id": 1,
        "expected_delivery_date": "2021-02-10",
    }
    row.update(overrides)
    return row


def test_fact_procurement_computes_extended_cost_and_quarantines_unresolved_supplier():
    rows, quarantine = build_fact_procurement_rows(
        [_po_line()], {900: _po()}, {10: 501}, {1: 401}, {1: 801}, {1: "OPEN"}
    )
    assert quarantine == []
    assert rows[0]["extended_cost"] == Decimal("5.00") * 100
    assert rows[0]["supplier_key"] == 401
    assert rows[0]["warehouse_key"] == 801

    rows2, quarantine2 = build_fact_procurement_rows(
        [_po_line()], {900: _po()}, {10: 501}, {1: None}, {1: 801}, {1: "OPEN"}
    )
    assert rows2 == []
    assert quarantine2[0][1] == "DQ-3"
    assert "2021-02-01" in quarantine2[0][2]


def test_fact_supplier_delivery_skips_lines_not_yet_delivered():
    rows, quarantine = build_fact_supplier_delivery_rows(
        [_po_line(actual_delivery_date=None)], {900: _po()}, {10: 501}, {1: 401}, {1: 801}
    )
    assert rows == []
    assert quarantine == []  # not delivered yet is not a DQ-3 failure, just not-yet-applicable


def test_fact_supplier_delivery_computes_on_time_and_variance():
    rows, quarantine = build_fact_supplier_delivery_rows(
        [
            _po_line(
                actual_delivery_date="2021-02-08", received_quantity=95, quality_rejected_quantity=5
            )
        ],
        {900: _po(expected_delivery_date="2021-02-10")},
        {10: 501},
        {1: 401},
        {1: 801},
    )
    assert quarantine == []
    row = rows[0]
    assert row["is_on_time"] is True
    assert row["lead_time_variance_days"] == -2
    assert row["quality_accepted_quantity"] == 90


def _return_line(**overrides):
    row = {
        "source_id": 1,
        "return_id": 300,
        "order_line_id": 1,
        "returned_quantity": 2,
        "reason_id": 1,
        "disposition_id": None,
    }
    row.update(overrides)
    return row


def test_fact_returns_computes_return_value_and_cost():
    rows, quarantine = build_fact_returns_rows(
        [_return_line()],
        {300: {"order_id": 100, "return_number": "RET-1", "return_date": "2021-04-01"}},
        {1: {"product_id": 10, "unit_price": "19.99", "unit_cost": "10.00"}},
        {100: {"order_number": "ORD-1", "customer_id": 1}},
        {10: 501},
        {1: 601},
        {1: "DEFECTIVE"},
        {},
    )
    assert quarantine == []
    row = rows[0]
    assert row["return_value"] == Decimal("19.99") * 2
    assert row["return_cost_value"] == Decimal("10.00") * 2
    assert row["reason_code"] == "DEFECTIVE"
    assert row["disposition_code"] is None


def test_fact_returns_quarantines_when_return_or_order_line_missing():
    rows, quarantine = build_fact_returns_rows(
        [_return_line(order_line_id=999)], {300: {"order_id": 100}}, {}, {}, {}, {}, {1: "X"}, {}
    )
    assert rows == []
    assert quarantine[0][1] == "DQ-3"


def test_scd2_supplier_candidates_carry_source_updated_at_and_tracked_columns():
    staged = [
        {
            "source_id": 1,
            "supplier_code": "SUP-1",
            "name": "Acme",
            "payment_terms_days": 30,
            "default_lead_time_days": 7,
            "is_active": 1,
            "updated_at": "2021-01-05T12:00:00",
        }
    ]

    candidates = build_scd2_supplier_candidates(staged)

    assert len(candidates) == 1
    c = candidates[0]
    assert c["supplier_id"] == 1
    assert c["payment_terms_days"] == 30
    assert c["source_updated_at"].date() == date(2021, 1, 5)


def test_scd2_warehouse_candidates_resolve_region_key():
    staged = [
        {
            "source_id": 7,
            "warehouse_code": "WH-1",
            "name": "Main",
            "region_id": 3,
            "total_capacity_units": 10000,
            "is_active": 1,
            "updated_at": "2021-01-05T12:00:00",
        }
    ]

    candidates = build_scd2_warehouse_candidates(staged, {3: 901})

    assert candidates[0]["warehouse_id"] == 7
    assert candidates[0]["region_key"] == 901


def test_date_key_for_is_yyyymmdd():
    assert date_key_for(date(2021, 3, 15)) == 20210315
