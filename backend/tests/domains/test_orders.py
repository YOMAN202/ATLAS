from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.orders.service import allocate_order_line, compute_order_status, create_order
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_code_by_id
from app.models import OrderLine, OrderStatus, Product

NOW = datetime(2026, 1, 15, 9, 0, 0)


@pytest.fixture
def product2(db_session):
    product = Product(
        sku="SKU-TEST-2",
        name="Test Product 2",
        unit_cost=Decimal("3.00"),
        unit_price=Decimal("9.99"),
    )
    db_session.add(product)
    db_session.flush()
    return product


def _status_code(db_session, order):
    return get_code_by_id(db_session, OrderStatus, order.status_id)


def _stock(db_session, *, product, warehouse, warehouse_zone, quantity):
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
        quantity_delta=quantity,
        occurred_at=NOW,
    )
    return position


@pytest.fixture
def pending_order(db_session, customer, product, lookups):
    return create_order(
        db_session,
        order_number="ORD-1001",
        customer_id=customer.id,
        order_date=date(2026, 1, 15),
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


def test_create_order_starts_pending_unallocated(db_session, pending_order):
    assert _status_code(db_session, pending_order) == "PENDING"
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()
    assert line.allocated_quantity == 0
    assert line.backordered_quantity == 0


# BR-2: full stock available -> the line is fully allocated, order -> ALLOCATED.
def test_allocate_full_stock_available(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity=100,
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.allocated_quantity == 100
    assert reloaded.backordered_quantity == 0
    assert reloaded.fulfillment_warehouse_id == warehouse.id
    assert _status_code(db_session, pending_order) == "ALLOCATED"


# BR-2: insufficient stock -> partial allocation + the remainder backordered.
def test_allocate_insufficient_stock_partial_and_backorder(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session, product=product, warehouse=warehouse, warehouse_zone=warehouse_zone, quantity=40
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.allocated_quantity == 40
    assert reloaded.backordered_quantity == 60
    # Nothing at all could be allocated for *some* of the order, but this
    # line did get a partial allocation, so the order is fully backordered
    # only when NO quantity was allocated anywhere; here total_allocated > 0.
    assert _status_code(db_session, pending_order) == "PARTIALLY_FULFILLED"


def test_allocate_zero_stock_fully_backorders_and_order_is_backordered(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups
):
    position = get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.allocated_quantity == 0
    assert reloaded.backordered_quantity == 100
    assert _status_code(db_session, pending_order) == "BACKORDERED"


def test_allocate_already_resolved_line_raises(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity=100,
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()
    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)

    with pytest.raises(InvalidStateTransitionError):
        allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position.id)


def test_allocate_product_mismatch_raises(
    db_session, pending_order, warehouse, warehouse_zone, product2, lookups
):
    mismatched_position = get_or_create_position(
        db_session,
        product_id=product2.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    with pytest.raises(InvalidStateTransitionError):
        allocate_order_line(
            db_session, order_line_id=line.id, inventory_position_id=mismatched_position.id
        )


def test_allocate_unknown_line_raises(db_session, warehouse, warehouse_zone, product, lookups):
    position = _stock(
        db_session, product=product, warehouse=warehouse, warehouse_zone=warehouse_zone, quantity=10
    )

    with pytest.raises(EntityNotFoundError):
        allocate_order_line(db_session, order_line_id=999999, inventory_position_id=position.id)


# Pure-function matrix for the order-status derivation, independent of the DB.
@pytest.mark.parametrize(
    "ordered,allocated,backordered,expected",
    [
        ((100,), (0,), (0,), "PENDING"),
        ((100,), (100,), (0,), "ALLOCATED"),
        ((100,), (0,), (100,), "BACKORDERED"),
        ((100, 50), (100, 0), (0, 50), "PARTIALLY_FULFILLED"),
    ],
)
def test_compute_order_status_matrix(ordered, allocated, backordered, expected):
    lines = [
        OrderLine(ordered_quantity=o, allocated_quantity=a, backordered_quantity=b)
        for o, a, b in zip(ordered, allocated, backordered, strict=True)
    ]
    assert compute_order_status(lines) == expected
