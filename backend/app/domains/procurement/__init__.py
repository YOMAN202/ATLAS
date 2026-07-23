"""Procurement domain — purchase order lifecycle (FR-1.2, FR-1.3; BR-1).

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Writes inventory only through the inventory module's
`record_transaction` — never touches InventoryPosition directly.
"""

from app.domains.procurement.service import (
    PO_RECEIPT_TOLERANCE,
    close_purchase_order,
    confirm_purchase_order,
    create_purchase_order,
    mark_purchase_order_fulfilled,
    receive_purchase_order_line,
    submit_purchase_order,
)

__all__ = [
    "PO_RECEIPT_TOLERANCE",
    "close_purchase_order",
    "confirm_purchase_order",
    "create_purchase_order",
    "mark_purchase_order_fulfilled",
    "receive_purchase_order_line",
    "submit_purchase_order",
]
