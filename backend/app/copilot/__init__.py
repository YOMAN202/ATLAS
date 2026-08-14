"""Phase 8 grounded analytics copilot (docs/phase8-analytics-copilot.md,
docs/phase8-grounding-spec.md). A read-only intelligence layer strictly
downstream of the deterministic decision-support core: it retrieves,
explains, and compares analytics Modules A-F already computed and
persisted -- it never generates a forecast, policy, score, or
optimization result itself, and holds no database credential of its
own (app.copilot.tools calls the existing dashboard REST API over
HTTP, the same trust boundary the frontend already operates inside).

Per ADR-023 (docs/ATLAS-TDD.md §14): claim drafting is the only
component that talks to an external LLM, and is built behind
ClaimDraftingClient so the deterministic verifier -- the actual
CI-blocking gate -- never depends on live network access.
"""
