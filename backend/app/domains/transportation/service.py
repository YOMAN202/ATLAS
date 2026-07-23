"""Shipment lifecycle (FR-3.1..FR-3.4): created -> picked -> in_transit ->
delivered / exception.

A single `shipments` table models both customer deliveries (FR-3.2) and
inter-warehouse transfers (FR-2.3); exactly one destination must be set,
matching the DB-level `exactly_one_destination` CHECK — enforced here too
so callers get a clear typed error instead of an IntegrityError.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.domains.shared.exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domains.shared.lookups import get_code_by_id, get_id_by_code
from app.models import Shipment, ShipmentEvent, ShipmentStatus

# FR-3.3 lifecycle graph. DELIVERED and EXCEPTION are terminal for the
# MVP — exception recovery/redelivery flows are a future enhancement, not
# named in the Roadmap's Phase 2 deliverables.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"PICKED", "EXCEPTION"},
    "PICKED": {"IN_TRANSIT", "EXCEPTION"},
    "IN_TRANSIT": {"DELIVERED", "EXCEPTION"},
    "DELIVERED": set(),
    "EXCEPTION": set(),
}


def create_shipment(
    session: Session,
    *,
    shipment_number: str,
    carrier_id: int,
    origin_warehouse_id: int,
    occurred_at: datetime,
    destination_warehouse_id: int | None = None,
    destination_customer_id: int | None = None,
    ship_date=None,
    estimated_delivery_date=None,
    distance_miles=None,
    shipping_cost=None,
) -> Shipment:
    """Create a shipment in CREATED status with its first lifecycle event.

    Raises:
        ValueError: neither, or both, of destination_warehouse_id /
            destination_customer_id were given — exactly one is required.
    """

    has_warehouse_dest = destination_warehouse_id is not None
    has_customer_dest = destination_customer_id is not None
    if has_warehouse_dest == has_customer_dest:
        raise ValueError(
            "exactly one of destination_warehouse_id or destination_customer_id is required"
        )

    shipment = Shipment(
        shipment_number=shipment_number,
        carrier_id=carrier_id,
        origin_warehouse_id=origin_warehouse_id,
        destination_warehouse_id=destination_warehouse_id,
        destination_customer_id=destination_customer_id,
        status_id=get_id_by_code(session, ShipmentStatus, "CREATED"),
        ship_date=ship_date,
        estimated_delivery_date=estimated_delivery_date,
        distance_miles=distance_miles,
        shipping_cost=shipping_cost,
    )
    session.add(shipment)
    session.flush()

    session.add(
        ShipmentEvent(
            shipment_id=shipment.id,
            status_id=shipment.status_id,
            occurred_at=occurred_at,
        )
    )
    session.flush()

    return shipment


def advance_shipment_status(
    session: Session,
    *,
    shipment_id: int,
    new_status_code: str,
    occurred_at: datetime,
    location: str | None = None,
    notes: str | None = None,
) -> Shipment:
    """Advance a shipment to `new_status_code`, appending a lifecycle event.

    Raises:
        EntityNotFoundError: unknown shipment.
        InvalidStateTransitionError: FR-3.3 — the requested status is not
            reachable from the shipment's current status.
    """

    shipment = session.get(Shipment, shipment_id)
    if shipment is None:
        raise EntityNotFoundError(f"Shipment {shipment_id} does not exist")

    current_code = get_code_by_id(session, ShipmentStatus, shipment.status_id)
    allowed = _ALLOWED_TRANSITIONS.get(current_code, set())
    if new_status_code not in allowed:
        raise InvalidStateTransitionError(
            f"Shipment {shipment_id} is '{current_code}', cannot move to "
            f"'{new_status_code}' (allowed: {sorted(allowed) or 'none — terminal state'})",
            rule="FR-3.3",
        )

    shipment.status_id = get_id_by_code(session, ShipmentStatus, new_status_code)
    session.add(
        ShipmentEvent(
            shipment_id=shipment.id,
            status_id=shipment.status_id,
            occurred_at=occurred_at,
            location=location,
            notes=notes,
        )
    )

    if new_status_code == "DELIVERED":
        shipment.actual_delivery_date = occurred_at.date()

    session.flush()

    return shipment
