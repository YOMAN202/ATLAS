"""The CI-blocking gate itself (docs/phase8-grounding-spec.md §6:
"Verifier self-test accuracy... 100%"). Every case here is a
synthetic, hand-constructed claim with a known-correct verdict --
some deliberately good, some deliberately flawed (wrong value, wrong
citation, inverted comparison, wrong derived arithmetic) -- because
the verifier's entire job is catching the bad ones, and that can only
be proven by feeding it some.
"""

from app.copilot.citations import Citation, ToolResult
from app.copilot.claims import ComparisonClaim, DerivedClaim, FactClaim
from app.copilot.verifier import _extract_path, verify_claims

_CITATION_A = Citation(
    citation_id="c1",
    endpoint="/api/v1/dashboards/planning/supplier-risk/summary",
    source_tables=("ds_supplier_risk_score",),
    model_id=7,
    model_name="composite_risk_score_v1",
    etl_run_id=9,
    generated_at="2026-08-14 01:00:00",
)
_CITATION_B = Citation(
    citation_id="c2",
    endpoint="/api/v1/dashboards/planning/inventory-policy/summary",
    source_tables=("ds_inventory_policy",),
    model_id=9,
    model_name="reorder_point_safety_stock_v1",
    etl_run_id=9,
    generated_at="2026-08-14 01:05:00",
)

_CITATION_C = Citation(
    citation_id="c3",
    endpoint="/api/v1/dashboards/planning/scenarios/compare",
    source_tables=("ds_scenario_result",),
    source_forecast_model_id=4,
    etl_run_id=9,
    generated_at="2026-08-14 01:17:35",
)

_TOOL_RESULTS = [
    ToolResult(
        tool_name="get_supplier_risk",
        payload={"summary": {"avg_risk_score": 42.7, "n_suppliers": 100, "model_name": "x"}},
        citation=_CITATION_A,
    ),
    ToolResult(
        tool_name="get_inventory_recommendation",
        payload={"summary": {"avg_safety_stock": 13.3, "n_recommendations": 2290}},
        citation=_CITATION_B,
    ),
    ToolResult(
        tool_name="compare_scenarios",
        payload={"scenario_inventory_investment": 4497458.60},
        citation=_CITATION_C,
    ),
    ToolResult(
        tool_name="get_supplier_risk",
        payload={"supplier": {"supplier_key": 5, "risk_score": 71.2}},
        citation=Citation(
            citation_id="c4",
            endpoint="/api/v1/dashboards/planning/supplier-risk/detail",
            source_tables=("ds_supplier_risk_score",),
            model_id=7,
            etl_run_id=9,
        ),
    ),
    ToolResult(
        tool_name="get_supplier_risk",
        payload={"supplier": {"supplier_key": 9, "risk_score": 18.4}},
        citation=Citation(
            citation_id="c5",
            endpoint="/api/v1/dashboards/planning/supplier-risk/detail",
            source_tables=("ds_supplier_risk_score",),
            model_id=7,
            etl_run_id=9,
        ),
    ),
]


def _verified(claim):
    return verify_claims([claim], _TOOL_RESULTS)[0]


# --- FactClaim ---


def test_fact_claim_exact_match_is_verified():
    result = _verified(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1")
    )
    assert result.verified is True
    assert result.reason == "exact_match"


def test_fact_claim_within_tolerance_is_verified():
    # 42.71 vs actual 42.7 -- within the 0.5% relative / 0.01 absolute tolerance band.
    result = _verified(
        FactClaim(metric_path="summary.avg_risk_score", value=42.705, citation_id="c1")
    )
    assert result.verified is True


def test_fact_claim_wrong_value_is_rejected():
    result = _verified(
        FactClaim(metric_path="summary.avg_risk_score", value=99.9, citation_id="c1")
    )
    assert result.verified is False
    assert "value_mismatch" in result.reason


def test_fact_claim_unknown_citation_is_rejected():
    result = _verified(
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c99")
    )
    assert result.verified is False
    assert result.reason == "citation_not_found"


def test_fact_claim_unknown_metric_path_is_rejected():
    result = _verified(
        FactClaim(metric_path="summary.nonexistent_field", value=1.0, citation_id="c1")
    )
    assert result.verified is False
    assert "metric_path_not_found" in result.reason


def test_fact_claim_string_value_exact_match_is_verified():
    result = _verified(FactClaim(metric_path="summary.model_name", value="x", citation_id="c1"))
    assert result.verified is True


def test_fact_claim_string_value_mismatch_is_rejected():
    result = _verified(FactClaim(metric_path="summary.model_name", value="y", citation_id="c1"))
    assert result.verified is False


# --- ComparisonClaim ---


def test_comparison_claim_across_two_real_entities_correct_direction_is_verified():
    result = _verified(
        ComparisonClaim(
            metric_path="supplier.risk_score",
            value_a=71.2,
            value_b=18.4,
            direction="higher",
            citation_id_a="c4",
            citation_id_b="c5",
        )
    )
    assert result.verified is True
    assert result.reason == "direction_confirmed"


def test_comparison_claim_across_two_real_entities_inverted_is_rejected():
    result = _verified(
        ComparisonClaim(
            metric_path="supplier.risk_score",
            value_a=71.2,
            value_b=18.4,
            direction="lower",
            citation_id_a="c4",
            citation_id_b="c5",
        )
    )
    assert result.verified is False
    assert "direction_mismatch" in result.reason


