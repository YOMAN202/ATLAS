"""Transportation: carriers + shipments + shipment_events (FR-3.1..FR-3.4).

A single shipments table models both customer-delivery shipments (FR-3.2)
and inter-warehouse transfers (FR-2.3), since TDD §4.1 names only one
`shipments` table. A CHECK constraint ensures exactly one destination
(warehouse xor customer) is set per shipment.
"""

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Carrier(Base, TimestampMixin):
    __tablename__ = "carriers"

    id: Mapped[int] = mapped_column(primary_key=True)
    carrier_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"
    __table_args__ = (
        CheckConstraint(
            "(destination_warehouse_id IS NOT NULL AND destination_customer_id IS NULL) OR "
            "(destination_warehouse_id IS NULL AND destination_customer_id IS NOT NULL)",
            name="exactly_one_destination",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # DQ-2
    carrier_id: Mapped[int] = mapped_column(ForeignKey("carriers.id"), nullable=False)
    origin_warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    # FR-2.3: inter-warehouse transfer destination.
    destination_warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
    # FR-3.2/UC-2: customer-delivery destination.
    destination_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    status_id: Mapped[int] = mapped_column(ForeignKey("shipment_statuses.id"), nullable=False)
    ship_date: Mapped[Date | None] = mapped_column(Date)
    estimated_delivery_date: Mapped[Date | None] = mapped_column(Date)
    actual_delivery_date: Mapped[Date | None] = mapped_column(Date)
    # FR-3.4: cost per mile needs distance.
    distance_miles: Mapped[Numeric | None] = mapped_column(Numeric(10, 2))
    # FR-3.2: shipments generated with cost.
    shipping_cost: Mapped[Numeric | None] = mapped_column(Numeric(12, 2))


class ShipmentEvent(Base, TimestampMixin):
    """FR-3.3: status-history/audit-trail of a shipment's lifecycle."""

    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("shipment_statuses.id"), nullable=False)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(String(500))
