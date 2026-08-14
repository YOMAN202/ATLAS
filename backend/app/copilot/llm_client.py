"""Claim-drafting client (ADR-023, docs/ATLAS-TDD.md §14): an abstract
interface with two implementations. The deterministic verifier -- the
actual CI-blocking gate -- depends on neither implementation directly;
it verifies whatever claims arrive, regardless of source, which is why
the verifier's own tests (test_verifier_unit.py) use raw Claim objects
with no client at all.
"""

from abc import ABC, abstractmethod

from app.copilot.citations import ToolResult
from app.copilot.claims import Claim
from app.core.config import settings


class ClaimDraftingClient(ABC):
    @abstractmethod
    def draft_claims(self, question: str, tool_results: list[ToolResult]) -> list[Claim]:
        """Given a question and the tool payloads retrieved for it,
        return a list of typed Claim objects. Implementations must
        never fabricate a citation_id that doesn't correspond to a
        real ToolResult passed in -- the verifier checks this, but a
        well-behaved client shouldn't rely on that check."""
        raise NotImplementedError


class AnthropicClaimDraftingClient(ClaimDraftingClient):
    """The real production client. Requires ANTHROPIC_API_KEY
    (settings.anthropic_api_key) -- raises a clear configuration error
    rather than silently degrading if it's unset, the same discipline
    every other module in this platform uses for a missing
    prerequisite (e.g. run_module_e.py's VALIDATION_FAILURE exit when
    no active forecast model exists).

    Not exercised end-to-end against a live model in this pass -- no
    API key is configured in this environment (ADR-023). The
    CI-blocking verification harness runs entirely against
    FixtureClaimDraftingClient below, which is a deliberate design
    choice, not a placeholder standing in for missing work.
    """

    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "AnthropicClaimDraftingClient requires settings.anthropic_api_key "
                "(env var ANTHROPIC_API_KEY) to be configured. Refusing to run "
                "rather than silently falling back to an unverified response."
            )
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = model

    def draft_claims(self, question: str, tool_results: list[ToolResult]) -> list[Claim]:
        # Real integration point: send `question` and the tool_results'
        # payloads (never raw database access) to the model with a
        # strict-JSON claims-list output contract, parse the response
        # into FactClaim/ComparisonClaim/DerivedClaim objects. Parsing
        # and prompt construction are intentionally not implemented in
        # this pass (no API key to test against) -- see ADR-023.
        raise NotImplementedError(
            "AnthropicClaimDraftingClient.draft_claims is not exercised in this "
            "environment (no ANTHROPIC_API_KEY configured, ADR-023). The client "
            "shape is defined so the verifier/renderer/refusal pipeline can be "
            "built and proven against FixtureClaimDraftingClient first."
        )


class FixtureClaimDraftingClient(ClaimDraftingClient):
    """Deterministic, version-controlled claim drafts keyed by
    question -- the client every test and the CI-blocking eval harness
    use (ADR-023). Includes both realistic "good" drafts and
    deliberately flawed ones (wrong values, invented citations,
    inverted comparisons), because the verifier's job is to catch bad
    claims, and that can only be proven by feeding it some."""

    def __init__(self, fixtures: dict[str, list[Claim]]) -> None:
        self._fixtures = fixtures

    def draft_claims(self, question: str, tool_results: list[ToolResult]) -> list[Claim]:
        if question not in self._fixtures:
            raise KeyError(
                f"No fixture claims registered for question: {question!r}. "
                "FixtureClaimDraftingClient requires an explicit fixture -- "
                "silent gaps are not allowed in test/eval data."
            )
        return self._fixtures[question]