def test_comparison_claim_same_metric_correct_direction_is_verified():
    result = _verified(
        ComparisonClaim(
            metric_path="summary.avg_safety_stock",
            value_a=13.3,
            value_b=13.3,
            direction="equal",
            citation_id_a="c2",
            citation_id_b="c2",
        )
    )
    assert result.verified is True
    assert result.reason == "direction_confirmed"


def test_comparison_claim_inverted_direction_is_rejected():
    result = _verified(
        ComparisonClaim(
            metric_path="summary.avg_safety_stock",
            value_a=13.3,
            value_b=13.3,
            direction="higher",
            citation_id_a="c2",
            citation_id_b="c2",
        )
    )
    assert result.verified is False
    assert "direction_mismatch" in result.reason


def test_comparison_claim_wrong_underlying_value_is_rejected():
    result = _verified(
        ComparisonClaim(
            metric_path="summary.avg_safety_stock",
            value_a=999.0,
            value_b=13.3,
            direction="higher",
            citation_id_a="c2",
            citation_id_b="c2",
        )
    )
    assert result.verified is False
    assert result.reason == "value_mismatch"


def test_comparison_claim_unknown_citation_is_rejected():
    result = _verified(
        ComparisonClaim(
            metric_path="summary.avg_safety_stock",
            value_a=13.3,
            value_b=13.3,
            direction="equal",
            citation_id_a="c2",
            citation_id_b="c404",
        )
    )
    assert result.verified is False
    assert result.reason == "citation_not_found"


# --- DerivedClaim ---


def test_derived_difference_is_verified():
    result = _verified(
        DerivedClaim(
            operation="difference",
            operand_metric_path_a="summary.avg_risk_score",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=42.7 - 13.3,
        )
    )
    assert result.verified is True
    assert result.reason == "derived_value_confirmed"


def test_derived_sum_is_verified():
    result = _verified(
        DerivedClaim(
            operation="sum",
            operand_metric_path_a="summary.avg_risk_score",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=42.7 + 13.3,
        )
    )
    assert result.verified is True


def test_derived_pct_delta_is_verified():
    expected = (42.7 - 13.3) / 13.3 * 100
    result = _verified(
        DerivedClaim(
            operation="pct_delta",
            operand_metric_path_a="summary.avg_risk_score",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=expected,
        )
    )
    assert result.verified is True


def test_derived_wrong_value_is_rejected():
    result = _verified(
        DerivedClaim(
            operation="difference",
            operand_metric_path_a="summary.avg_risk_score",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=1_000_000.0,
        )
    )
    assert result.verified is False
    assert "derived_value_mismatch" in result.reason


def test_derived_unknown_operation_is_rejected():
    result = _verified(
        DerivedClaim(
            operation="multiply",  # not a supported operation
            operand_metric_path_a="summary.avg_risk_score",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=1.0,
        )
    )
    assert result.verified is False
    assert "unknown_operation" in result.reason


def test_derived_missing_operand_is_rejected():
    result = _verified(
        DerivedClaim(
            operation="difference",
            operand_metric_path_a="summary.does_not_exist",
            operand_metric_path_b="summary.avg_safety_stock",
            citation_id_a="c1",
            citation_id_b="c2",
            value=1.0,
        )
    )
    assert result.verified is False
    assert result.reason == "operand_not_found"


def test_verify_claims_processes_a_mixed_batch_independently():
    claims = [
        FactClaim(metric_path="summary.avg_risk_score", value=42.7, citation_id="c1"),
        FactClaim(metric_path="summary.avg_risk_score", value=999.0, citation_id="c1"),
    ]
    results = verify_claims(claims, _TOOL_RESULTS)
    assert [r.verified for r in results] == [True, False]


# --- _extract_path list indexing (Module E scenario-comparison paths) ---


def test_extract_path_resolves_a_list_index():
    payload = {"scenarios": [{"scenario_inventory_investment": 3597927.95}]}
    assert _extract_path(payload, "scenarios.0.scenario_inventory_investment") == 3597927.95


def test_extract_path_out_of_range_index_returns_none():
    payload = {"scenarios": [{"x": 1}]}
    assert _extract_path(payload, "scenarios.1.x") is None


def test_extract_path_non_numeric_segment_against_a_list_returns_none():
    payload = {"scenarios": [{"x": 1}]}
    assert _extract_path(payload, "scenarios.not_a_number.x") is None


def test_scenario_comparison_derived_claim_resolves_list_indexed_operands():
    citation = Citation(
        citation_id="c1",
        endpoint="/api/v1/dashboards/planning/scenarios/compare",
        source_tables=("ds_scenario_result",),
    )
    tool_results = [
        ToolResult(
            tool_name="compare_scenarios",
            payload={
                "scenarios": [
                    {
                        "baseline_inventory_investment": 2998304.58,
                        "scenario_inventory_investment": 3597927.95,
                    }
                ]
            },
            citation=citation,
        )
    ]
    claim = DerivedClaim(
        operation="difference",
        operand_metric_path_a="scenarios.0.scenario_inventory_investment",
        operand_metric_path_b="scenarios.0.baseline_inventory_investment",
        citation_id_a="c1",
        citation_id_b="c1",
        value=3597927.95 - 2998304.58,
    )
    result = verify_claims([claim], tool_results)[0]
    assert result.verified is True
