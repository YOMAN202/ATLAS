"""Procurement: purchase orders + lines (FR-1.2, FR-1.3; BR-1).

purchase_order_lines' received_quantity/quality_rejected_quantity/
actual_delivery_date fields are the OLTP source for the "delivery event"
grain of fact_supplier_delivery (TDD §4.2.1) — there is no separate OLTP
delivery table because TDD §4.1 does not name one; a PO line's receipt
*is* the delivery event.
"""

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # DQ-2
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("po_statuses.id"), nullable=False)
    order_date: Mapped[Date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[Date | None] = mapped_column(Date)


class PurchaseOrderLine(Base, TimestampMixin):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("purchase_order_id", "line_number"),
        CheckConstraint("ordered_quantity > 0", name="ordered_quantity_positive"),
        CheckConstraint("received_quantity >= 0", name="received_quantity_non_negative"),
        CheckConstraint(
            "quality_rejected_quantity >= 0", name="quality_rejected_quantity_non_negative"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    ordered_quantity: Mapped[int] = mapped_column(nullable=False)
    # Cost at time of order — deliberately not a live join to products.unit_cost,
    # so historical procurement spend doesn't shift when a product's cost changes.
    unit_cost: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    # BR-1: PO cannot be marked fulfilled until received_quantity matches
    # ordered_quantity within an approved tolerance (Domain Service, Phase 2).
    received_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    # FR-1.3: quality rejection rate.
    quality_rejected_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    expected_delivery_date: Mapped[Date | None] = mapped_column(Date)
    # FR-1.3: on-time % — this is the delivery event date.
    actual_delivery_date: Mapped[Date | None] = mapped_column(Date)
