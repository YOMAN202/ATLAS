"""The renderer (docs/phase8-grounding-spec.md §1): verified claims to
final response, by template -- deliberately NOT a second LLM call.
Re-generating prose via another model pass would reopen exactly the
hallucination risk the claims/verification pipeline exists to close.
Only VERIFIED claims are ever passed in here; the pipeline (§ below)
is responsible for filtering before calling this module, but the
renderer defensively re-filters too, so a caller bug can't leak an
unverified number through.
"""

from dataclasses import dataclass

from app.copilot.citations import Citation
from app.copilot.claims import ComparisonClaim, DerivedClaim, FactClaim
from app.copilot.verifier import VerifiedClaim


@dataclass(frozen=True)
class CopilotResponse:
    status: str  # "answered"
    answer: str
    sources: tuple[Citation, ...]
    claim_count: int


def _render_claim_sentence(vc: VerifiedClaim) -> str:
    claim = vc.claim
    if isinstance(claim, FactClaim):
        return f"{claim.metric_path} is {claim.value}."
    if isinstance(claim, ComparisonClaim):
        return (
            f"{claim.metric_path} is {claim.direction} for A ({claim.value_a}) "
            f"than B ({claim.value_b})."
        )
    if isinstance(claim, DerivedClaim):
        return (
            f"{claim.operation} of {claim.operand_metric_path_a} and "
            f"{claim.operand_metric_path_b} is {claim.value}."
        )
    raise TypeError(  # pragma: no cover — verifier already typed this
        f"Unrenderable claim type: {type(claim)}"
    )


def render(verified_claims: list[VerifiedClaim]) -> CopilotResponse:
    """Builds the final response from ONLY claims where `.verified` is
    True. This is the enforcement point for "no numeric value may
    appear in the final response unless it originates from a verified
    claim" -- unverified claims are excluded here by construction, not
    filtered by convention upstream."""
    verified = [vc for vc in verified_claims if vc.verified]

    sentences = [_render_claim_sentence(vc) for vc in verified]
    answer = " ".join(sentences)

    seen_ids: set[str] = set()
    sources: list[Citation] = []
    for vc in verified:
        for citation in vc.citations:
            if citation.citation_id not in seen_ids:
                seen_ids.add(citation.citation_id)
                sources.append(citation)

    return CopilotResponse(
        status="answered",
        answer=answer,
        sources=tuple(sources),
        claim_count=len(verified),
    )
