"""Returns (FR-4.3; BR-5).

return_number is not in SRS DQ-2's example list (order_number, po_number,
shipment_number), but Master Prompt §5's stated principle — "unique
constraints on all business keys" — applies to any natural business
identifier, so it gets one here for consistency.
"""

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Return(Base, TimestampMixin):
    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    return_date: Mapped[Date] = mapped_column(Date, nullable=False)


class ReturnLine(Base, TimestampMixin):
    __tablename__ = "return_lines"
    __table_args__ = (
        UniqueConstraint("return_id", "line_number"),
        CheckConstraint("returned_quantity > 0", name="returned_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id"), nullable=False)
    order_line_id: Mapped[int] = mapped_column(ForeignKey("order_lines.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(nullable=False)
    returned_quantity: Mapped[int] = mapped_column(nullable=False)
    reason_id: Mapped[int] = mapped_column(ForeignKey("return_reasons.id"), nullable=False)
    # BR-5: null until inspected; sellable inventory is decremented only
    # after the inspection step sets a disposition.
    disposition_id: Mapped[int | None] = mapped_column(ForeignKey("return_dispositions.id"))
    inspected_at: Mapped[DateTime | None] = mapped_column(DateTime)
