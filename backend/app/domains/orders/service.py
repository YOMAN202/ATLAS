"""Order creation and allocation (FR-4.1, FR-4.2; BR-2).

Allocation reserves stock against a caller-specified inventory position —
it does not search across zones/warehouses for available stock. FR-2.2
explicitly places "advanced warehouse slotting and optimization" out of
MVP scope, so which position to allocate from is the caller's decision
(Phase 3 simulation, later the API), not a bin-picking algorithm here.

Allocation reserves (`InventoryPosition.quantity_reserved`) rather than
physically picking (`quantity_on_hand`) — the physical pick happens at
dispatch time, via inventory.pick(), called by whoever creates the
shipment (Phase 3's transportation generator). `mark_line_shipped` links
a line to the shipment fulfilling it once that pick has happened; it
does not alter order status — an order-level FULFILLED status derived
from shipment completion is a future integration point, not built here.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.inventory.service import reserve
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_id_by_code
from app.models import (
    Customer,
    InventoryPosition,
    Order,
    OrderLine,
    OrderStatus,
    Region,
    Shipment,
)


def compute_order_status(lines: list[OrderLine]) -> str:
    """Pure function deriving an order's overall status from its lines'
    allocated/backordered quantities (BR-2, FR-4.2):

    - PENDING: no line has been allocated or backordered yet.
    - ALLOCATED: every line is fully allocated, nothing backordered.
    - BACKORDERED: nothing at all could be allocated across any line.
    - PARTIALLY_FULFILLED: a mix — some quantity allocated, some backordered.
    """

    total_ordered = sum(line.ordered_quantity for line in lines)
    total_allocated = sum(line.allocated_quantity for line in lines)
    total_backordered = sum(line.backordered_quantity for line in lines)

    if total_allocated == 0 and total_backordered == 0:
        return "PENDING"
    if total_backordered == 0 and total_allocated == total_ordered:
        return "ALLOCATED"
    if total_allocated == 0 and total_backordered > 0:
        return "BACKORDERED"
    return "PARTIALLY_FULFILLED"


def create_customer(
    session: Session,
    *,
    customer_code: str,
    name: str,
    region_id: int,
    email: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    city: str | None = None,
    state_province: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
) -> Customer:
    """Create a customer master record. Thin: validates the referenced
    region exists, constructs, and persists."""

    if session.get(Region, region_id) is None:
        raise EntityNotFoundError(f"Region {region_id} does not exist")

    customer = Customer(
        customer_code=customer_code,
        name=name,
        region_id=region_id,
        email=email,
        phone=phone,
        address_line1=address_line1,
        city=city,
        state_province=state_province,
        postal_code=postal_code,
        country=country,
    )
    session.add(customer)
    session.flush()

    return customer


def create_order(
    session: Session,
    *,
    order_number: str,
    customer_id: int,
    order_date: date,
    lines: list[dict],
) -> Order:
    """Create an order in PENDING status with its lines, unallocated.

    Each entry in `lines` is a dict with keys: product_id, line_number,
    ordered_quantity, unit_price, unit_cost.
    """

    order = Order(
        order_number=order_number,
        customer_id=customer_id,
        status_id=get_id_by_code(session, OrderStatus, "PENDING"),
        order_date=order_date,
    )
    session.add(order)
    session.flush()

    for line in lines:
        session.add(
            OrderLine(
                order_id=order.id,
                product_id=line["product_id"],
                line_number=line["line_number"],
                ordered_quantity=line["ordered_quantity"],
                unit_price=line["unit_price"],
                unit_cost=line["unit_cost"],
            )
        )
    session.flush()

    return order


def create_orders_bulk(session: Session, *, orders: list[dict]) -> list[Order]:
    """Batched equivalent of calling create_order() once per entry in
    `orders` (each a dict with order_number, customer_id, order_date,
    lines keys — same shape create_order() takes, just plural), in list
    order.

    Orders don't share any mutable state with each other, so — like
    create_shipments_bulk — this is a straightforward two-flush bulk
    insert (all Order rows in one flush to get their ids, then all
    OrderLine rows in a second flush) instead of one create_order() call
    per order, each with its own two flushes. Order creation was
    identified as the single largest per-day cost (~34%) in steady-state
    profiling, entirely from this previously-unbatched N+1 pattern.

    Returns the created Order objects only, in the same order as the
    input list — callers needing the created OrderLine rows (e.g. to
    allocate them) should query for them afterward, same as existing
    create_order() callers already do.
    """

    if not orders:
        return []

    pending_status_id = get_id_by_code(session, OrderStatus, "PENDING")
    new_orders = [
        Order(
            order_number=entry["order_number"],
            customer_id=entry["customer_id"],
            status_id=pending_status_id,
            order_date=entry["order_date"],
        )
        for entry in orders
    ]
    session.add_all(new_orders)
    session.flush()

    new_lines = [
        OrderLine(
            order_id=order.id,
            product_id=line["product_id"],
            line_number=line["line_number"],
            ordered_quantity=line["ordered_quantity"],
            unit_price=line["unit_price"],
            unit_cost=line["unit_cost"],
        )
        for order, entry in zip(new_orders, orders, strict=True)
        for line in entry["lines"]
    ]
    session.add_all(new_lines)
    session.flush()

    return new_orders


def allocate_order_line(
    session: Session, *, order_line_id: int, inventory_position_id: int
) -> OrderLine:
    """Allocate as much of an order line's remaining (unallocated,
    non-backordered) quantity as the given position can cover.

    BR-2: if the position cannot cover the full remaining quantity, the
    shortfall is backordered rather than raising an error — that is the
    correct rule outcome, not a failure. The order's status is
    recomputed after every allocation attempt.

    Raises:
        InvalidStateTransitionError: the line has nothing left to
            allocate (already fully allocated or already backordered in
            full), or the position's product doesn't match the line's.
    """

    line = session.get(OrderLine, order_line_id)
    if line is None:
        raise EntityNotFoundError(f"OrderLine {order_line_id} does not exist")

    remaining = line.ordered_quantity - line.allocated_quantity - line.backordered_quantity
    if remaining <= 0:
        raise InvalidStateTransitionError(
            f"OrderLine {order_line_id} has no remaining quantity to allocate "
            f"(ordered={line.ordered_quantity}, allocated={line.allocated_quantity}, "
            f"backordered={line.backordered_quantity})"
        )

    position = session.get(InventoryPosition, inventory_position_id)
    if position is None:
        raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")
    if position.product_id != line.product_id:
        raise InvalidStateTransitionError(
            f"InventoryPosition {inventory_position_id} is for product "
            f"{position.product_id}, but OrderLine {order_line_id} is for product "
            f"{line.product_id}"
        )

    available = position.quantity_on_hand - position.quantity_reserved
    can_allocate = min(available, remaining)

    if can_allocate > 0:
        reserve(session, inventory_position_id=position.id, quantity=can_allocate)
        line.allocated_quantity += can_allocate
        if line.fulfillment_warehouse_id is None:
            line.fulfillment_warehouse_id = position.warehouse_id

    shortfall = remaining - can_allocate
    if shortfall > 0:
        line.backordered_quantity += shortfall

    session.flush()

    order = session.get(Order, line.order_id)
    all_lines = (
        session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()
    )
    order.status_id = get_id_by_code(session, OrderStatus, compute_order_status(all_lines))
    session.flush()

    return line


def allocate_order_lines_bulk(session: Session, *, allocations: list[dict]) -> list[OrderLine]:
    """Batched equivalent of calling allocate_order_line() once per entry
    in `allocations` (each a dict with order_line_id, inventory_position_id
    keys), in list order — same BR-2 validation and per-line outcome, but
    with bulk reads instead of one session.get() per line/position.

    Multiple allocations targeting the same inventory position, or
    belonging to the same order, are handled with the same running-state
    semantics as calling allocate_order_line() sequentially: each
    position's available-to-reserve capacity is tracked and consumed in
    list order (so BR-2 can never be violated by a same-batch race), and
    each touched order's status is recomputed once at the end from its
    complete, fully-updated set of lines — equivalent to the sequential
    version's final recomputation for that order.

    Raises the same exceptions, for the same conditions, as
    allocate_order_line() — EntityNotFoundError for an unknown line or
    position, InvalidStateTransitionError for a line with nothing left to
    allocate or a position/line product mismatch.
    """

    if not allocations:
        return []

    line_ids = [entry["order_line_id"] for entry in allocations]
    position_ids = [entry["inventory_position_id"] for entry in allocations]

    lines_by_id = {
        line.id: line
        for line in session.execute(select(OrderLine).where(OrderLine.id.in_(line_ids)))
        .scalars()
        .all()
    }
    positions_by_id = {
        position.id: position
        for position in session.execute(
            select(InventoryPosition).where(InventoryPosition.id.in_(position_ids))
        )
        .scalars()
        .all()
    }

    # Running quantity_reserved per touched position, seeded from the
    # bulk-fetched snapshot and consumed in list order as this batch's
    # allocations are processed — mirrors reserve()'s
    # available = on_hand - reserved check, kept current in-memory instead
    # of via N separate reserve() writes.
    running_reserved: dict[int, int] = {}
    touched_order_ids: set[int] = set()
    result_lines: list[OrderLine] = []

    for entry in allocations:
        order_line_id = entry["order_line_id"]
        inventory_position_id = entry["inventory_position_id"]

        line = lines_by_id.get(order_line_id)
        if line is None:
            raise EntityNotFoundError(f"OrderLine {order_line_id} does not exist")

        remaining = line.ordered_quantity - line.allocated_quantity - line.backordered_quantity
        if remaining <= 0:
            raise InvalidStateTransitionError(
                f"OrderLine {order_line_id} has no remaining quantity to allocate "
                f"(ordered={line.ordered_quantity}, allocated={line.allocated_quantity}, "
                f"backordered={line.backordered_quantity})"
            )

        position = positions_by_id.get(inventory_position_id)
        if position is None:
            raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")
        if position.product_id != line.product_id:
            raise InvalidStateTransitionError(
                f"InventoryPosition {inventory_position_id} is for product "
                f"{position.product_id}, but OrderLine {order_line_id} is for product "
                f"{line.product_id}"
            )

        if inventory_position_id not in running_reserved:
            running_reserved[inventory_position_id] = position.quantity_reserved

        available = position.quantity_on_hand - running_reserved[inventory_position_id]
        can_allocate = min(available, remaining)

        if can_allocate > 0:
            running_reserved[inventory_position_id] += can_allocate
            line.allocated_quantity += can_allocate
            if line.fulfillment_warehouse_id is None:
                line.fulfillment_warehouse_id = position.warehouse_id

        shortfall = remaining - can_allocate
        if shortfall > 0:
            line.backordered_quantity += shortfall

        touched_order_ids.add(line.order_id)
        result_lines.append(line)

    for position_id, final_reserved in running_reserved.items():
        positions_by_id[position_id].quantity_reserved = final_reserved

    session.flush()

    all_lines_by_order: dict[int, list[OrderLine]] = {}
    for line in (
        session.execute(select(OrderLine).where(OrderLine.order_id.in_(touched_order_ids)))
        .scalars()
        .all()
    ):
        all_lines_by_order.setdefault(line.order_id, []).append(line)

    orders_by_id = {
        order.id: order
        for order in session.execute(select(Order).where(Order.id.in_(touched_order_ids)))
        .scalars()
        .all()
    }
    for order_id, order in orders_by_id.items():
        order.status_id = get_id_by_code(
            session, OrderStatus, compute_order_status(all_lines_by_order[order_id])
        )

    session.flush()
    return result_lines


def mark_line_shipped(session: Session, *, order_line_id: int, shipment_id: int) -> OrderLine:
    """Link a fully-allocated order line to the shipment fulfilling it.

    Thin: validates the line has an allocated quantity and the shipment
    exists, then sets shipment_id. Callers are expected to have already
    converted the reservation into a physical pick via inventory.pick()
    before calling this — this function does not touch inventory itself,
    and it does not alter order status (see module docstring).

    Raises:
        EntityNotFoundError: unknown order line or shipment.
        InvalidStateTransitionError: the line has no allocated quantity
            to ship.
    """

    line = session.get(OrderLine, order_line_id)
    if line is None:
        raise EntityNotFoundError(f"OrderLine {order_line_id} does not exist")

    if line.allocated_quantity <= 0:
        raise InvalidStateTransitionError(
            f"OrderLine {order_line_id} has no allocated quantity to ship"
        )

    if session.get(Shipment, shipment_id) is None:
        raise EntityNotFoundError(f"Shipment {shipment_id} does not exist")

    line.shipment_id = shipment_id
    session.flush()

    return line


def mark_lines_shipped_bulk(session: Session, *, links: list[dict]) -> list[OrderLine]:
    """Batched equivalent of calling mark_line_shipped() once per entry in
    `links` (each a dict with order_line_id, shipment_id keys), in list
    order. Each link is independent (no shared mutable state between
    entries), so this is a bulk-read-then-bulk-write, same validation and
    exceptions as the single-item version.
    """

    if not links:
        return []

    line_ids = [entry["order_line_id"] for entry in links]
    shipment_ids = [entry["shipment_id"] for entry in links]

    lines_by_id = {
        line.id: line
        for line in session.execute(select(OrderLine).where(OrderLine.id.in_(line_ids)))
        .scalars()
        .all()
    }
    existing_shipment_ids = set(
        session.execute(select(Shipment.id).where(Shipment.id.in_(shipment_ids))).scalars().all()
    )

    result_lines: list[OrderLine] = []
    for entry in links:
        order_line_id = entry["order_line_id"]
        shipment_id = entry["shipment_id"]

        line = lines_by_id.get(order_line_id)
        if line is None:
            raise EntityNotFoundError(f"OrderLine {order_line_id} does not exist")
        if line.allocated_quantity <= 0:
            raise InvalidStateTransitionError(
                f"OrderLine {order_line_id} has no allocated quantity to ship"
            )
        if shipment_id not in existing_shipment_ids:
            raise EntityNotFoundError(f"Shipment {shipment_id} does not exist")

        line.shipment_id = shipment_id
        result_lines.append(line)

    session.flush()
    return result_lines
