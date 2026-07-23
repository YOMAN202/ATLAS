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
from app.models import InventoryPosition, Region, Warehouse, WarehouseZone


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


def create_warehouse(
    session: Session,
    *,
    warehouse_code: str,
    name: str,
    region_id: int,
    total_capacity_units: int,
    address_line1: str | None = None,
    city: str | None = None,
    state_province: str | None = None,
    postal_code: str | None = None,
    country: str | None = None,
    is_active: bool = True,
) -> Warehouse:
    """Create a warehouse master record.

    Intentionally thin: this is reference-data creation (ADR-007 requires
    even reference-data writes to go through Domain Services, not just
    transactional ones), not a business rule — it validates, constructs,
    and persists, nothing more.
    """

    if session.get(Region, region_id) is None:
        raise EntityNotFoundError(f"Region {region_id} does not exist")

    warehouse = Warehouse(
        warehouse_code=warehouse_code,
        name=name,
        region_id=region_id,
        total_capacity_units=total_capacity_units,
        address_line1=address_line1,
        city=city,
        state_province=state_province,
        postal_code=postal_code,
        country=country,
        is_active=is_active,
    )
    session.add(warehouse)
    session.flush()

    return warehouse


def create_warehouse_zone(
    session: Session,
    *,
    warehouse_id: int,
    zone_code: str,
    name: str,
    zone_capacity_units: int,
) -> WarehouseZone:
    """Create a zone within an existing warehouse. Thin: validates the
    parent warehouse exists, constructs, and persists."""

    warehouse = session.get(Warehouse, warehouse_id)
    if warehouse is None:
        raise EntityNotFoundError(f"Warehouse {warehouse_id} does not exist")

    zone = WarehouseZone(
        warehouse_id=warehouse_id,
        zone_code=zone_code,
        name=name,
        zone_capacity_units=zone_capacity_units,
    )
    session.add(zone)
    session.flush()

    return zone
