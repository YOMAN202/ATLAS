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
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.shared.exceptions import EntityNotFoundError, InsufficientInventoryError
from app.domains.warehousing.service import assert_zone_capacity_available
from app.models import InventoryPosition, InventoryTransaction, InventoryTransactionType, Product


def create_product(
    session: Session,
    *,
    sku: str,
    name: str,
    unit_cost: Decimal,
    unit_price: Decimal,
    category: str | None = None,
    unit_of_measure: str = "EA",
    is_active: bool = True,
) -> Product:
    """Create a product master record. Thin: validates nothing beyond
    what the caller provides (no BR- rule governs product pricing at
    creation time) — constructs and persists."""

    product = Product(
        sku=sku,
        name=name,
        unit_cost=unit_cost,
        unit_price=unit_price,
        category=category,
        unit_of_measure=unit_of_measure,
        is_active=is_active,
    )
    session.add(product)
    session.flush()

    return product


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


def pick(
    session: Session,
    *,
    inventory_position_id: int,
    quantity: int,
    occurred_at: datetime,
    source_reference_type: str | None = None,
    source_reference_id: int | None = None,
) -> InventoryPosition:
    """Convert a reservation into a physical pick: the point at which a
    soft-held reservation (FR-4.2) becomes an actual, physically-moved
    unit. Decrements quantity_reserved and, via record_transaction,
    quantity_on_hand together (a PICK ledger transaction).

    Raises:
        EntityNotFoundError: unknown position.
        InsufficientInventoryError: BR-2 — attempting to pick more than
            is currently reserved at this position.
    """

    if quantity <= 0:
        raise ValueError("quantity must be positive")

    position = session.get(InventoryPosition, inventory_position_id)
    if position is None:
        raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")

    if quantity > position.quantity_reserved:
        raise InsufficientInventoryError(
            f"Position {position.id}: only {position.quantity_reserved} reserved, "
            f"cannot pick {quantity}",
            rule="BR-2",
        )

    record_transaction(
        session,
        inventory_position_id=inventory_position_id,
        transaction_type_code="PICK",
        quantity_delta=-quantity,
        occurred_at=occurred_at,
        source_reference_type=source_reference_type,
        source_reference_id=source_reference_id,
    )
    position.quantity_reserved -= quantity
    session.flush()

    return position


def pick_bulk(session: Session, *, picks: list[dict]) -> list[InventoryPosition]:
    """Batched equivalent of calling pick() once per entry in `picks`
    (each a dict with inventory_position_id, quantity, occurred_at, and
    optional source_reference_type/source_reference_id), in list order.

    Same BR-2 outcome per pick, including under same-batch contention:
    multiple picks targeting the same position consume a running
    in-memory quantity_reserved/quantity_on_hand tracker in list order
    (same pattern as orders.allocate_order_lines_bulk), so this can never
    allow an over-pick a same-batch race could otherwise hide.

    Raises:
        EntityNotFoundError: unknown position.
        InsufficientInventoryError: BR-2 — a pick would exceed what's
            currently reserved at that position (evaluated against the
            running, in-batch reserved total, not just the initial one).
    """

    if not picks:
        return []

    position_ids = [entry["inventory_position_id"] for entry in picks]
    positions_by_id = {
        position.id: position
        for position in session.execute(
            select(InventoryPosition).where(InventoryPosition.id.in_(position_ids))
        )
        .scalars()
        .all()
    }

    pick_transaction_type = session.execute(
        select(InventoryTransactionType).where(InventoryTransactionType.code == "PICK")
    ).scalar_one_or_none()
    if pick_transaction_type is None:
        raise EntityNotFoundError("InventoryTransactionType 'PICK' does not exist")

    running_reserved: dict[int, int] = {}
    running_on_hand: dict[int, int] = {}
    new_transactions: list[InventoryTransaction] = []

    for entry in picks:
        inventory_position_id = entry["inventory_position_id"]
        quantity = entry["quantity"]
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        position = positions_by_id.get(inventory_position_id)
        if position is None:
            raise EntityNotFoundError(f"InventoryPosition {inventory_position_id} does not exist")

        if inventory_position_id not in running_reserved:
            running_reserved[inventory_position_id] = position.quantity_reserved
            running_on_hand[inventory_position_id] = position.quantity_on_hand

        if quantity > running_reserved[inventory_position_id]:
            raise InsufficientInventoryError(
                f"Position {position.id}: only "
                f"{running_reserved[inventory_position_id]} reserved, cannot pick {quantity}",
                rule="BR-2",
            )

        running_reserved[inventory_position_id] -= quantity
        running_on_hand[inventory_position_id] -= quantity

        new_transactions.append(
            InventoryTransaction(
                inventory_position_id=inventory_position_id,
                transaction_type_id=pick_transaction_type.id,
                quantity_delta=-quantity,
                occurred_at=entry["occurred_at"],
                source_reference_type=entry.get("source_reference_type"),
                source_reference_id=entry.get("source_reference_id"),
            )
        )

    for position_id, position in positions_by_id.items():
        if position_id in running_reserved:
            position.quantity_reserved = running_reserved[position_id]
            position.quantity_on_hand = running_on_hand[position_id]

    session.add_all(new_transactions)
    session.flush()

    return [positions_by_id[entry["inventory_position_id"]] for entry in picks]


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
