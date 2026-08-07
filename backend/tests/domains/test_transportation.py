from datetime import datetime

import pytest
from sqlalchemy import select

from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_code_by_id
from app.domains.transportation.service import (
    advance_shipment_status,
    create_carrier,
    create_shipment,
    create_shipments_bulk,
)
from app.models import Shipment, ShipmentStatus, VehicleType, Warehouse

NOW = datetime(2026, 1, 15, 9, 0, 0)


@pytest.fixture
def carrier(db_session, lookups):
    vehicle_type = db_session.execute(
        select(VehicleType).where(VehicleType.code == "VAN")
    ).scalar_one()
    return create_carrier(
        db_session, carrier_code="CARR-1", name="Test Carrier", vehicle_type_id=vehicle_type.id
    )


def test_create_carrier_unknown_vehicle_type_raises(db_session, lookups):
    with pytest.raises(EntityNotFoundError):
        create_carrier(
            db_session, carrier_code="CARR-BAD", name="Bad Carrier", vehicle_type_id=999999
        )


@pytest.fixture
def destination_warehouse(db_session, region):
    warehouse = Warehouse(
        warehouse_code="WH-DEST",
        name="Destination Warehouse",
        region_id=region.id,
        total_capacity_units=5000,
    )
    db_session.add(warehouse)
    db_session.flush()
    return warehouse


def _status_code(db_session, shipment):
    return get_code_by_id(db_session, ShipmentStatus, shipment.status_id)


def test_create_shipment_to_customer_starts_created(
    db_session, carrier, warehouse, customer, lookups
):
    shipment = create_shipment(
        db_session,
        shipment_number="SHIP-1001",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )

    assert _status_code(db_session, shipment) == "CREATED"


def test_create_shipment_requires_exactly_one_destination(
    db_session, carrier, warehouse, customer, destination_warehouse, lookups
):
    with pytest.raises(ValueError):
        create_shipment(
            db_session,
            shipment_number="SHIP-BOTH",
            carrier_id=carrier.id,
            origin_warehouse_id=warehouse.id,
            destination_customer_id=customer.id,
            destination_warehouse_id=destination_warehouse.id,
            occurred_at=NOW,
        )

    with pytest.raises(ValueError):
        create_shipment(
            db_session,
            shipment_number="SHIP-NEITHER",
            carrier_id=carrier.id,
            origin_warehouse_id=warehouse.id,
            occurred_at=NOW,
        )


def test_create_shipments_bulk_empty_list_returns_empty(db_session):
    assert create_shipments_bulk(db_session, shipments=[]) == []


def test_create_shipments_bulk_matches_single_shipment_behavior(
    db_session, carrier, warehouse, customer, lookups
):
    shipments = create_shipments_bulk(
        db_session,
        shipments=[
            {
                "shipment_number": "SHIP-BULK-1",
                "carrier_id": carrier.id,
                "origin_warehouse_id": warehouse.id,
                "destination_customer_id": customer.id,
                "occurred_at": NOW,
            }
        ],
    )

    assert len(shipments) == 1
    assert _status_code(db_session, shipments[0]) == "CREATED"


def test_create_shipments_bulk_creates_all_in_order(
    db_session, carrier, warehouse, customer, lookups
):
    shipments = create_shipments_bulk(
        db_session,
        shipments=[
            {
                "shipment_number": f"SHIP-BULK-{i}",
                "carrier_id": carrier.id,
                "origin_warehouse_id": warehouse.id,
                "destination_customer_id": customer.id,
                "occurred_at": NOW,
            }
            for i in range(5)
        ],
    )

    assert len(shipments) == 5
    assert [s.shipment_number for s in shipments] == [f"SHIP-BULK-{i}" for i in range(5)]
    assert all(_status_code(db_session, s) == "CREATED" for s in shipments)


def test_create_shipments_bulk_requires_exactly_one_destination(
    db_session, carrier, warehouse, customer, lookups
):
    with pytest.raises(ValueError):
        create_shipments_bulk(
            db_session,
            shipments=[
                {
                    "shipment_number": "SHIP-BULK-BAD",
                    "carrier_id": carrier.id,
                    "origin_warehouse_id": warehouse.id,
                    "occurred_at": NOW,
                }
            ],
        )


def test_transfer_shipment_between_warehouses(
    db_session, carrier, warehouse, destination_warehouse, lookups
):
    shipment = create_shipment(
        db_session,
        shipment_number="SHIP-TRANSFER",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_warehouse_id=destination_warehouse.id,
        occurred_at=NOW,
    )

    assert _status_code(db_session, shipment) == "CREATED"


# FR-3.3: the full happy-path lifecycle, ending with actual_delivery_date set.
def test_advance_full_lifecycle_to_delivered(db_session, carrier, warehouse, customer, lookups):
    shipment = create_shipment(
        db_session,
        shipment_number="SHIP-1002",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )

    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="PICKED", occurred_at=NOW
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="IN_TRANSIT", occurred_at=NOW
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="DELIVERED", occurred_at=NOW
    )

    reloaded = db_session.get(Shipment, shipment.id)
    assert _status_code(db_session, reloaded) == "DELIVERED"
    assert reloaded.actual_delivery_date == NOW.date()


def test_advance_out_of_sequence_raises(db_session, carrier, warehouse, customer, lookups):
    shipment = create_shipment(
        db_session,
        shipment_number="SHIP-1003",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        advance_shipment_status(
            db_session, shipment_id=shipment.id, new_status_code="DELIVERED", occurred_at=NOW
        )
    assert exc_info.value.rule == "FR-3.3"


def test_delivered_is_terminal(db_session, carrier, warehouse, customer, lookups):
    shipment = create_shipment(
        db_session,
        shipment_number="SHIP-1004",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="PICKED", occurred_at=NOW
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="IN_TRANSIT", occurred_at=NOW
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="DELIVERED", occurred_at=NOW
    )

    with pytest.raises(InvalidStateTransitionError):
        advance_shipment_status(
            db_session, shipment_id=shipment.id, new_status_code="PICKED", occurred_at=NOW
        )


@pytest.mark.parametrize("from_status", ["PICKED", "IN_TRANSIT"])
def test_exception_reachable_from_picked_and_in_transit(
    db_session, carrier, warehouse, customer, lookups, from_status
):
    shipment = create_shipment(
        db_session,
        shipment_number=f"SHIP-EXC-{from_status}",
        carrier_id=carrier.id,
        origin_warehouse_id=warehouse.id,
        destination_customer_id=customer.id,
        occurred_at=NOW,
    )
    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="PICKED", occurred_at=NOW
    )
    if from_status == "IN_TRANSIT":
        advance_shipment_status(
            db_session, shipment_id=shipment.id, new_status_code="IN_TRANSIT", occurred_at=NOW
        )

    advance_shipment_status(
        db_session, shipment_id=shipment.id, new_status_code="EXCEPTION", occurred_at=NOW
    )

    reloaded = db_session.get(Shipment, shipment.id)
    assert _status_code(db_session, reloaded) == "EXCEPTION"


def test_advance_unknown_shipment_raises(db_session, lookups):
    with pytest.raises(EntityNotFoundError):
        advance_shipment_status(
            db_session, shipment_id=999999, new_status_code="PICKED", occurred_at=NOW
        )
