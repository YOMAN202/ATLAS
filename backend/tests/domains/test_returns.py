from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.orders.service import allocate_order_line, create_order
from app.domains.returns.service import create_return, inspect_return_line
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.models import InventoryPosition, OrderLine, ReturnLine

NOW = datetime(2026, 1, 20, 9, 0, 0)


@pytest.fixture
def fulfilled_order_line(db_session, customer, product, warehouse, warehouse_zone, lookups):
    order = create_order(
        db_session,
        order_number="ORD-2001",
        customer_id=customer.id,
        order_date=date(2026, 1, 10),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 20,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            }
        ],
    )
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
        quantity_delta=20,
        occurred_at=NOW,
    )
    line = db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalar_one()
    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    return db_session.get(OrderLine, line.id)


def test_create_return_uninspected(db_session, fulfilled_order_line):
    ret = create_return(
        db_session,
        return_number="RET-1001",
        order_id=fulfilled_order_line.order_id,
        return_date=date(2026, 1, 20),
        lines=[
            {
                "order_line_id": fulfilled_order_line.id,
                "line_number": 1,
                "returned_quantity": 5,
                "reason_code": "DAMAGED",
            }
        ],
    )

    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()
    assert return_line.disposition_id is None
    assert return_line.inspected_at is None


# FR-4.3 sanity check: cannot return more than was ever allocated to the customer.
def test_create_return_exceeding_allocated_raises(db_session, fulfilled_order_line):
    with pytest.raises(InvalidStateTransitionError):
        create_return(
            db_session,
            return_number="RET-1002",
            order_id=fulfilled_order_line.order_id,
            return_date=date(2026, 1, 20),
            lines=[
                {
                    "order_line_id": fulfilled_order_line.id,
                    "line_number": 1,
                    "returned_quantity": 999,
                    "reason_code": "DAMAGED",
                }
            ],
        )


# BR-5: a SELLABLE disposition restocks inventory at the specified zone.
def test_inspect_sellable_restocks_inventory(
    db_session, fulfilled_order_line, warehouse, warehouse_zone, product
):
    ret = create_return(
        db_session,
        return_number="RET-1003",
        order_id=fulfilled_order_line.order_id,
        return_date=date(2026, 1, 20),
        lines=[
            {
                "order_line_id": fulfilled_order_line.id,
                "line_number": 1,
                "returned_quantity": 5,
                "reason_code": "DAMAGED",
            }
        ],
    )
    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()

    before = db_session.execute(
        select(InventoryPosition).where(
            InventoryPosition.product_id == product.id,
            InventoryPosition.warehouse_id == warehouse.id,
            InventoryPosition.warehouse_zone_id == warehouse_zone.id,
        )
    ).scalar_one()
    on_hand_before = before.quantity_on_hand

    inspect_return_line(
        db_session,
        return_line_id=return_line.id,
        disposition_code="SELLABLE",
        inspected_at=NOW,
        warehouse_zone_id=warehouse_zone.id,
    )

    after = db_session.get(InventoryPosition, before.id)
    assert after.quantity_on_hand == on_hand_before + 5
    reloaded_line = db_session.get(ReturnLine, return_line.id)
    assert reloaded_line.inspected_at == NOW


# BR-5: a non-SELLABLE disposition leaves sellable inventory untouched.
def test_inspect_quarantine_does_not_restock(
    db_session, fulfilled_order_line, warehouse, warehouse_zone, product
):
    ret = create_return(
        db_session,
        return_number="RET-1004",
        order_id=fulfilled_order_line.order_id,
        return_date=date(2026, 1, 20),
        lines=[
            {
                "order_line_id": fulfilled_order_line.id,
                "line_number": 1,
                "returned_quantity": 5,
                "reason_code": "QUALITY_DEFECT",
            }
        ],
    )
    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()

    before = db_session.execute(
        select(InventoryPosition).where(
            InventoryPosition.product_id == product.id,
            InventoryPosition.warehouse_id == warehouse.id,
            InventoryPosition.warehouse_zone_id == warehouse_zone.id,
        )
    ).scalar_one()
    on_hand_before = before.quantity_on_hand

    inspect_return_line(
        db_session,
        return_line_id=return_line.id,
        disposition_code="QUARANTINE",
        inspected_at=NOW,
    )

    after = db_session.get(InventoryPosition, before.id)
    assert after.quantity_on_hand == on_hand_before


def test_double_inspection_raises(db_session, fulfilled_order_line, warehouse_zone):
    ret = create_return(
        db_session,
        return_number="RET-1005",
        order_id=fulfilled_order_line.order_id,
        return_date=date(2026, 1, 20),
        lines=[
            {
                "order_line_id": fulfilled_order_line.id,
                "line_number": 1,
                "returned_quantity": 5,
                "reason_code": "DAMAGED",
            }
        ],
    )
    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()
    inspect_return_line(
        db_session,
        return_line_id=return_line.id,
        disposition_code="SELLABLE",
        inspected_at=NOW,
        warehouse_zone_id=warehouse_zone.id,
    )

    with pytest.raises(InvalidStateTransitionError):
        inspect_return_line(
            db_session,
            return_line_id=return_line.id,
            disposition_code="SELLABLE",
            inspected_at=NOW,
            warehouse_zone_id=warehouse_zone.id,
        )


def test_inspect_sellable_without_zone_raises(db_session, fulfilled_order_line):
    ret = create_return(
        db_session,
        return_number="RET-1006",
        order_id=fulfilled_order_line.order_id,
        return_date=date(2026, 1, 20),
        lines=[
            {
                "order_line_id": fulfilled_order_line.id,
                "line_number": 1,
                "returned_quantity": 5,
                "reason_code": "DAMAGED",
            }
        ],
    )
    return_line = db_session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()

    with pytest.raises(ValueError):
        inspect_return_line(
            db_session,
            return_line_id=return_line.id,
            disposition_code="SELLABLE",
            inspected_at=NOW,
        )


def test_inspect_unknown_return_line_raises(db_session, lookups):
    with pytest.raises(EntityNotFoundError):
        inspect_return_line(
            db_session,
            return_line_id=999999,
            disposition_code="SELLABLE",
            inspected_at=NOW,
        )
