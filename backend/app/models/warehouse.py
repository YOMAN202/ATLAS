"""Warehouse + zone masters (FR-2.2: warehouse capacity constraints and
zone-level allocation)."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    # FR-2.2: warehouse capacity constraints.
    total_capacity_units: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class WarehouseZone(Base, TimestampMixin):
    """FR-2.2: zone-level allocation. Inventory positions (Phase 1, next
    commit) are associated with a zone, not just a warehouse."""

    __tablename__ = "warehouse_zones"
    __table_args__ = (UniqueConstraint("warehouse_id", "zone_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    zone_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # FR-2.2: zone capacity is modeled.
    zone_capacity_units: Mapped[int] = mapped_column(nullable=False)
