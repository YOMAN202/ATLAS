"""Order creation and allocation (FR-4.1, FR-4.2; BR-2).

Allocation reserves stock against a caller-specified inventory position —
it does not search across zones/warehouses for available stock. FR-2.2
explicitly places "advanced warehouse slotting and optimization" out of
MVP scope, so which position to allocate from is the caller's decision
(Phase 3 simulation, later the API), not a bin-picking algorithm here.

Allocation reserves (`InventoryPosition.quantity_reserved`) rather than
physically picking (`quantity_on_hand`). Nothing in the Roadmap's Phase 2
deliverable list names order-to-shipment integration as in scope, and
order_lines.shipment_id stays null until a later phase wires shipping —
so the physical pick (decrementing on-hand, a ledger PICK transaction)
is intentionally left for whichever phase builds that dispatch flow, not
invented here.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.inventory.service import reserve
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_id_by_code
from app.models import InventoryPosition, Order, OrderLine, OrderStatus


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
