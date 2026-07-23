"""Purchase order lifecycle (FR-1.2, FR-1.3; BR-1).

Lifecycle: DRAFT -> SUBMITTED -> CONFIRMED -> FULFILLED -> CLOSED.

BR-1: a PO cannot be marked fulfilled until every line's received quantity
matches its ordered quantity within PO_RECEIPT_TOLERANCE. Only *accepted*
quantity (received minus quality-rejected) enters sellable inventory —
rejected units are tracked for FR-1.3's quality-rejection-rate metric but
never added to on-hand stock.

Atomicity: every function validates before mutating anything, so a raised
exception always means nothing was written. None of these functions call
session.commit() — the caller's session/transaction is the unit of work.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.inventory.service import get_or_create_position, record_transaction
from app.domains.shared.exceptions import (
    EntityNotFoundError,
    InvalidStateTransitionError,
    ReceiptToleranceExceededError,
)
from app.domains.shared.lookups import get_code_by_id, get_id_by_code
from app.models import POStatus, PurchaseOrder, PurchaseOrderLine

# BR-1's "approved tolerance" is not a numeric value in any frozen document.
# 2% under-receipt is a standard procurement shortage allowance, confirmed
# with the project owner in the Phase 2 review gate (2026-07-24). Change
# only through the same review process, not by editing this constant ad hoc.
PO_RECEIPT_TOLERANCE = Decimal("0.02")

_INVENTORY_RECEIPT_TYPE_CODE = "RECEIPT"
_PO_SOURCE_REFERENCE_TYPE = "purchase_order_line"


def _lines_within_tolerance(session: Session, purchase_order_id: int) -> bool:
    lines = (
        session.execute(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == purchase_order_id
            )
        )
        .scalars()
        .all()
    )
    return all(
        line.received_quantity >= line.ordered_quantity * (1 - PO_RECEIPT_TOLERANCE)
        for line in lines
    )


def create_purchase_order(
    session: Session,
    *,
    po_number: str,
    supplier_id: int,
    warehouse_id: int,
    order_date: date,
    lines: list[dict],
    expected_delivery_date: date | None = None,
) -> PurchaseOrder:
    """Create a PO in DRAFT status with its lines.

    Each entry in `lines` is a dict with keys: product_id, line_number,
    ordered_quantity, unit_cost, and optionally expected_delivery_date.
    """

    po = PurchaseOrder(
        po_number=po_number,
        supplier_id=supplier_id,
        warehouse_id=warehouse_id,
        status_id=get_id_by_code(session, POStatus, "DRAFT"),
        order_date=order_date,
        expected_delivery_date=expected_delivery_date,
    )
    session.add(po)
    session.flush()

    for line in lines:
        session.add(
            PurchaseOrderLine(
                purchase_order_id=po.id,
                product_id=line["product_id"],
                line_number=line["line_number"],
                ordered_quantity=line["ordered_quantity"],
                unit_cost=line["unit_cost"],
                expected_delivery_date=line.get("expected_delivery_date"),
            )
        )
    session.flush()

    return po


def submit_purchase_order(session: Session, purchase_order_id: int) -> PurchaseOrder:
    """DRAFT -> SUBMITTED."""

    return _transition(session, purchase_order_id, from_code="DRAFT", to_code="SUBMITTED")


def confirm_purchase_order(session: Session, purchase_order_id: int) -> PurchaseOrder:
    """SUBMITTED -> CONFIRMED."""

    return _transition(session, purchase_order_id, from_code="SUBMITTED", to_code="CONFIRMED")


def _transition(
    session: Session, purchase_order_id: int, *, from_code: str, to_code: str
) -> PurchaseOrder:
    po = session.get(PurchaseOrder, purchase_order_id)
    if po is None:
        raise EntityNotFoundError(f"PurchaseOrder {purchase_order_id} does not exist")

    current_code = get_code_by_id(session, POStatus, po.status_id)
    if current_code != from_code:
        raise InvalidStateTransitionError(
            f"PurchaseOrder {purchase_order_id} is '{current_code}', cannot move to "
            f"'{to_code}' (requires '{from_code}')"
        )

    po.status_id = get_id_by_code(session, POStatus, to_code)
    session.flush()

    return po


def receive_purchase_order_line(
    session: Session,
    *,
    po_line_id: int,
    received_quantity: int,
    quality_rejected_quantity: int,
    delivery_date: date,
    warehouse_zone_id: int,
    occurred_at: datetime,
) -> PurchaseOrderLine:
    """Record a (possibly partial) receipt against a PO line.

    Only the accepted quantity (received minus quality-rejected) is added
    to sellable inventory via the inventory module's ledger. If, after
    this receipt, every line on the PO is within PO_RECEIPT_TOLERANCE, the
    PO auto-advances CONFIRMED -> FULFILLED (BR-1) — no exception on the
    normal path; most individual receipts simply won't complete the PO
    yet, which is not an error.

    Raises:
        InvalidStateTransitionError: the PO is not CONFIRMED (out of
            sequence — must be confirmed before it can be received against).
    """

    if received_quantity < 0 or quality_rejected_quantity < 0:
        raise ValueError("received_quantity and quality_rejected_quantity must be >= 0")
    if quality_rejected_quantity > received_quantity:
        raise ValueError("quality_rejected_quantity cannot exceed received_quantity")

    line = session.get(PurchaseOrderLine, po_line_id)
    if line is None:
        raise EntityNotFoundError(f"PurchaseOrderLine {po_line_id} does not exist")

    po = session.get(PurchaseOrder, line.purchase_order_id)
    current_code = get_code_by_id(session, POStatus, po.status_id)
    if current_code != "CONFIRMED":
        raise InvalidStateTransitionError(
            f"PurchaseOrder {po.id} is '{current_code}', cannot receive against it "
            "(requires 'CONFIRMED')"
        )

    accepted_quantity = received_quantity - quality_rejected_quantity
    if accepted_quantity > 0:
        position = get_or_create_position(
            session,
            product_id=line.product_id,
            warehouse_id=po.warehouse_id,
            warehouse_zone_id=warehouse_zone_id,
        )
        record_transaction(
            session,
            inventory_position_id=position.id,
            transaction_type_code=_INVENTORY_RECEIPT_TYPE_CODE,
            quantity_delta=accepted_quantity,
            occurred_at=occurred_at,
            source_reference_type=_PO_SOURCE_REFERENCE_TYPE,
            source_reference_id=line.id,
        )

    line.received_quantity += received_quantity
    line.quality_rejected_quantity += quality_rejected_quantity
    line.actual_delivery_date = delivery_date
    session.flush()

    if _lines_within_tolerance(session, po.id):
        po.status_id = get_id_by_code(session, POStatus, "FULFILLED")
        session.flush()

    return line


def mark_purchase_order_fulfilled(session: Session, purchase_order_id: int) -> PurchaseOrder:
    """Explicitly attempt CONFIRMED -> FULFILLED.

    Raises:
        ReceiptToleranceExceededError: BR-1 — one or more lines are not
            yet within PO_RECEIPT_TOLERANCE.
    """

    po = session.get(PurchaseOrder, purchase_order_id)
    if po is None:
        raise EntityNotFoundError(f"PurchaseOrder {purchase_order_id} does not exist")

    current_code = get_code_by_id(session, POStatus, po.status_id)
    if current_code != "CONFIRMED":
        raise InvalidStateTransitionError(
            f"PurchaseOrder {purchase_order_id} is '{current_code}', cannot mark "
            "fulfilled (requires 'CONFIRMED')"
        )

    if not _lines_within_tolerance(session, purchase_order_id):
        raise ReceiptToleranceExceededError(
            f"PurchaseOrder {purchase_order_id} has lines outside the "
            f"{PO_RECEIPT_TOLERANCE:.0%} receipt tolerance",
            rule="BR-1",
        )

    po.status_id = get_id_by_code(session, POStatus, "FULFILLED")
    session.flush()

    return po


def close_purchase_order(session: Session, purchase_order_id: int) -> PurchaseOrder:
    """FULFILLED -> CLOSED."""

    return _transition(session, purchase_order_id, from_code="FULFILLED", to_code="CLOSED")
