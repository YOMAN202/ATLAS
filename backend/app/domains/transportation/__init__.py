"""Transportation domain — shipment lifecycle (FR-3.1..FR-3.4).

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Standalone for Phase 2 — linking a shipment back to
the order line(s) it fulfills is not a named Phase 2 deliverable and is
left for whichever phase wires order dispatch (see orders/service.py).
"""

from app.domains.transportation.service import advance_shipment_status, create_shipment

__all__ = ["advance_shipment_status", "create_shipment"]
