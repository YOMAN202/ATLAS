"""Inventory positions + transactions (FR-2.1, FR-2.2, FR-2.4; BR-2).

inventory_positions is the current-state table (one row per product x
warehouse x zone). inventory_transactions is the append-only ledger of
every movement against a position — the two together let BR-2 ("inventory
cannot go negative") be enforced by the Domain Service layer (Phase 2)
while still giving a DB-level CHECK backstop here.
"""

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InventoryPosition(Base, TimestampMixin):
    __tablename__ = "inventory_positions"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", "warehouse_zone_id"),
        CheckConstraint("quantity_on_hand >= 0", name="quantity_on_hand_non_negative"),
        CheckConstraint("quantity_reserved >= 0", name="quantity_reserved_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), nullable=False)
    warehouse_zone_id: Mapped[int] = mapped_column(ForeignKey("warehouse_zones.id"), nullable=False)
    # BR-2: inventory cannot go negative — enforced at the DB level as a
    # backstop to the Domain Service logic that owns this invariant.
    quantity_on_hand: Mapped[int] = mapped_column(nullable=False, default=0)
    # Allocated to open orders, not yet shipped (FR-4.2 partial fulfillment).
    quantity_reserved: Mapped[int] = mapped_column(nullable=False, default=0)


class InventoryTransaction(Base, TimestampMixin):
    """Append-only ledger. source_reference_type/id is a deliberate,
    documented exception to "every FK enforced at the DB level" (ADR-002):
    a transaction's origin is polymorphic (a PO line receipt, an order
    line pick, a return line, or a transfer), and MySQL cannot express a
    single FK across multiple target tables. This is the one place in the
    OLTP schema that relationship is soft rather than DB-enforced."""

    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_position_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_positions.id"), nullable=False
    )
    transaction_type_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_transaction_types.id"), nullable=False
    )
    # Positive for receipt/return-in; negative for pick/adjustment-out. A
    # transfer is two rows: a negative at the source position, a positive
    # at the destination position.
    quantity_delta: Mapped[int] = mapped_column(nullable=False)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False, index=True)
    source_reference_type: Mapped[str | None] = mapped_column(String(30))
    source_reference_id: Mapped[int | None] = mapped_column()
