"""Product master. unit_cost/unit_price are the current standard values;
order/PO lines snapshot their own price/cost at transaction time rather
than joining live to this table, so historical revenue/margin figures do
not shift retroactively when a product's price changes."""

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    unit_of_measure: Mapped[str] = mapped_column(String(10), nullable=False, default="EA")
    # NFR-4: DECIMAL, never FLOAT/DOUBLE, for money.
    unit_cost: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Numeric] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
