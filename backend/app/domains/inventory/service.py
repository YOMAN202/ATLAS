"""Inventory transactions and positions (FR-2.1, FR-2.2, FR-2.4; BR-2).

`record_transaction` is the single entry point for every physical stock
movement (receipt, pick, transfer, adjustment, return-in) — the one place
BR-2's non-negative guarantee and FR-2.2's zone-capacity check are
enforced, so no caller can duplicate or bypass either check.

`reserve`/`release_reservation` manage `quantity_reserved` — a soft hold
against open orders (FR-4.2) that has not yet physically moved. Reserving
does not append to the transaction ledger, because nothing physically
moved yet; only `record_transaction` does. Whether/when a reservation
becomes a physical pick (decrementing on-hand) is intentionally left to
the caller — Phase 2 does not wire orders through to shipment dispatch
(that integration isn't a named Phase 2 deliverable); see orders/service.py.

Atomicity: every function validates before mutating anything, so a raised
exception always means nothing was written. None of these functions call
session.commit() — the caller's session/transaction is the unit of work,
and per Master Prompt §6 (dependency-injected sessions), the caller must
roll back the session if any exception propagates from here, exactly as
tests/conftest.py's db_session fixture and a future request-scoped DB
session both already do.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.shared.exceptions import EntityNotFoundError, InsufficientInventoryError
from app.domains.warehousing.service import assert_zone_capacity_available
from app.models import InventoryPosition, InventoryTransaction, InventoryTransactionType


def get_or_create_position(
    session: Session, *, product_id: int, warehouse_id: int, warehouse_zone_id: int
) -> InventoryPosition:
    """Return the position for this product x warehouse x zone, creating
    an empty one (0 on hand, 0 reserved) if it doesn't exist yet."""

    position = session.execute(
        select(InventoryPosition).where(
            InventoryPosition.product_id == product_id,
            InventoryPosition.warehouse_id == warehouse_id,
            InventoryPosition.warehouse_zone_id == warehouse_zone_id,
        )
    ).scalar_one_or_none()

    if position is None:
        position = InventoryPosition(
            product_id=product_id,
            warehouse_id=warehouse_id,
            warehouse_zone_id=warehouse_zone_id,
            quantity_on_hand=0,
            quantity_reserved=0,
        )
        session.add(position)
        session.flush()

    return position


def record_transaction(
    session: Session,
    *,
    inventory_position_id: int,
    transaction_type_code: str,
    quantity_delta: int,
    occurred_at: datetime,
    source_reference_type: str | None = None,
    source_reference_id: int | None = None,
) -> InventoryTransaction:
    """Apply a physical stock movement to a position and append it to the
    ledger.

    quantity_delta is positive for receipt/return-in, negative for
    pick/adjustment-out; a transfer is two calls (a negative at the
    source position, a positive at the destination).

    Raises:
        EntityNotFoundError: unknown position or transaction type code.
        InsufficientInventoryError: BR-2 — the movement would drive
            quantity_on_hand negative.
        ZoneCapacityExceededError: FR-2.2 — the movement would exceed the
            position's zone capacity.
    """

    position = session.get(InventoryPosition, inventory_position_id)
    if position is None:
        raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")

    transaction_type = session.execute(
        select(InventoryTransactionType).where(
            InventoryTransactionType.code == transaction_type_code
        )
    ).scalar_one_or_none()
    if transaction_type is None:
        raise EntityNotFoundError(
            f"InventoryTransactionType '{transaction_type_code}' does not exist"
        )

    new_quantity = position.quantity_on_hand + quantity_delta
    if new_quantity < 0:
        raise InsufficientInventoryError(
            f"Position {position.id}: {position.quantity_on_hand} on hand, "
            f"{quantity_delta} requested would go negative",
            rule="BR-2",
        )

    if quantity_delta > 0:
        assert_zone_capacity_available(session, position.warehouse_zone_id, quantity_delta)

    position.quantity_on_hand = new_quantity
    transaction = InventoryTransaction(
        inventory_position_id=position.id,
        transaction_type_id=transaction_type.id,
        quantity_delta=quantity_delta,
        occurred_at=occurred_at,
        source_reference_type=source_reference_type,
        source_reference_id=source_reference_id,
    )
    session.add(transaction)
    session.flush()

    return transaction


def reserve(session: Session, *, inventory_position_id: int, quantity: int) -> InventoryPosition:
    """Soft-hold `quantity` units of on-hand stock against an open order
    (FR-4.2). Raises InsufficientInventoryError (BR-2) if it would reserve
    more than is actually available (on hand minus already reserved).
    """

    if quantity <= 0:
        raise ValueError("quantity must be positive")

    position = session.get(InventoryPosition, inventory_position_id)
    if position is None:
        raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")

    available = position.quantity_on_hand - position.quantity_reserved
    if quantity > available:
        raise InsufficientInventoryError(
            f"Position {position.id}: {available} available to reserve, {quantity} requested",
            rule="BR-2",
        )

    position.quantity_reserved += quantity
    session.flush()

    return position


def release_reservation(
    session: Session, *, inventory_position_id: int, quantity: int
) -> InventoryPosition:
    """Release a previously reserved quantity back to available stock
    (e.g. an order line cancellation in a later phase)."""

    if quantity <= 0:
        raise ValueError("quantity must be positive")

    position = session.get(InventoryPosition, inventory_position_id)
    if position is None:
        raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")

    if quantity > position.quantity_reserved:
        raise InsufficientInventoryError(
            f"Position {position.id}: only {position.quantity_reserved} reserved, "
            f"cannot release {quantity}",
            rule="BR-2",
        )

    position.quantity_reserved -= quantity
    session.flush()

    return position
