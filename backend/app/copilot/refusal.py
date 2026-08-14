"""Structured refusal (docs/phase8-grounding-spec.md §4). Refusal is a
typed response, not free-text "I don't know" prose, so the eval
harness can assert on `reason_code` deterministically. A refusal is
always preferred to a fabrication -- this module exists to make that
the easy, default path, not a special case bolted on afterward.
"""

from dataclasses import dataclass
from typing import Literal

from app.copilot.verifier import VerifiedClaim

ReasonCode = Literal[
    "no_matching_tool",
    "entity_not_found",
    "out_of_scope",
    "insufficient_verified_evidence",
    "data_unavailable",
]

# Keyword-level out-of-scope detection for capabilities explicitly
# excluded from the initial release (docs/phase8-analytics-copilot.md
# §3, §9) -- checked before any tool call, so an out-of-scope question
# never even reaches a tool.
_OUT_OF_SCOPE_MARKERS = {
    "eoq": "EOQ is explicitly out of scope for Module B (docs/phase7-module-b-completion.md).",
    "economic order quantity": (
        "EOQ is explicitly out of scope for Module B (docs/phase7-module-b-completion.md)."
    ),
    "executive briefing": (
        "Executive briefing generation is explicitly out of scope for the initial "
        "copilot release (docs/phase8-analytics-copilot.md §3)."
    ),
    "submit a scenario": (
        "Live, user-parameterized scenario submission is not built -- Module E is a "
        "precomputed scenario library (docs/phase7-2-architecture.md §1.2)."
    ),
    "create a scenario": (
        "Live, user-parameterized scenario submission is not built -- Module E is a "
        "precomputed scenario library (docs/phase7-2-architecture.md §1.2)."
    ),
}


@dataclass(frozen=True)
class Refusal:
    reason_code: ReasonCode
    explanation: str


def check_out_of_scope(question: str) -> Refusal | None:
    lowered = question.lower()
    for marker, explanation in _OUT_OF_SCOPE_MARKERS.items():
        if marker in lowered:
            return Refusal(reason_code="out_of_scope", explanation=explanation)
    return None


def decide_refusal(
    verified_claims: list[VerifiedClaim], had_tool_results: bool, entity_missing: bool
) -> Refusal | None:
    """Called after tool calls and verification. Returns a Refusal if
    the pipeline should stop here, or None if there is enough verified
    evidence to render an answer."""
    if not had_tool_results:
        return Refusal(
            reason_code="no_matching_tool",
            explanation="No available tool can retrieve data relevant to this question.",
        )
    if entity_missing:
        return Refusal(
            reason_code="entity_not_found",
            explanation="The requested entity was not found in the retrieved data.",
        )
    if not any(vc.verified for vc in verified_claims):
        return Refusal(
            reason_code="insufficient_verified_evidence",
            explanation=(
                "Retrieved data exists, but no claim about it could be verified "
                "against the actual retrieved values."
            ),
        )
    return None
