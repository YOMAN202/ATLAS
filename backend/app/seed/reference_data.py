"""Seed/reference data loader for static lookup tables (Roadmap Phase 1:
"Seed/reference data loaders for static lookups: status codes, regions,
vehicle types").

Idempotent: safe to re-run (checks for an existing row by its unique
`code` before inserting, rather than assuming a fresh database).

vehicle_types' capacity/cost figures are illustrative starting values for
FR-3.1's "capacity and cost profiles" — the Simulation Engine's world-state
config (TDD §5, Phase 3) is the designated place to tune them further.
"""

from sqlalchemy.orm import Session

from app.models import (
    InventoryTransactionType,
    OrderStatus,
    POStatus,
    Region,
    ReturnDisposition,
    ReturnReason,
    ShipmentStatus,
    VehicleType,
)

REGIONS = [
    ("NE", "Northeast"),
    ("MW", "Midwest"),
    ("SO", "South"),
    ("WE", "West"),
    ("INTL", "International"),
]

INVENTORY_TRANSACTION_TYPES = [
    ("RECEIPT", "Receipt"),
    ("PICK", "Pick"),
    ("TRANSFER", "Transfer"),
    ("ADJUSTMENT", "Adjustment"),
    ("RETURN", "Return"),
]

# (code, name, sort_order)
PO_STATUSES = [
    ("DRAFT", "Draft", 1),
    ("SUBMITTED", "Submitted", 2),
    ("CONFIRMED", "Confirmed", 3),
    ("FULFILLED", "Fulfilled", 4),
    ("CLOSED", "Closed", 5),
]

ORDER_STATUSES = [
    ("PENDING", "Pending", 1),
    ("ALLOCATED", "Allocated", 2),
    ("PARTIALLY_FULFILLED", "Partially Fulfilled", 3),
    ("BACKORDERED", "Backordered", 4),
    ("FULFILLED", "Fulfilled", 5),
    ("CANCELLED", "Cancelled", 6),
]

SHIPMENT_STATUSES = [
    ("CREATED", "Created", 1),
    ("PICKED", "Picked", 2),
    ("IN_TRANSIT", "In Transit", 3),
    ("DELIVERED", "Delivered", 4),
    ("EXCEPTION", "Exception", 5),
]

RETURN_REASONS = [
    ("DAMAGED", "Damaged"),
    ("WRONG_ITEM", "Wrong Item"),
    ("NO_LONGER_NEEDED", "No Longer Needed"),
    ("QUALITY_DEFECT", "Quality Defect"),
    ("OTHER", "Other"),
]

RETURN_DISPOSITIONS = [
    ("SELLABLE", "Sellable"),
    ("QUARANTINE", "Quarantine"),
    ("SCRAP", "Scrap"),
    ("RETURN_TO_SUPPLIER", "Return to Supplier"),
]

# (code, name, capacity_units, cost_per_mile)
VEHICLE_TYPES = [
    ("VAN", "Cargo Van", 500, "1.10"),
    ("BOX_TRUCK", "Box Truck", 2000, "1.75"),
    ("SEMI_TRAILER", "Semi Trailer", 10000, "2.50"),
]


def _seed_simple(session: Session, model: type, rows: list[tuple[str, str]]) -> None:
    existing_codes = {row.code for row in session.query(model.code).all()}
    for code, name in rows:
        if code not in existing_codes:
            session.add(model(code=code, name=name))


def _seed_with_sort_order(session: Session, model: type, rows: list[tuple[str, str, int]]) -> None:
    existing_codes = {row.code for row in session.query(model.code).all()}
    for code, name, sort_order in rows:
        if code not in existing_codes:
            session.add(model(code=code, name=name, sort_order=sort_order))


def seed_reference_data(session: Session) -> None:
    _seed_simple(session, Region, REGIONS)
    _seed_simple(session, InventoryTransactionType, INVENTORY_TRANSACTION_TYPES)
    _seed_simple(session, ReturnReason, RETURN_REASONS)
    _seed_simple(session, ReturnDisposition, RETURN_DISPOSITIONS)
    _seed_with_sort_order(session, POStatus, PO_STATUSES)
    _seed_with_sort_order(session, OrderStatus, ORDER_STATUSES)
    _seed_with_sort_order(session, ShipmentStatus, SHIPMENT_STATUSES)

    existing_vehicle_codes = {row.code for row in session.query(VehicleType.code).all()}
    for code, name, capacity_units, cost_per_mile in VEHICLE_TYPES:
        if code not in existing_vehicle_codes:
            session.add(
                VehicleType(
                    code=code,
                    name=name,
                    capacity_units=capacity_units,
                    cost_per_mile=cost_per_mile,
                )
            )

    session.commit()


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from app.core.config import settings

    engine = create_engine(settings.database_url_oltp)
    with Session(engine) as db_session:
        seed_reference_data(db_session)
        print("Reference data seeded.")
