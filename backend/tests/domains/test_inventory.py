from datetime import datetime

import pytest

from app.domains.inventory.service import (
    get_or_create_position,
    record_transaction,
    release_reservation,
    reserve,
)
from app.domains.shared.exceptions import (
    EntityNotFoundError,
    InsufficientInventoryError,
    ZoneCapacityExceededError,
)
from app.models import InventoryPosition

NOW = datetime(2026, 1, 15, 9, 0, 0)


@pytest.fixture
def position(db_session, product, warehouse, warehouse_zone):
    return get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )


def test_get_or_create_position_creates_once(db_session, product, warehouse, warehouse_zone):
    first = get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )
    second = get_or_create_position(
        db_session,
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
    )

    assert first.id == second.id
    assert first.quantity_on_hand == 0
    assert first.quantity_reserved == 0


# BR-2: a receipt increases on-hand stock.
def test_record_transaction_receipt_increases_on_hand(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )

    db_session.flush()
    reloaded = db_session.get(InventoryPosition, position.id)
    assert reloaded.quantity_on_hand == 50


# BR-2: a pick decreases on-hand stock.
def test_record_transaction_pick_decreases_on_hand(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="PICK",
        quantity_delta=-20,
        occurred_at=NOW,
    )

    reloaded = db_session.get(InventoryPosition, position.id)
    assert reloaded.quantity_on_hand == 30


# BR-2: inventory cannot go negative.
def test_record_transaction_rejects_negative_result(db_session, position, lookups):
    with pytest.raises(InsufficientInventoryError) as exc_info:
        record_transaction(
            db_session,
            inventory_position_id=position.id,
            transaction_type_code="PICK",
            quantity_delta=-1,
            occurred_at=NOW,
        )
    assert exc_info.value.rule == "BR-2"

    # The rejected movement must not have partially applied.
    reloaded = db_session.get(InventoryPosition, position.id)
    assert reloaded.quantity_on_hand == 0


# FR-2.2: a receipt that would exceed the zone's modeled capacity is rejected.
def test_record_transaction_rejects_zone_capacity_exceeded(db_session, position, lookups):
    with pytest.raises(ZoneCapacityExceededError):
        record_transaction(
            db_session,
            inventory_position_id=position.id,
            transaction_type_code="RECEIPT",
            quantity_delta=1001,  # zone_capacity_units is 1000 (conftest fixture)
            occurred_at=NOW,
        )


def test_record_transaction_unknown_position_raises(db_session, lookups):
    with pytest.raises(EntityNotFoundError):
        record_transaction(
            db_session,
            inventory_position_id=999999,
            transaction_type_code="RECEIPT",
            quantity_delta=10,
            occurred_at=NOW,
        )


def test_record_transaction_unknown_type_code_raises(db_session, position, lookups):
    with pytest.raises(EntityNotFoundError):
        record_transaction(
            db_session,
            inventory_position_id=position.id,
            transaction_type_code="NOT_A_TYPE",
            quantity_delta=10,
            occurred_at=NOW,
        )


def test_reserve_within_available_succeeds(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )

    reserve(db_session, inventory_position_id=position.id, quantity=30)

    reloaded = db_session.get(InventoryPosition, position.id)
    assert reloaded.quantity_reserved == 30


# BR-2: cannot reserve more than is actually available (on hand minus already reserved).
def test_reserve_beyond_available_raises(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=10,
        occurred_at=NOW,
    )

    with pytest.raises(InsufficientInventoryError):
        reserve(db_session, inventory_position_id=position.id, quantity=11)


def test_reserve_non_positive_quantity_raises(db_session, position):
    with pytest.raises(ValueError):
        reserve(db_session, inventory_position_id=position.id, quantity=0)


def test_release_reservation_succeeds(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )
    reserve(db_session, inventory_position_id=position.id, quantity=30)

    release_reservation(db_session, inventory_position_id=position.id, quantity=10)

    reloaded = db_session.get(InventoryPosition, position.id)
    assert reloaded.quantity_reserved == 20


def test_release_reservation_beyond_reserved_raises(db_session, position, lookups):
    record_transaction(
        db_session,
        inventory_position_id=position.id,
        transaction_type_code="RECEIPT",
        quantity_delta=50,
        occurred_at=NOW,
    )
    reserve(db_session, inventory_position_id=position.id, quantity=10)

    with pytest.raises(InsufficientInventoryError):
        release_reservation(db_session, inventory_position_id=position.id, quantity=11)
