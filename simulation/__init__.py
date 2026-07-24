"""ATLAS Simulation Engine (Phase 3).

Generates a realistic, rule-driven operational history by calling the
OLTP Domain Services layer exclusively (ADR-007) — this package never
imports SQLAlchemy models and writes to a table directly. It also never
reads the OLAP warehouse or Decision Support output (Master Prompt §9):
it is a pure producer of operational (OLTP) history.
"""
