"""The deterministic verifier (docs/phase8-grounding-spec.md §2) --
the actual CI-blocking gate. Every claim drafted by an LLM (or a
fixture, in tests) is checked here against the real, retrieved tool
payloads before it is allowed anywhere near a rendered response. Pure
Python, no network dependency, no LLM call -- its correctness is
provable the same way every other formula in this platform is:
against known synthetic inputs with a known-correct answer
(backend/tests/copilot/test_verifier_unit.py).
"""

from dataclasses import dataclass

from app.copilot.citations import Citation, ToolResult
from app.copilot.claims import Claim, ComparisonClaim, DerivedClaim, FactClaim

# Relative tolerance for numeric matching -- wide enough to absorb
# reasonable rounding/formatting choices an LLM might make when
# restating a number ("24%" for 24.13%), narrow enough that a
# materially wrong number still fails. Absolute floor covers small
# currency-cent-level values where a pure relative tolerance would be
# too forgiving.
RELATIVE_TOLERANCE = 0.005
ABSOLUTE_TOLERANCE = 0.01


@dataclass(frozen=True)
class VerifiedClaim:
    claim: Claim
    verified: bool
    reason: str
    citations: tuple[Citation, ...]


def _extract_path(payload: dict, path: str):
    """Dotted-path traversal into a retrieved JSON payload, e.g.
    "summary.avg_risk_score" or "recommendation.safety_stock" --
    including numeric segments for list indexing, e.g.
    "scenarios.0.scenario_inventory_investment" (Module E's
    /scenarios/compare returns a list under "scenarios"). Returns
    None (never raises) if any segment is missing or out of range -- a
    missing value is a verification failure, not a Python exception."""
    current = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return None
            current = current[segment]
        elif isinstance(current, list):
            if not segment.lstrip("-").isdigit():
                return None
            index = int(segment)
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        else:
            return None
    return current


def _numeric_match(claimed, actual) -> bool:
    if actual is None:
        return False
    if isinstance(claimed, str) or isinstance(actual, str):
        return str(claimed) == str(actual)
    try:
        claimed_f, actual_f = float(claimed), float(actual)
    except (TypeError, ValueError):
        return False
    diff = abs(claimed_f - actual_f)
    return diff <= ABSOLUTE_TOLERANCE or diff <= RELATIVE_TOLERANCE * max(abs(actual_f), 1e-9)


def _find_citation(citation_id: str, tool_results: list[ToolResult]) -> Citation | None:
    for tr in tool_results:
        if tr.citation.citation_id == citation_id:
            return tr.citation
    return None


def _find_payload(citation_id: str, tool_results: list[ToolResult]) -> dict | None:
    for tr in tool_results:
        if tr.citation.citation_id == citation_id:
            return tr.payload
    return None


def verify_fact_claim(claim: FactClaim, tool_results: list[ToolResult]) -> VerifiedClaim:
    citation = _find_citation(claim.citation_id, tool_results)
    if citation is None:
        return VerifiedClaim(claim, False, "citation_not_found", ())
    payload = _find_payload(claim.citation_id, tool_results)
    actual = _extract_path(payload, claim.metric_path)
    if actual is None:
        return VerifiedClaim(
            claim, False, f"metric_path_not_found: {claim.metric_path}", (citation,)
        )
    if not _numeric_match(claim.value, actual):
        return VerifiedClaim(
            claim, False, f"value_mismatch: claimed {claim.value!r}, actual {actual!r}", (citation,)
        )
    return VerifiedClaim(claim, True, "exact_match", (citation,))


