"""Warehouse zone-capacity enforcement (FR-2.2).

"Zone-level allocation" for the MVP means: inventory positions are tied
to a specific warehouse zone, zone capacity is modeled, and inventory
movements respect it. Advanced slotting/optimization — choosing *which*
zone to pick from, cross-zone rebalancing — is explicitly out of scope
for the MVP per FR-2.2 ("Advanced warehouse slotting and optimization are
future enhancements") and is not implemented here: callers (Phase 3
simulation, later the API) specify the zone; this module only validates it.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.shared.exceptions import EntityNotFoundError, ZoneCapacityExceededError
from app.models import InventoryPosition, WarehouseZone


def get_zone_occupied_units(session: Session, warehouse_zone_id: int) -> int:
    """Sum of on-hand quantity across every position in this zone."""

    total = session.scalar(
        select(func.coalesce(func.sum(InventoryPosition.quantity_on_hand), 0)).where(
            InventoryPosition.warehouse_zone_id == warehouse_zone_id
        )
    )
    return int(total or 0)


def assert_zone_capacity_available(
    session: Session, warehouse_zone_id: int, additional_quantity: int
) -> None:
    """Raise ZoneCapacityExceededError (FR-2.2) if adding
    `additional_quantity` units to this zone would exceed its modeled
    capacity. A no-op for additional_quantity <= 0 — movements that free
    up space can never violate a capacity ceiling.
    """

    if additional_quantity <= 0:
        return

    zone = session.get(WarehouseZone, warehouse_zone_id)
    if zone is None:
        raise EntityNotFoundError(f"WarehouseZone {warehouse_zone_id} does not exist")

    occupied = get_zone_occupied_units(session, warehouse_zone_id)
    if occupied + additional_quantity > zone.zone_capacity_units:
        raise ZoneCapacityExceededError(
            f"Zone '{zone.zone_code}' capacity {zone.zone_capacity_units} would be exceeded: "
            f"{occupied} occupied + {additional_quantity} requested",
            rule="FR-2.2",
        )
