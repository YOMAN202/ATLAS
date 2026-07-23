"""Inventory domain — positions, the movement ledger (FR-2.1, FR-2.4; BR-2),
and product master data.

The only module that mutates InventoryPosition rows. Every other domain
(procurement receiving, orders allocating, returns restocking) goes
through this module's functions rather than touching InventoryPosition
directly, so BR-2's non-negative guarantee and the FR-2.2 zone-capacity
check are enforced in exactly one place.

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007).
"""

from app.domains.inventory.service import (
    create_product,
    get_or_create_position,
    record_transaction,
    release_reservation,
    reserve,
)

__all__ = [
    "create_product",
    "get_or_create_position",
    "record_transaction",
    "release_reservation",
    "reserve",
]
