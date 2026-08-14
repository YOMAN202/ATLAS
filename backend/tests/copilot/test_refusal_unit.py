"""Proves refusal reason_code selection is deterministic and correct
-- the property the eval harness's negative/adversarial sets
ultimately depend on (docs/phase8-grounding-spec.md §4-5)."""

from app.copilot.claims import FactClaim
from app.copilot.refusal import check_out_of_scope, decide_refusal
from app.copilot.verifier import VerifiedClaim


def test_out_of_scope_detects_eoq():
    result = check_out_of_scope("What EOQ should we order for SKU-4231?")
    assert result is not None
    assert result.reason_code == "out_of_scope"


def test_out_of_scope_detects_executive_briefing():
    result = check_out_of_scope("Give me an executive briefing for this week.")
    assert result is not None
    assert result.reason_code == "out_of_scope"


def test_out_of_scope_returns_none_for_in_scope_question():
    result = check_out_of_scope("Why does SKU-4231 have a high stockout probability?")
    assert result is None


def test_decide_refusal_no_matching_tool_when_no_results():
    refusal = decide_refusal(verified_claims=[], had_tool_results=False, entity_missing=False)
    assert refusal is not None
    assert refusal.reason_code == "no_matching_tool"


def test_decide_refusal_entity_not_found():
    refusal = decide_refusal(verified_claims=[], had_tool_results=True, entity_missing=True)
    assert refusal is not None
    assert refusal.reason_code == "entity_not_found"


def test_decide_refusal_insufficient_verified_evidence():
    unverified = VerifiedClaim(
        FactClaim(metric_path="x", value=1.0, citation_id="c1"), False, "value_mismatch", ()
    )
    refusal = decide_refusal(
        verified_claims=[unverified], had_tool_results=True, entity_missing=False
    )
    assert refusal is not None
    assert refusal.reason_code == "insufficient_verified_evidence"


def test_decide_refusal_returns_none_when_evidence_exists():
    verified = VerifiedClaim(
        FactClaim(metric_path="x", value=1.0, citation_id="c1"), True, "exact_match", ()
    )
    refusal = decide_refusal(
        verified_claims=[verified], had_tool_results=True, entity_missing=False
    )
    assert refusal is None
