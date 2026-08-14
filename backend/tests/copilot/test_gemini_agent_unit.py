"""Pure-logic tests for the Gemini provider's claim-parsing and
tool-dispatch helpers (app/copilot/gemini_agent.py) -- no network, no
GEMINI_API_KEY required, so these run in the same CI-blocking gate as
every other copilot test. Mirrors ADR-023's precedent: the LLM call
itself is never unit-tested against a mock (that proves nothing about
the real API); only the deterministic parsing/dispatch code around it
is.
"""

import pytest

from app.copilot.claims import ComparisonClaim, DerivedClaim, FactClaim
from app.copilot.gemini_agent import GeminiClaimDraftingClient, _claim_from_dict, _execute_tool_call
from app.copilot.tools import ToolError
from app.core.config import settings


def test_claim_from_dict_parses_fact_claim():
    claim = _claim_from_dict(
        {
            "claim_type": "fact",
            "metric_path": "summary.avg_risk_score",
            "value": 42.7,
            "citation_id": "c1",
        }
    )
    assert claim == FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1")


def test_claim_from_dict_parses_comparison_claim():
    claim = _claim_from_dict(
        {
            "claim_type": "comparison",
            "metric_path": "supplier.risk_score",
            "value_a": 71.2,
            "value_b": 18.4,
            "direction": "higher",
            "citation_id_a": "c1",
            "citation_id_b": "c2",
        }
    )
    assert claim == ComparisonClaim(
        metric_path="supplier.risk_score",
        value_a=71.2,
        value_b=18.4,
        direction="higher",
        citation_id_a="c1",
        citation_id_b="c2",
    )


def test_claim_from_dict_parses_derived_claim():
    claim = _claim_from_dict(
        {
            "claim_type": "derived",
            "operation": "difference",
            "operand_metric_path_a": "a.x",
            "operand_metric_path_b": "b.y",
            "citation_id_a": "c1",
            "citation_id_b": "c2",
            "value": 10.0,
        }
    )
    assert claim == DerivedClaim(
        operation="difference",
        operand_metric_path_a="a.x",
        operand_metric_path_b="b.y",
        citation_id_a="c1",
        citation_id_b="c2",
        value=10.0,
    )


def test_claim_from_dict_missing_required_field_returns_none():
    # A fact claim missing "value" -- a malformed submit_claims argument
    # from the model must be dropped, never crash the pipeline.
    claim = _claim_from_dict({"claim_type": "fact", "metric_path": "x", "citation_id": "c1"})
    assert claim is None


def test_claim_from_dict_unknown_claim_type_returns_none():
    claim = _claim_from_dict({"claim_type": "not_a_real_type"})
    assert claim is None


def test_claim_from_dict_missing_claim_type_returns_none():
    claim = _claim_from_dict({"metric_path": "x", "value": 1, "citation_id": "c1"})
    assert claim is None


def test_execute_tool_call_unknown_tool_raises_tool_error():
    with pytest.raises(ToolError, match="unknown_tool"):
        _execute_tool_call(
            "not_a_real_tool", {}, http_client=None, role="administrator", citation_id="c1"
        )


def test_gemini_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    with pytest.raises(RuntimeError, match="gemini_api_key"):
        GeminiClaimDraftingClient()
