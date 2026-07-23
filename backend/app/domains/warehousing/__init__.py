"""Warehousing domain — zone-level allocation (FR-2.2).

Responsibility: enforce warehouse-zone capacity. Does not own inventory
quantities themselves (that's the inventory module); this module only
answers "would this movement exceed the zone's modeled capacity."

Boundary: callable and testable without FastAPI or the Simulation Engine
present (ADR-007). Never writes outside this schema's zone/capacity
concern — it has no business logic about *what* moves, only *how much
room* a zone has left.
"""

from app.domains.warehousing.service import assert_zone_capacity_available, get_zone_occupied_units

__all__ = ["assert_zone_capacity_available", "get_zone_occupied_units"]
