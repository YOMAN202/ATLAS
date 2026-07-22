"""Constrained-enumeration lookup tables.

Master Prompt §5 / TDD §4.1: "Status fields ... modeled as constrained
enumerations (lookup tables, not free-text)." The TDD's core-entity table
list (§4.1) is representative of the business objects, not exhaustive of
every supporting table; these lookup tables are the concrete
implementation of that stated principle, plus the "regions, vehicle types"
static reference data the Roadmap Phase 1 deliverables call for.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Region(Base, TimestampMixin):
    """Geographic region — anchors FR-5.1 ("forecasts per SKU/region") and
    feeds the OLAP dim_region conformed dimension (TDD §4.2)."""

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class InventoryTransactionType(Base, TimestampMixin):
    """FR-2.1: "updated by every relevant transaction (receipt, pick,
    transfer, adjustment, return)" — those five values populate this table."""

    __tablename__ = "inventory_transaction_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class POStatus(Base, TimestampMixin):
    """FR-1.2 lifecycle: draft -> submitted -> confirmed -> fulfilled -> closed."""

    __tablename__ = "po_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)


class OrderStatus(Base, TimestampMixin):
    """FR-4.2 order lifecycle, including partial fulfillment and
    backorders (BR-2): pending -> allocated -> partially_fulfilled /
    backordered -> fulfilled -> cancelled."""

    __tablename__ = "order_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)


class ReturnReason(Base, TimestampMixin):
    """FR-4.3: returns with reason codes."""

    __tablename__ = "return_reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class ReturnDisposition(Base, TimestampMixin):
    """BR-5: failed inspection routes to a separate disposition (e.g.
    sellable, quarantine, scrap, return_to_supplier)."""

    __tablename__ = "return_dispositions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
