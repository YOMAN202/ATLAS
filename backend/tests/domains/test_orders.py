from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.orders.service import (
    allocate_order_line,
    allocate_order_lines_bulk,
    compute_order_status,
    create_customer,
    create_order,
    mark_line_shipped,
    mark_lines_shipped_bulk,
)
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_code_by_id
from app.domains.transportation.service import create_carrier, create_shipment
from app.models import OrderLine, OrderStatus, Product, VehicleType

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


def test_create_customer(db_session, region):
    customer = create_customer(
        db_session, customer_code="CUST-NEW", name="New Customer", region_id=region.id
    )

    assert customer.id is not None
    assert customer.region_id == region.id


def test_create_customer_unknown_region_raises(db_session):
    with pytest.raises(EntityNotFoundError):
        create_customer(db_session, customer_code="CUST-BAD", name="Bad Customer", region_id=999999)


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


def test_allocate_order_lines_bulk_empty_list_returns_empty(db_session):
    assert allocate_order_lines_bulk(db_session, allocations=[]) == []


def test_allocate_order_lines_bulk_matches_single_line_behavior(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session, product=product, warehouse=warehouse, warehouse_zone=warehouse_zone, quantity=40
    )
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    result = allocate_order_lines_bulk(
        db_session, allocations=[{"order_line_id": line.id, "inventory_position_id": position.id}]
    )

    assert len(result) == 1
    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.allocated_quantity == 40
    assert reloaded.backordered_quantity == 60
    assert reloaded.fulfillment_warehouse_id == warehouse.id
    assert _status_code(db_session, pending_order) == "PARTIALLY_FULFILLED"


# BR-2 correctness under batching: two order lines (from two different
# orders) competing for the same position, in one bulk call, must consume
# the position's available capacity cumulatively — never allocate more in
# total than the position actually has, matching what two sequential
# allocate_order_line() calls would do.
def test_allocate_order_lines_bulk_shared_position_never_over_allocates(
    db_session, customer, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session, product=product, warehouse=warehouse, warehouse_zone=warehouse_zone, quantity=60
    )
    order_a = create_order(
        db_session,
        order_number="ORD-BULK-A",
        customer_id=customer.id,
        order_date=date(2026, 1, 15),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 50,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            }
        ],
    )
    order_b = create_order(
        db_session,
        order_number="ORD-BULK-B",
        customer_id=customer.id,
        order_date=date(2026, 1, 15),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 50,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            }
        ],
    )
    line_a = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == order_a.id)
    ).scalar_one()
    line_b = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == order_b.id)
    ).scalar_one()

    allocate_order_lines_bulk(
        db_session,
        allocations=[
            {"order_line_id": line_a.id, "inventory_position_id": position.id},
            {"order_line_id": line_b.id, "inventory_position_id": position.id},
        ],
    )

    reloaded_a = db_session.get(OrderLine, line_a.id)
    reloaded_b = db_session.get(OrderLine, line_b.id)
    reloaded_position = db_session.get(type(position), position.id)

    # First-in-list gets priority (same as calling allocate_order_line()
    # for A then B sequentially would): A fully allocated, B gets the
    # remaining 10 and backorders the rest.
    assert reloaded_a.allocated_quantity == 50
    assert reloaded_b.allocated_quantity == 10
    assert reloaded_b.backordered_quantity == 40
    assert reloaded_position.quantity_reserved == 60
    assert reloaded_position.quantity_reserved <= reloaded_position.quantity_on_hand


def test_allocate_order_lines_bulk_recomputes_status_for_multi_line_order(
    db_session, customer, warehouse, warehouse_zone, product, product2, lookups
):
    position1 = _stock(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity=100,
    )
    position2 = _stock(
        db_session,
        product=product2,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity=100,
    )
    order = create_order(
        db_session,
        order_number="ORD-BULK-MULTI",
        customer_id=customer.id,
        order_date=date(2026, 1, 15),
        lines=[
            {
                "product_id": product.id,
                "line_number": 1,
                "ordered_quantity": 10,
                "unit_price": Decimal("19.99"),
                "unit_cost": Decimal("10.00"),
            },
            {
                "product_id": product2.id,
                "line_number": 2,
                "ordered_quantity": 10,
                "unit_price": Decimal("9.99"),
                "unit_cost": Decimal("3.00"),
            },
        ],
    )
    lines = (
        db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()
    )
    line1 = next(line_item for line_item in lines if line_item.product_id == product.id)
    line2 = next(line_item for line_item in lines if line_item.product_id == product2.id)

    allocate_order_lines_bulk(
        db_session,
        allocations=[
            {"order_line_id": line1.id, "inventory_position_id": position1.id},
            {"order_line_id": line2.id, "inventory_position_id": position2.id},
        ],
    )

    assert _status_code(db_session, order) == "ALLOCATED"


