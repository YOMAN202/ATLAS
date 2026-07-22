# simulation/

Day-advancing simulation engine that generates a realistic 5-year operational history by calling the OLTP Domain Services layer — never writing to the database directly (ADR-007).

Populated in **Phase 3** (`simulation/engine.py`, `simulation/generators/`, `simulation/config/`), after the Domain Services layer (Phase 2) it depends on. See `docs/ATLAS-Roadmap.md`.

Skeleton only for Phase 0 — see `docs/ATLAS-ClaudeCode-MasterPrompt.md` §9 for simulation standards.
