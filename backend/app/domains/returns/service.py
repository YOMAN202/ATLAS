"""Returns and the inspection/disposition step (FR-4.3; BR-5).

BR-5: a return decrements nothing from — and adds nothing back to —
sellable inventory until the inspection step records a disposition. Only
a SELLABLE disposition restocks inventory; QUARANTINE / SCRAP /
RETURN_TO_SUPPLIER leave sellable stock untouched, which is the point of
the inspection gate.

Atomicity: every function validates before mutating anything, so a raised
exception always means nothing was written. None of these functions call
session.commit() — the caller's session/transaction is the unit of work.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_id_by_code
from app.models import Order, OrderLine, Return, ReturnDisposition, ReturnLine, ReturnReason

_INVENTORY_RETURN_TYPE_CODE = "RETURN"
_RETURN_SOURCE_REFERENCE_TYPE = "return_line"
_SELLABLE_DISPOSITION_CODE = "SELLABLE"


def create_return(
    session: Session,
    *,
    return_number: str,
    order_id: int,
    return_date: date,
    lines: list[dict],
) -> Return:
    """Create a return with its lines, uninspected (disposition null).

    Each entry in `lines` is a dict with keys: order_line_id, line_number,
    returned_quantity, reason_code.

    Raises:
        EntityNotFoundError: the order, an order line, or a reason code
            does not exist.
        InvalidStateTransitionError: a line requests more than was ever
            allocated to the customer on the original order line.
    """

    order = session.get(Order, order_id)
    if order is None:
        raise EntityNotFoundError(f"Order {order_id} does not exist")

    # Validate every line before creating anything, so a bad line never
    # leaves a half-built Return behind.
    order_lines = []
    for line in lines:
        order_line = session.get(OrderLine, line["order_line_id"])
        if order_line is None:
            raise EntityNotFoundError(f"OrderLine {line['order_line_id']} does not exist")
        if line["returned_quantity"] > order_line.allocated_quantity:
            raise InvalidStateTransitionError(
                f"OrderLine {order_line.id}: cannot return "
                f"{line['returned_quantity']} units, only {order_line.allocated_quantity} "
                "were ever allocated to this order",
                rule="FR-4.3",
            )
        order_lines.append(order_line)

    ret = Return(return_number=return_number, order_id=order_id, return_date=return_date)
    session.add(ret)
    session.flush()

    for line, order_line in zip(lines, order_lines, strict=True):
        session.add(
            ReturnLine(
                return_id=ret.id,
                order_line_id=order_line.id,
                line_number=line["line_number"],
                returned_quantity=line["returned_quantity"],
                reason_id=get_id_by_code(session, ReturnReason, line["reason_code"]),
            )
        )
    session.flush()

    return ret


def inspect_return_line(
    session: Session,
    *,
    return_line_id: int,
    disposition_code: str,
    inspected_at: datetime,
    warehouse_zone_id: int | None = None,
) -> ReturnLine:
    """Record the inspection outcome for a return line (BR-5).

    Only a SELLABLE disposition restocks inventory — via the inventory
    module's ledger, at `warehouse_zone_id` (required in that case) in
    the same warehouse the original order line was fulfilled from.

    Raises:
        EntityNotFoundError: unknown return line or disposition code.
        InvalidStateTransitionError: this line was already inspected.
        ValueError: SELLABLE disposition given without warehouse_zone_id.
    """

    return_line = session.get(ReturnLine, return_line_id)
    if return_line is None:
        raise EntityNotFoundError(f"ReturnLine {return_line_id} does not exist")

    if return_line.disposition_id is not None:
        raise InvalidStateTransitionError(
            f"ReturnLine {return_line_id} was already inspected", rule="BR-5"
        )

    if disposition_code == _SELLABLE_DISPOSITION_CODE and warehouse_zone_id is None:
        raise ValueError("warehouse_zone_id is required to restock a SELLABLE disposition")

    disposition_id = get_id_by_code(session, ReturnDisposition, disposition_code)
    return_line.disposition_id = disposition_id
    return_line.inspected_at = inspected_at
    session.flush()

    if disposition_code == _SELLABLE_DISPOSITION_CODE:
        order_line = session.get(OrderLine, return_line.order_line_id)
        position = get_or_create_position(
            session,
            product_id=order_line.product_id,
            warehouse_id=order_line.fulfillment_warehouse_id,
            warehouse_zone_id=warehouse_zone_id,
        )
        record_transaction(
            session,
            inventory_position_id=position.id,
            transaction_type_code=_INVENTORY_RETURN_TYPE_CODE,
            quantity_delta=return_line.returned_quantity,
            occurred_at=inspected_at,
            source_reference_type=_RETURN_SOURCE_REFERENCE_TYPE,
            source_reference_id=return_line.id,
        )

    return return_line