def test_allocate_order_lines_bulk_unknown_line_raises(
    db_session, warehouse, warehouse_zone, product, lookups
):
    position = _stock(
        db_session, product=product, warehouse=warehouse, warehouse_zone=warehouse_zone, quantity=10
    )
    with pytest.raises(EntityNotFoundError):
        allocate_order_lines_bulk(
            db_session,
            allocations=[{"order_line_id": 999999, "inventory_position_id": position.id}],
        )


def test_allocate_order_lines_bulk_product_mismatch_raises(
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
        allocate_order_lines_bulk(
            db_session,
            allocations=[
                {"order_line_id": line.id, "inventory_position_id": mismatched_position.id}
            ],
        )


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


@pytest.fixture
def shipment(db_session, warehouse, customer, lookups):
    vehicle_type = db_session.execute(
        select(VehicleType).where(VehicleType.code == "VAN")
    ).scalar_one()
    carrier = create_carrier(
        db_session,
        carrier_code="CARR-ORD-TEST",
        name="Test Carrier",
        vehicle_type_id=vehicle_type.id,
    )
    return create_shipment(
        db_session,
        shipment_number="SHIP-ORD-TEST",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )


# Dispatch: linking a fully-allocated line to the shipment fulfilling it.
def test_mark_line_shipped(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups, shipment
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

    mark_line_shipped(db_session, order_line_id=line.id, shipment_id=shipment.id)

    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.shipment_id == shipment.id


def test_mark_line_shipped_unallocated_line_raises(db_session, pending_order, shipment, lookups):
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    with pytest.raises(InvalidStateTransitionError):
        mark_line_shipped(db_session, order_line_id=line.id, shipment_id=shipment.id)


def test_mark_line_shipped_unknown_shipment_raises(
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

    with pytest.raises(EntityNotFoundError):
        mark_line_shipped(db_session, order_line_id=line.id, shipment_id=999999)


def test_mark_line_shipped_unknown_line_raises(db_session, shipment, lookups):
    with pytest.raises(EntityNotFoundError):
        mark_line_shipped(db_session, order_line_id=999999, shipment_id=shipment.id)


def test_mark_lines_shipped_bulk_empty_list_returns_empty(db_session):
    assert mark_lines_shipped_bulk(db_session, links=[]) == []


def test_mark_lines_shipped_bulk_matches_single_line_behavior(
    db_session, pending_order, warehouse, warehouse_zone, product, lookups, shipment
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

    result = mark_lines_shipped_bulk(
        db_session, links=[{"order_line_id": line.id, "shipment_id": shipment.id}]
    )

    assert len(result) == 1
    reloaded = db_session.get(OrderLine, line.id)
    assert reloaded.shipment_id == shipment.id


def test_mark_lines_shipped_bulk_unallocated_line_raises(
    db_session, pending_order, shipment, lookups
):
    line = db_session.execute(
        select(OrderLine).where(OrderLine.order_id == pending_order.id)
    ).scalar_one()

    with pytest.raises(InvalidStateTransitionError):
        mark_lines_shipped_bulk(
            db_session, links=[{"order_line_id": line.id, "shipment_id": shipment.id}]
        )


def test_mark_lines_shipped_bulk_unknown_shipment_raises(
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

    with pytest.raises(EntityNotFoundError):
        mark_lines_shipped_bulk(
            db_session, links=[{"order_line_id": line.id, "shipment_id": 999999}]
        )


def test_mark_lines_shipped_bulk_unknown_line_raises(db_session, shipment, lookups):
    with pytest.raises(EntityNotFoundError):
        mark_lines_shipped_bulk(
            db_session, links=[{"order_line_id": 999999, "shipment_id": shipment.id}]
        )
