"""Customer orders (FR-4.1, FR-4.2; BR-2).

order_lines carries fulfillment_warehouse_id (set once allocated) at the
LINE grain rather than a single warehouse_id on the order, because BR-2
partial fulfillment means different lines of the same order can be
allocated from, and shipped out of, different warehouses.

A shipment_id FK is added to order_lines in the transportation commit,
once the shipments table exists to reference (Alembic/FK ordering: a
table cannot FK-reference a table that doesn't exist yet).
"""

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy import String as SAString
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(SAString(30), unique=True, nullable=False)  # DQ-2
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("order_statuses.id"), nullable=False)
    order_date: Mapped[Date] = mapped_column(Date, nullable=False)


class OrderLine(Base, TimestampMixin):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "line_number"),
        CheckConstraint("ordered_quantity > 0", name="ordered_quantity_positive"),
        CheckConstraint("allocated_quantity >= 0", name="allocated_quantity_non_negative"),
        CheckConstraint("backordered_quantity >= 0", name="backordered_quantity_non_negative"),
        CheckConstraint(
            "allocated_quantity + backordered_quantity <= ordered_quantity",
            name="allocated_plus_backordered_within_ordered",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    ordered_quantity: Mapped[int] = mapped_column(nullable=False)
    # BR-2: partial fulfillment — the remainder is backordered.
    allocated_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    backordered_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    # Price/cost at time of sale (revenue + COGS for gross-margin KPI),
    # snapshotted rather than joined live to products, same rationale as
    # purchase_order_lines.unit_cost.
    unit_price: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    fulfillment_warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"))
