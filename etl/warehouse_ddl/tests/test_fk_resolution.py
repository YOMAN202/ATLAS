"""Roadmap Phase 4 Testing Requirement: "a smoke test inserting a handful
of synthetic rows validates FK resolution fact -> dim."

For each of the 6 fact tables: insert one synthetic row per dimension it
references (via conftest.py's shared fixtures), insert one valid fact
row referencing those real surrogate keys (must succeed), then attempt a
fact insert with a nonexistent surrogate key (must raise IntegrityError)
— proving the FK constraints are real and enforced, not just declared.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

BOGUS_KEY = 999999


def test_fact_orders_fk_resolution(db_conn, date_key_a, product_key, customer_key):
    db_conn.execute(
        text(
            "INSERT INTO fact_orders "
            "(source_order_line_id, order_number, order_line_number, order_date_key, "
            " product_key, customer_key, ordered_quantity, allocated_quantity, "
            " backordered_quantity, unit_price, unit_cost, extended_revenue, extended_cost, "
            " gross_margin) "
            "VALUES (1, 'ORD-1', 1, :date_key, :product_key, :customer_key, 10, 10, 0, "
            " 19.99, 10.00, 199.90, 100.00, 99.90)"
        ),
        {"date_key": date_key_a, "product_key": product_key, "customer_key": customer_key},
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_orders "
                    "(source_order_line_id, order_number, order_line_number, order_date_key, "
                    " product_key, customer_key, ordered_quantity, allocated_quantity, "
                    " backordered_quantity, unit_price, unit_cost, extended_revenue, "
                    " extended_cost, gross_margin) "
                    "VALUES (2, 'ORD-2', 1, :date_key, :bogus, :customer_key, 10, 10, 0, "
                    " 19.99, 10.00, 199.90, 100.00, 99.90)"
                ),
                {"date_key": date_key_a, "bogus": BOGUS_KEY, "customer_key": customer_key},
            )


def test_fact_shipments_fk_resolution(db_conn, carrier_key, warehouse_key, date_key_a):
    db_conn.execute(
        text(
            "INSERT INTO fact_shipments "
            "(source_shipment_id, shipment_number, status_code, carrier_key, "
            " origin_warehouse_key, destination_warehouse_key, ship_date_key) "
            "VALUES (1, 'SHIP-1', 'CREATED', :carrier_key, :warehouse_key, :warehouse_key, "
            " :date_key)"
        ),
        {"carrier_key": carrier_key, "warehouse_key": warehouse_key, "date_key": date_key_a},
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_shipments "
                    "(source_shipment_id, shipment_number, status_code, carrier_key, "
                    " origin_warehouse_key, destination_warehouse_key, ship_date_key) "
                    "VALUES (2, 'SHIP-2', 'CREATED', :bogus, :warehouse_key, :warehouse_key, "
                    " :date_key)"
                ),
                {"bogus": BOGUS_KEY, "warehouse_key": warehouse_key, "date_key": date_key_a},
            )


def test_fact_inventory_snapshot_fk_resolution(db_conn, product_key, warehouse_key, date_key_a):
    db_conn.execute(
        text(
            "INSERT INTO fact_inventory_snapshot "
            "(snapshot_date_key, product_key, warehouse_key, quantity_on_hand, "
            " quantity_reserved, quantity_available, inventory_value, is_stockout) "
            "VALUES (:date_key, :product_key, :warehouse_key, 100, 20, 80, 800.00, 0)"
        ),
        {"date_key": date_key_a, "product_key": product_key, "warehouse_key": warehouse_key},
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_inventory_snapshot "
                    "(snapshot_date_key, product_key, warehouse_key, quantity_on_hand, "
                    " quantity_reserved, quantity_available, inventory_value, is_stockout) "
                    "VALUES (:date_key, :bogus, :warehouse_key, 100, 20, 80, 800.00, 0)"
                ),
                {"date_key": date_key_a, "bogus": BOGUS_KEY, "warehouse_key": warehouse_key},
            )


def test_fact_procurement_fk_resolution(
    db_conn, supplier_key, product_key, warehouse_key, date_key_a
):
    db_conn.execute(
        text(
            "INSERT INTO fact_procurement "
            "(source_po_line_id, po_number, po_line_number, po_status_code, supplier_key, "
            " product_key, warehouse_key, order_date_key, ordered_quantity, unit_cost, "
            " extended_cost, received_quantity, quality_rejected_quantity) "
            "VALUES (1, 'PO-1', 1, 'CONFIRMED', :supplier_key, :product_key, :warehouse_key, "
            " :date_key, 100, 10.00, 1000.00, 0, 0)"
        ),
        {
            "supplier_key": supplier_key,
            "product_key": product_key,
            "warehouse_key": warehouse_key,
            "date_key": date_key_a,
        },
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_procurement "
                    "(source_po_line_id, po_number, po_line_number, po_status_code, "
                    " supplier_key, product_key, warehouse_key, order_date_key, "
                    " ordered_quantity, unit_cost, extended_cost, received_quantity, "
                    " quality_rejected_quantity) "
                    "VALUES (2, 'PO-2', 1, 'CONFIRMED', :bogus, :product_key, :warehouse_key, "
                    " :date_key, 100, 10.00, 1000.00, 0, 0)"
                ),
                {
                    "bogus": BOGUS_KEY,
                    "product_key": product_key,
                    "warehouse_key": warehouse_key,
                    "date_key": date_key_a,
                },
            )


def test_fact_supplier_delivery_fk_resolution(
    db_conn, supplier_key, product_key, warehouse_key, date_key_a, date_key_b
):
    db_conn.execute(
        text(
            "INSERT INTO fact_supplier_delivery "
            "(source_po_line_id, po_number, po_line_number, supplier_key, product_key, "
            " warehouse_key, delivery_date_key, expected_delivery_date_key, ordered_quantity, "
            " received_quantity, quality_rejected_quantity, quality_accepted_quantity, "
            " is_on_time, lead_time_variance_days) "
            "VALUES (1, 'PO-1', 1, :supplier_key, :product_key, :warehouse_key, :date_key_b, "
            " :date_key_a, 100, 100, 0, 100, 1, -1)"
        ),
        {
            "supplier_key": supplier_key,
            "product_key": product_key,
            "warehouse_key": warehouse_key,
            "date_key_a": date_key_a,
            "date_key_b": date_key_b,
        },
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_supplier_delivery "
                    "(source_po_line_id, po_number, po_line_number, supplier_key, product_key, "
                    " warehouse_key, delivery_date_key, expected_delivery_date_key, "
                    " ordered_quantity, received_quantity, quality_rejected_quantity, "
                    " quality_accepted_quantity, is_on_time, lead_time_variance_days) "
                    "VALUES (2, 'PO-2', 1, :bogus, :product_key, :warehouse_key, :date_key_b, "
                    " :date_key_a, 100, 100, 0, 100, 1, -1)"
                ),
                {
                    "bogus": BOGUS_KEY,
                    "product_key": product_key,
                    "warehouse_key": warehouse_key,
                    "date_key_a": date_key_a,
                    "date_key_b": date_key_b,
                },
            )


def test_fact_returns_fk_resolution(db_conn, product_key, customer_key, date_key_a):
    db_conn.execute(
        text(
            "INSERT INTO fact_returns "
            "(source_return_line_id, return_number, order_number, reason_code, product_key, "
            " customer_key, return_date_key, returned_quantity, unit_price, unit_cost, "
            " return_value, return_cost_value) "
            "VALUES (1, 'RET-1', 'ORD-1', 'DAMAGED', :product_key, :customer_key, :date_key, "
            " 2, 19.99, 10.00, 39.98, 20.00)"
        ),
        {"product_key": product_key, "customer_key": customer_key, "date_key": date_key_a},
    )

    with pytest.raises(IntegrityError):
        with db_conn.begin_nested():
            db_conn.execute(
                text(
                    "INSERT INTO fact_returns "
                    "(source_return_line_id, return_number, order_number, reason_code, "
                    " product_key, customer_key, return_date_key, returned_quantity, "
                    " unit_price, unit_cost, return_value, return_cost_value) "
                    "VALUES (2, 'RET-2', 'ORD-2', 'DAMAGED', :bogus, :customer_key, :date_key, "
                    " 2, 19.99, 10.00, 39.98, 20.00)"
                ),
                {"bogus": BOGUS_KEY, "customer_key": customer_key, "date_key": date_key_a},
            )
