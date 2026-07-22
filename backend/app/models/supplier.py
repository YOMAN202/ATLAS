"""Supplier master (FR-1.1: supplier master with contract terms, lead
times, and reliability history). Reliability history is not a column here
— it is derived at ETL time from purchase_order_lines' receipt fields
(see procurement.py), which is what feeds fact_supplier_delivery."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(150))
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state_province: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(100))
    # FR-1.1: contract terms.
    payment_terms_days: Mapped[int] = mapped_column(nullable=False, default=30)
    # FR-1.1: lead times. Baseline lead time; per-delivery actuals are
    # captured on purchase_order_lines and drive the lead-time-variance KPI.
    default_lead_time_days: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
