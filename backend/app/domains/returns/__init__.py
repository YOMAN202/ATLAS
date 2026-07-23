"""Returns domain — return creation and inspection/disposition (FR-4.3; BR-5).

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Writes inventory only through the inventory module's
`record_transaction`, and only for a SELLABLE disposition.
"""

from app.domains.returns.service import create_return, inspect_return_line

__all__ = ["create_return", "inspect_return_line"]