def verify_comparison_claim(
    claim: ComparisonClaim, tool_results: list[ToolResult]
) -> VerifiedClaim:
    citation_a = _find_citation(claim.citation_id_a, tool_results)
    citation_b = _find_citation(claim.citation_id_b, tool_results)
    if citation_a is None or citation_b is None:
        return VerifiedClaim(
            claim, False, "citation_not_found", tuple(c for c in (citation_a, citation_b) if c)
        )

    payload_a = _find_payload(claim.citation_id_a, tool_results)
    payload_b = _find_payload(claim.citation_id_b, tool_results)
    actual_a = _extract_path(payload_a, claim.metric_path)
    actual_b = _extract_path(payload_b, claim.metric_path)
    citations = (citation_a, citation_b)

    if actual_a is None or actual_b is None:
        return VerifiedClaim(claim, False, f"metric_path_not_found: {claim.metric_path}", citations)
    if not _numeric_match(claim.value_a, actual_a) or not _numeric_match(claim.value_b, actual_b):
        return VerifiedClaim(claim, False, "value_mismatch", citations)

    try:
        a_f, b_f = float(actual_a), float(actual_b)
    except (TypeError, ValueError):
        return VerifiedClaim(claim, False, "non_numeric_comparison", citations)

    if a_f > b_f:
        actual_direction = "higher"
    elif a_f < b_f:
        actual_direction = "lower"
    else:
        actual_direction = "equal"

    if actual_direction != claim.direction:
        return VerifiedClaim(
            claim,
            False,
            f"direction_mismatch: claimed {claim.direction}, actual {actual_direction}",
            citations,
        )
    return VerifiedClaim(claim, True, "direction_confirmed", citations)


_OPERATIONS = {
    "difference": lambda a, b: a - b,
    "sum": lambda a, b: a + b,
    "pct_delta": lambda a, b: ((a - b) / b * 100) if b else None,
}


def verify_derived_claim(claim: DerivedClaim, tool_results: list[ToolResult]) -> VerifiedClaim:
    """Legitimate arithmetic on retrieved values (a difference, sum, or
    percentage delta) is verified by recomputing the operation from
    the retrieved operands -- not rejected as "not literally in the
    payload" the way a fabricated number would be."""
    citation_a = _find_citation(claim.citation_id_a, tool_results)
    citation_b = _find_citation(claim.citation_id_b, tool_results)
    if citation_a is None or citation_b is None:
        return VerifiedClaim(
            claim, False, "citation_not_found", tuple(c for c in (citation_a, citation_b) if c)
        )

    payload_a = _find_payload(claim.citation_id_a, tool_results)
    payload_b = _find_payload(claim.citation_id_b, tool_results)
    operand_a = _extract_path(payload_a, claim.operand_metric_path_a)
    operand_b = _extract_path(payload_b, claim.operand_metric_path_b)
    citations = (citation_a, citation_b)

    if operand_a is None or operand_b is None:
        return VerifiedClaim(claim, False, "operand_not_found", citations)

    op = _OPERATIONS.get(claim.operation)
    if op is None:
        return VerifiedClaim(claim, False, f"unknown_operation: {claim.operation}", citations)

    try:
        expected = op(float(operand_a), float(operand_b))
    except (TypeError, ValueError, ZeroDivisionError):
        return VerifiedClaim(claim, False, "operation_failed", citations)

    if expected is None or not _numeric_match(claim.value, expected):
        return VerifiedClaim(
            claim,
            False,
            f"derived_value_mismatch: claimed {claim.value}, recomputed {expected}",
            citations,
        )
    return VerifiedClaim(claim, True, "derived_value_confirmed", citations)


def verify_claims(claims: list[Claim], tool_results: list[ToolResult]) -> list[VerifiedClaim]:
    """Verify every claim independently. A claim that fails
    verification is never silently included -- callers must filter on
    `.verified` before rendering (app.copilot.renderer enforces this
    by construction, not by convention)."""
    results = []
    for claim in claims:
        if isinstance(claim, FactClaim):
            results.append(verify_fact_claim(claim, tool_results))
        elif isinstance(claim, ComparisonClaim):
            results.append(verify_comparison_claim(claim, tool_results))
        elif isinstance(claim, DerivedClaim):
            results.append(verify_derived_claim(claim, tool_results))
        else:
            results.append(VerifiedClaim(claim, False, f"unknown_claim_type: {type(claim)}", ()))
    return results
