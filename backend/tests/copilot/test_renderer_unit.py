"""Proves the enforcement point stated in the authorization directly:
"no numeric value may appear in the final response unless it
originates from a verified claim." The renderer must exclude
unverified claims by construction, not merely by upstream convention.
"""

from app.copilot.citations import Citation
from app.copilot.claims import FactClaim
from app.copilot.renderer import render
from app.copilot.verifier import VerifiedClaim

_CITATION = Citation(
    citation_id="c1",
    endpoint="/api/v1/dashboards/planning/supplier-risk/summary",
    source_tables=("ds_supplier_risk_score",),
    model_id=7,
    etl_run_id=9,
)


def test_render_includes_only_verified_claims():
    verified = VerifiedClaim(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1"),
        True,
        "exact_match",
        (_CITATION,),
    )
    unverified = VerifiedClaim(
        FactClaim(metric_path="summary.avg_risk_score", value=999.0, citation_id="c1"),
        False,
        "value_mismatch: claimed 999.0, actual 42.7",
        (_CITATION,),
    )

    response = render([verified, unverified])

    assert "42.7" in response.answer
    assert "999.0" not in response.answer
    assert response.claim_count == 1


def test_render_with_zero_verified_claims_produces_empty_answer():
    unverified = VerifiedClaim(
        FactClaim(metric_path="x", value=1.0, citation_id="c1"),
        False,
        "value_mismatch",
        (_CITATION,),
    )
    response = render([unverified])
    assert response.answer == ""
    assert response.sources == ()
    assert response.claim_count == 0


def test_render_deduplicates_sources_across_claims():
    v1 = VerifiedClaim(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1"),
        True,
        "exact_match",
        (_CITATION,),
    )
    v2 = VerifiedClaim(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1"),
        True,
        "exact_match",
        (_CITATION,),
    )
    response = render([v1, v2])
    assert len(response.sources) == 1
    assert response.sources[0].citation_id == "c1"


def test_render_sources_are_only_from_verified_claims():
    other_citation = Citation(
        citation_id="c2",
        endpoint="/api/v1/dashboards/planning/inventory-policy/summary",
        source_tables=("ds_inventory_policy",),
    )
    verified = VerifiedClaim(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1"),
        True,
        "exact_match",
        (_CITATION,),
    )
    unverified_from_other_source = VerifiedClaim(
        FactClaim(metric_path="summary.avg_safety_stock", value=1.0, citation_id="c2"),
        False,
        "value_mismatch",
        (other_citation,),
    )
    response = render([verified, unverified_from_other_source])
    assert len(response.sources) == 1
    assert response.sources[0].citation_id == "c1"
