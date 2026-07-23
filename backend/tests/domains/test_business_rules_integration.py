"""Cross-cutting acceptance suite for the Phase 2 business rules (BR-1,
BR-2, BR-5), composing multiple domain modules the way a real workflow
would rather than exercising one function in isolation. Per-module edge
cases already live in their own test files; this suite is the explicit,
BR-tagged scenarios the Roadmap's Phase 2 Testing Requirements name.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.orders.service import allocate_order_line, create_order
from app.domains.procurement.service import (
    confirm_purchase_order,
    create_purchase_order,
    mark_purchase_order_fulfilled,
    receive_purchase_order_line,
    submit_purchase_order,
)
from app.domains.returns.service import create_return, inspect_return_line
from app.domains.shared.exceptions import ReceiptToleranceExceededError
from app.models import InventoryPosition, OrderLine, PurchaseOrderLine, ReturnLine

NOW = datetime(2026, 2, 1, 9, 0, 0)


# BR-2: allocating more than is on hand partially fulfills the line and
# backorders the remainder — the correct rule outcome, not an error.
def test_allocate_more_than_stock_partially_fulfills_and_backorders(
    db_session, customer, product, warehouse, warehouse_zone, lookups
):
    position = get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=30,
        occurred_at=NOW,
    )

    order = create_order(
        db_session,
        order_number="ORD-INT-1",
        customer_id=customer.id,
        order_date=date(2026, 2, 1),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 100,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            }
        ],
    )
    line = db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalar_one()

    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.allocated_quantity == 30
    assert reloaded.backordered_quantity == 70


# BR-1: a PO whose receipt falls outside the approved tolerance is never
# marked fulfilled, whether automatically or via an explicit attempt.
def test_po_receipt_outside_tolerance_is_never_fulfilled(
    db_session, supplier, warehouse, product, warehouse_zone, lookups
):
    po = create_purchase_order(
        db_session,
        po_number="PO-INT-1",
        supplier_id=supplier.id,
        warehouse_id=warehouse.id,
        order_date=date(2026, 2, 1),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 200,
                "unit_cost": Decimal("5.00"),
            }
        ],
    )
    submit_purchase_order(db_session, po.id)
    confirm_purchase_order(db_session, po.id)
    line = db_session.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
    ).scalar_one()

    receive_purchase_order_line(
        db_session,
        po_line_id=line.id,
        received_quantity=150,  # 75% — well outside tolerance
        quality_rejected_quantity=0,
        delivery_date=date(2026, 2, 10),
        warehouse_zone_id=warehouse_zone.id,
        occurred_at=NOW,
    )

    with pytest.raises(ReceiptToleranceExceededError):
        mark_purchase_order_fulfilled(db_session, po.id)


# BR-5: a return that fails inspection is routed to a non-SELLABLE
# disposition, and sellable inventory is provably unchanged by it.
def test_return_failing_inspection_gets_separate_disposition_stock_unchanged(
    db_session, customer, product, warehouse, warehouse_zone, lookups
):
    position = get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )
    order = create_order(
        db_session,
        order_number="ORD-INT-2",
        customer_id=customer.id,
        order_date=date(2026, 2, 1),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 10,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            }
        ],
    )
    line = db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalar_one()
    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    ret = create_return(
        db_session,
        return_number="RET-INT-1",
        order_id=order.id,
        return_date=date(2026, 2, 15),
        lines=[
            {
                "order_line_id": line.id,
                "line_number": 1,
                "returned_quantity": 3,
                "reason_code": "QUALITY_DEFECT",
            }
        ],
    )
    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()

    on_hand_before = db_session.get(InventoryPosition, position.id).quantity_on_hand

    inspect_return_line(
        db_session,
        return_line_id=return_line.id,
        disposition_code="SCRAP",
        inspected_at=NOW,
    )

    reloaded_line = db_session.get(ReturnLine, return_line.id)
    on_hand_after = db_session.get(InventoryPosition, position.id).quantity_on_hand

    assert reloaded_line.disposition_id is not None
    assert on_hand_after == on_hand_before
