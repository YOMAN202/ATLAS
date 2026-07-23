"""Domain Services — the only sanctioned OLTP write path (ADR-007).

Each submodule owns one bounded business area (procurement, inventory,
warehousing, transportation, orders, returns) and is callable and testable
without FastAPI or the Simulation Engine present, per the Master Prompt
§3 communication matrix and §6 Domain Services standard.
"""
