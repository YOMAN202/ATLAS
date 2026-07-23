import pytest

from app.domains.shared.exceptions import EntityNotFoundError, ZoneCapacityExceededError
from app.domains.warehousing.service import (
    assert_zone_capacity_available,
    create_warehouse,
    create_warehouse_zone,
    get_zone_occupied_units,
)
from app.models import InventoryPosition


def _add_position(db_session, *, product, warehouse, warehouse_zone, quantity_on_hand):
    position = InventoryPosition(
        product_id=product.id,
        warehouse_id=warehouse.id,
        warehouse_zone_id=warehouse_zone.id,
        quantity_on_hand=quantity_on_hand,
    )
    db_session.add(position)
    db_session.flush()
    return position


def test_get_zone_occupied_units_sums_positions(db_session, product, warehouse, warehouse_zone):
    _add_position(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity_on_hand=300,
    )

    assert get_zone_occupied_units(db_session, warehouse_zone.id) == 300


def test_get_zone_occupied_units_empty_zone_is_zero(db_session, warehouse_zone):
    assert get_zone_occupied_units(db_session, warehouse_zone.id) == 0


# FR-2.2: movement within remaining zone capacity is permitted.
def test_capacity_available_within_limit_does_not_raise(
    db_session, product, warehouse, warehouse_zone
):
    _add_position(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity_on_hand=900,
    )

    # zone_capacity_units is 1000 (conftest fixture); 900 occupied + 100 fits exactly.
    assert_zone_capacity_available(db_session, warehouse_zone.id, 100)


# FR-2.2: movement that would exceed the zone's modeled capacity is rejected.
def test_capacity_exceeded_raises(db_session, product, warehouse, warehouse_zone):
    _add_position(
        db_session,
        product=product,
        warehouse=warehouse,
        warehouse_zone=warehouse_zone,
        quantity_on_hand=900,
    )

    with pytest.raises(ZoneCapacityExceededError) as exc_info:
        assert_zone_capacity_available(db_session, warehouse_zone.id, 101)
    assert exc_info.value.rule == "FR-2.2"


def test_non_positive_additional_quantity_is_a_noop(db_session, warehouse_zone):
    # Freeing up space (or a zero-quantity check) can never violate capacity.
    assert_zone_capacity_available(db_session, warehouse_zone.id, 0)
    assert_zone_capacity_available(db_session, warehouse_zone.id, -50)


def test_unknown_zone_raises_not_found(db_session):
    with pytest.raises(EntityNotFoundError):
        assert_zone_capacity_available(db_session, 999999, 10)


def test_create_warehouse(db_session, region):
    warehouse = create_warehouse(
        db_session,
        warehouse_code="WH-NEW",
        name="New Warehouse",
        region_id=region.id,
        total_capacity_units=5000,
    )

    assert warehouse.id is not None
    assert warehouse.is_active is True


def test_create_warehouse_unknown_region_raises(db_session):
    with pytest.raises(EntityNotFoundError):
        create_warehouse(
            db_session,
            warehouse_code="WH-BAD",
            name="Bad Warehouse",
            region_id=999999,
            total_capacity_units=5000,
        )


def test_create_warehouse_zone(db_session, warehouse):
    zone = create_warehouse_zone(
        db_session,
        warehouse_id=warehouse.id,
        zone_code="B1",
        name="Zone B1",
        zone_capacity_units=500,
    )

    assert zone.id is not None
    assert zone.warehouse_id == warehouse.id


def test_create_warehouse_zone_unknown_warehouse_raises(db_session):
    with pytest.raises(EntityNotFoundError):
        create_warehouse_zone(
            db_session, warehouse_id=999999, zone_code="B1", name="Zone B1", zone_capacity_units=500
        )
