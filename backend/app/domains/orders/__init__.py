"""Orders domain — order creation and allocation (FR-4.1, FR-4.2; BR-2),
and customer master data.

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Writes inventory only through the inventory module's
`reserve`/`release_reservation` — never touches InventoryPosition directly.
"""

from app.domains.orders.service import (
    allocate_order_line,
    allocate_order_lines_bulk,
    create_customer,
    create_order,
    mark_line_shipped,
    mark_lines_shipped_bulk,
)

__all__ = [
    "allocate_order_line",
    "allocate_order_lines_bulk",
    "create_customer",
    "create_order",
    "mark_line_shipped",
    "mark_lines_shipped_bulk",
]
