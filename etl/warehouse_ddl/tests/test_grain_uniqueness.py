"""Grain-level validation: for each fact table, prove its stated grain
(see each NN_fact_*.sql file's header comment) is enforced by the DDL,
not just documented — insert one valid row, then attempt a second row
with the SAME logical grain key (differing only in non-key values) and
confirm it is rejected by the grain-enforcing UNIQUE constraint.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_fact_orders_grain_is_one_row_per_order_line(
    db_conn, date_key_a, product_key, customer_key
):
    """Grain key: source_order_line_id. A second row for the same order
    line — even with different order/quantity values — must be rejected."""

    insert = text(
        "INSERT INTO fact_orders "
        "(source_order_line_id, order_number, order_line_number, order_date_key, "
        " product_key, customer_key, ordered_quantity, allocated_quantity, "
        " backordered_quantity, unit_price, unit_cost, extended_revenue, extended_cost, "
        " gross_margin) "
        "VALUES (:source_id, :order_number, 1, :date_key, :product_key, :customer_key, "
        " 10, 10, 0, 19.99, 10.00, 199.90, 100.00, 99.90)"
    )
    params = {"date_key": date_key_a, "product_key": product_key, "customer_key": customer_key}
    db_conn.execute(insert, {**params, "source_id": 100, "order_number": "ORD-100"})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                insert, {**params, "source_id": 100, "order_number": "ORD-100-DUPLICATE"}
            )


def test_fact_shipments_grain_is_one_row_per_shipment(
    db_conn, carrier_key, warehouse_key, date_key_a
):
    """Grain key: source_shipment_id."""

    insert = text(
        "INSERT INTO fact_shipments "
        "(source_shipment_id, shipment_number, status_code, carrier_key, "
        " origin_warehouse_key, destination_warehouse_key, ship_date_key) "
        "VALUES (:source_id, :shipment_number, 'CREATED', :carrier_key, :warehouse_key, "
        " :warehouse_key, :date_key)"
    )
    params = {"carrier_key": carrier_key, "warehouse_key": warehouse_key, "date_key": date_key_a}
    db_conn.execute(insert, {**params, "source_id": 100, "shipment_number": "SHIP-100"})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(insert, {**params, "source_id": 100, "shipment_number": "SHIP-100-DUP"})


def test_fact_inventory_snapshot_grain_is_product_warehouse_date(
    db_conn, product_key, warehouse_key, date_key_a
):
    """Grain key: (product_key, warehouse_key, snapshot_date_key) — the
    explicit "one row per product, per warehouse, per snapshot date"
    statement in 12_fact_inventory_snapshot.sql. A second row for the
    same (product, warehouse, date) — even with different quantities —
    must be rejected."""

    insert = text(
        "INSERT INTO fact_inventory_snapshot "
        "(snapshot_date_key, product_key, warehouse_key, quantity_on_hand, "
        " quantity_reserved, quantity_available, inventory_value, is_stockout) "
        "VALUES (:date_key, :product_key, :warehouse_key, :qty, 0, :qty, 100.00, 0)"
    )
    params = {"date_key": date_key_a, "product_key": product_key, "warehouse_key": warehouse_key}
    db_conn.execute(insert, {**params, "qty": 50})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            # Different quantity, same (product, warehouse, date) grain — must still collide.
            db_conn.execute(insert, {**params, "qty": 999})


def test_fact_procurement_grain_is_one_row_per_po_line(
    db_conn, supplier_key, product_key, warehouse_key, date_key_a
):
    """Grain key: source_po_line_id."""

    insert = text(
        "INSERT INTO fact_procurement "
        "(source_po_line_id, po_number, po_line_number, po_status_code, supplier_key, "
        " product_key, warehouse_key, order_date_key, ordered_quantity, unit_cost, "
        " extended_cost, received_quantity, quality_rejected_quantity) "
        "VALUES (:source_id, :po_number, 1, 'CONFIRMED', :supplier_key, :product_key, "
        " :warehouse_key, :date_key, 100, 10.00, 1000.00, 0, 0)"
    )
    params = {
        "supplier_key": supplier_key,
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "date_key": date_key_a,
    }
    db_conn.execute(insert, {**params, "source_id": 100, "po_number": "PO-100"})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(insert, {**params, "source_id": 100, "po_number": "PO-100-DUP"})


def test_fact_supplier_delivery_grain_is_one_row_per_po_line(
    db_conn, supplier_key, product_key, warehouse_key, date_key_a, date_key_b
):
    """Grain key: source_po_line_id."""

    insert = text(
        "INSERT INTO fact_supplier_delivery "
        "(source_po_line_id, po_number, po_line_number, supplier_key, product_key, "
        " warehouse_key, delivery_date_key, expected_delivery_date_key, ordered_quantity, "
        " received_quantity, quality_rejected_quantity, quality_accepted_quantity, "
        " is_on_time, lead_time_variance_days) "
        "VALUES (:source_id, :po_number, 1, :supplier_key, :product_key, :warehouse_key, "
        " :date_key_b, :date_key_a, 100, 100, 0, 100, 1, -1)"
    )
    params = {
        "supplier_key": supplier_key,
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "date_key_a": date_key_a,
        "date_key_b": date_key_b,
    }
    db_conn.execute(insert, {**params, "source_id": 100, "po_number": "PO-100"})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(insert, {**params, "source_id": 100, "po_number": "PO-100-DUP"})


def test_fact_returns_grain_is_one_row_per_return_line(
    db_conn, product_key, customer_key, date_key_a
):
    """Grain key: source_return_line_id."""

    insert = text(
        "INSERT INTO fact_returns "
        "(source_return_line_id, return_number, order_number, reason_code, product_key, "
        " customer_key, return_date_key, returned_quantity, unit_price, unit_cost, "
        " return_value, return_cost_value) "
        "VALUES (:source_id, :return_number, 'ORD-100', 'DAMAGED', :product_key, "
        " :customer_key, :date_key, 2, 19.99, 10.00, 39.98, 20.00)"
    )
    params = {"product_key": product_key, "customer_key": customer_key, "date_key": date_key_a}
    db_conn.execute(insert, {**params, "source_id": 100, "return_number": "RET-100"})

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(insert, {**params, "source_id": 100, "return_number": "RET-100-DUP"})
