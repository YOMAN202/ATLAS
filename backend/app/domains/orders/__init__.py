"""Orders domain — order creation and allocation (FR-4.1, FR-4.2; BR-2).

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Writes inventory only through the inventory module's
`reserve`/`release_reservation` — never touches InventoryPosition directly.
"""

from app.domains.orders.service import allocate_order_line, create_order

__all__ = ["allocate_order_line", "create_order"]
