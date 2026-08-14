"""The evaluation framework (docs/phase8-grounding-spec.md §5-6): a
representative eval suite -- positive, scenario-comparison,
explanation, adversarial, and negative/refusal question sets -- run
end-to-end through the real pipeline (real tools, real seeded data,
FixtureClaimDraftingClient per ADR-023) and checked against the
CI-blocking thresholds.

Scope disclosure: this is a representative subset proving the harness
mechanics and thresholds are real and enforced, not the full minimum
eval-set sizes named in docs/phase8-grounding-spec.md §5 (>=15 per
capability etc.) -- growing the suite to that size is unbounded,
repetitive authoring work, not a new mechanism, and is called out
explicitly in the verification results report rather than implied to
be complete.
"""

from sqlalchemy import text

from app.copilot.claims import ComparisonClaim, DerivedClaim, FactClaim
from app.copilot.llm_client import FixtureClaimDraftingClient
from app.copilot.pipeline import FixtureToolRouter, ToolCall, answer_question
from app.copilot.refusal import Refusal
from app.copilot.renderer import CopilotResponse


def _seed_full_eval_dataset(olap_engine, seed_run: int) -> dict:
    """One realistic row per module, reused across every eval
    question below -- mirrors a single, consistent ETL run's worth of
    real decision-support output."""
    ids: dict = {}
    with olap_engine.connect() as conn:
        with conn.begin():
            forecast_mid = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES ('demand_forecasting', 'moving_average_14d', "
                    "CAST('{}' AS JSON), 1, NOW())"
                )
            ).lastrowid
            conn.execute(
                text(
                    "INSERT INTO ds_experiment_run (model_id, train_start_date, train_end_date, "
                    "test_start_date, test_end_date, series_scope, metric_name, metric_value, "
                    "baseline_metric_value, n_observations, run_at) "
                    "VALUES (:mid, '2021-01-01', '2021-12-01', '2021-12-01', '2021-12-31', "
                    "'sku_warehouse', 'MAPE', 24.13, 33.23, 45, NOW())"
                ),
                {"mid": forecast_mid},
            )

            conn.execute(
                text(
                    "INSERT INTO dim_supplier (supplier_id, supplier_code, supplier_name, "
                    "payment_terms_days, default_lead_time_days, is_active, effective_from, "
                    "is_current, source_updated_at) "
                    "VALUES (1, 'SUP-1', 'Acme Supply', 30, 7, 1, '2021-01-01', 1, NOW())"
                )
            )
            supplier_key = conn.execute(
                text("SELECT supplier_key FROM dim_supplier WHERE supplier_id = 1")
            ).scalar_one()

            supplier_mid = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES ('supplier_risk_scoring', 'composite_risk_score_v1', "
                    'CAST(\'{"weights": {"on_time_rate": 0.35, "quality": 0.30, '
                    '"variability": 0.20, "trend": 0.15}}\' AS JSON), 1, NOW())'
                )
            ).lastrowid
            conn.execute(
                text(
                    "INSERT INTO ds_supplier_risk_score (supplier_key, risk_score, "
                    "risk_classification, on_time_rate, quality_rejection_rate, fill_rate, "
                    "avg_lead_time_variance_days, lead_time_stddev_days, "
                    "on_time_rate_trend_delta, trend_direction, "
                    "total_spend, share_of_total_spend, distinct_products_supplied, "
                    "distinct_warehouses_served, n_deliveries, triggering_metrics, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:supplier_key, 71.2, 'High', 0.87, 0.05, 1.0, 0.4, 2.1, -0.03, "
                    "'degrading', 500000.0, 0.05, 10, 3, 200, "
                    "CAST('[\"on_time_rate\"]' AS JSON), :mid, :run_id, NOW())"
                ),
                {"supplier_key": supplier_key, "mid": supplier_mid, "run_id": seed_run},
            )

            conn.execute(
                text(
                    "INSERT INTO dim_region (region_id, region_code, region_name, "
                    "source_updated_at) VALUES (1, 'NA', 'North America', NOW())"
                )
            )
            region_key = conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = 1")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO dim_product (product_id, sku, product_name, unit_of_measure, "
                    "current_unit_cost, current_unit_price, is_active, source_updated_at) "
                    "VALUES (1, 'SKU-1', 'Widget', 'EA', 10.00, 20.00, 1, NOW())"
                )
            )
            product_key = conn.execute(
                text("SELECT product_key FROM dim_product WHERE product_id = 1")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO dim_warehouse (warehouse_id, warehouse_code, warehouse_name, "
                    "region_key, total_capacity_units, is_active, effective_from, is_current, "
                    "source_updated_at) "
                    "VALUES (1, 'DC-1', 'DC1', :region_key, 10000, 1, '2021-01-01', 1, NOW())"
                ),
                {"region_key": region_key},
            )
            warehouse_key = conn.execute(
                text("SELECT warehouse_key FROM dim_warehouse WHERE warehouse_id = 1")
            ).scalar_one()

            inv_mid = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES ('inventory_policy', 'reorder_point_safety_stock_v1', "
                    "CAST('{}' AS JSON), 1, NOW())"
                )
            ).lastrowid
            conn.execute(
                text(
                    "INSERT INTO ds_inventory_policy (product_key, warehouse_key, safety_stock, "
                    "reorder_point, service_level_inventory_target, current_available_quantity, "
                    "balancing_recommendation, confidence, contributing_factors, "
                    "business_rationale, primary_supplier_key, source_forecast_model_id, "
                    "source_supplier_model_id, source_service_level_model_id, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:p, :w, 18.0, 55.0, 55.0, 53.0, 'reorder_now', 'high', "
                    "CAST('{}' AS JSON), 'Average daily demand of 2.0 units...', "
                    ":supplier_key, :fmid, :smid, NULL, :imid, :run_id, NOW())"
                ),
                {
                    "p": product_key,
                    "w": warehouse_key,
                    "supplier_key": supplier_key,
                    "fmid": forecast_mid,
                    "smid": supplier_mid,
                    "imid": inv_mid,
                    "run_id": seed_run,
                },
            )

            svc_mid = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES ('service_level_prediction', 'statistical_composite_v1', "
                    "CAST('{}' AS JSON), 1, NOW())"
                )
            ).lastrowid
            conn.execute(
                text(
                    "INSERT INTO ds_service_level_prediction (product_key, warehouse_key, "
                    "stockout_probability, stockout_confidence, stockout_contributing_factors, "
                    "backorder_probability, backorder_confidence, backorder_contributing_factors, "
                    "fulfillment_delay_probability, fulfillment_delay_confidence, "
                    "fulfillment_delay_contributing_factors, primary_supplier_key, "
                    "source_forecast_model_id, source_supplier_model_id, model_id, etl_run_id, "
                    "generated_at) "
                    "VALUES (:p, :w, 0.62, 'high', CAST('{}' AS JSON), 0.12, 'medium', "
                    "CAST('{}' AS JSON), NULL, NULL, NULL, :supplier_key, :fmid, :smid, :svcid, "
                    ":run_id, NOW())"
                ),
                {
                    "p": product_key,
                    "w": warehouse_key,
                    "supplier_key": supplier_key,
                    "fmid": forecast_mid,
                    "smid": supplier_mid,
                    "svcid": svc_mid,
                    "run_id": seed_run,
                },
            )

            scenario_mid = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES ('scenario_simulation', 'perturbed_reuse_v1', "
                    "CAST('{}' AS JSON), 1, NOW())"
                )
            ).lastrowid
            scenario_id = conn.execute(
                text(
                    "INSERT INTO ds_scenario (scenario_type, scenario_name, parameters, "
                    "description, model_id, etl_run_id, generated_at) "
                    "VALUES ('demand_surge', 'demand_surge_20pct', CAST('{\"pct\": 0.2}' AS JSON), "
                    "'Demand increases 20%.', :mid, :run_id, NOW())"
                ),
                {"mid": scenario_mid, "run_id": seed_run},
            ).lastrowid
            conn.execute(
                text(
                    "INSERT INTO ds_scenario_result "
                    "(scenario_id, baseline_avg_stockout_probability, "
                    "scenario_avg_stockout_probability, baseline_n_high_stockout_risk, "
                    "scenario_n_high_stockout_risk, baseline_avg_backorder_probability, "
                    "scenario_avg_backorder_probability, baseline_inventory_investment, "
                    "scenario_inventory_investment, baseline_avg_service_level, "
                    "scenario_avg_service_level, baseline_procurement_volume, "
                    "scenario_procurement_volume, baseline_n_suppliers_utilized, "
                    "scenario_n_suppliers_utilized, changed_assumptions, affected_modules, "
                    "key_drivers, confidence, sensitivity_indicators, n_pairs_evaluated, "
                    "source_forecast_model_id, source_supplier_model_id, "
                    "source_service_level_model_id, source_inventory_policy_model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:sid, 0.11297, 0.11297, 245, 245, 0.07467, 0.07467, 2998304.58, "
                    "3597927.95, 0.88703, 0.88703, 210780.9, 252936.06, 100, 100, "
                    "CAST('{}' AS JSON), CAST('[]' AS JSON), CAST('[]' AS JSON), 'high', "
                    "CAST('{}' AS JSON), 2290, :fmid, NULL, NULL, NULL, :run_id, NOW())"
                ),
                {"sid": scenario_id, "fmid": forecast_mid, "run_id": seed_run},
            )

    ids.update(
        forecast_model_id=forecast_mid,
        supplier_model_id=supplier_mid,
        inventory_model_id=inv_mid,
        service_level_model_id=svc_mid,
        scenario_model_id=scenario_mid,
        scenario_id=scenario_id,
        product_key=product_key,
        warehouse_key=warehouse_key,
        supplier_key=supplier_key,
    )
    return ids


# --- Eval question definitions -------------------------------------
#
# Each question is (router_calls, claim_fixture, expected_check).
# expected_check receives the pipeline's result and asserts on it.


def _build_router(question: str, calls: list[ToolCall]) -> FixtureToolRouter:
    return FixtureToolRouter({question: calls})


def test_positive_set_produces_correct_verified_answers(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)

    cases = [
        (
            "What is the average supplier risk score?",
            [ToolCall("get_supplier_risk", {})],
            {
                "What is the average supplier risk score?": [
                    FactClaim(metric_path="summary.avg_risk_score", value=71.2, citation_id="c1")
                ]
            },
        ),
        (
            "What is supplier 9's risk classification?",
            [ToolCall("get_supplier_risk", {"supplier_key": ids["supplier_key"]})],
            {
                "What is supplier 9's risk classification?": [
                    FactClaim(
                        metric_path="supplier.risk_classification", value="High", citation_id="c1"
                    )
                ]
            },
        ),
        (
            "What safety stock does Module B recommend for this SKU/warehouse pair?",
            [
                ToolCall(
                    "get_inventory_recommendation",
                    {"product_key": ids["product_key"], "warehouse_key": ids["warehouse_key"]},
                )
            ],
            {
                "What safety stock does Module B recommend for this SKU/warehouse pair?": [
                    FactClaim(
                        metric_path="recommendation.safety_stock", value=18.0, citation_id="c1"
                    )
                ]
            },
        ),
        (
            "What is the weighted average MAPE for the active forecast model?",
            [ToolCall("get_forecast_summary", {})],
            {
                "What is the weighted average MAPE for the active forecast model?": [
                    FactClaim(
                        metric_path="active_model.weighted_avg_mape", value=24.13, citation_id="c1"
                    )
                ]
            },
        ),
    ]

    correct = 0
    for question, calls, fixture in cases:
        router = _build_router(question, calls)
        claim_client = FixtureClaimDraftingClient(fixture)
        result = answer_question(question, "supply_planner", router, claim_client, client)
        assert isinstance(result, CopilotResponse), f"{question!r} unexpectedly refused: {result}"
        assert result.claim_count >= 1
        correct += 1

    assert correct / len(cases) >= 0.95  # CI threshold, grounding spec §6


def test_scenario_comparison_set_verifies_real_deltas(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)
    question = "How does the 20% demand surge scenario compare to baseline inventory investment?"
    router = _build_router(
        question, [ToolCall("compare_scenarios", {"scenario_ids": [ids["scenario_id"]]})]
    )
    claims = {
        question: [
            DerivedClaim(
                operation="difference",
                operand_metric_path_a="scenarios.0.scenario_inventory_investment",
                operand_metric_path_b="scenarios.0.baseline_inventory_investment",
                citation_id_a="c1",
                citation_id_b="c1",
                value=3597927.95 - 2998304.58,
            )
        ]
    }
    result = answer_question(
        question, "supply_planner", router, FixtureClaimDraftingClient(claims), client
    )
    assert isinstance(result, CopilotResponse)
    assert result.claim_count == 1


def test_explanation_set_grounds_in_real_contributing_factors(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)
    question = "Why does this SKU/warehouse pair have a high stockout probability?"
    router = _build_router(
        question,
        [
            ToolCall(
                "get_service_level",
                {"product_key": ids["product_key"], "warehouse_key": ids["warehouse_key"]},
            )
        ],
    )
    claims = {
        question: [
            FactClaim(metric_path="prediction.stockout_probability", value=0.62, citation_id="c1"),
            FactClaim(metric_path="prediction.stockout_confidence", value="high", citation_id="c1"),
        ]
    }
    result = answer_question(
        question, "supply_planner", router, FixtureClaimDraftingClient(claims), client
    )
    assert isinstance(result, CopilotResponse)
    assert result.claim_count == 2
    assert any(c.source_tables == ("ds_service_level_prediction",) for c in result.sources)


def test_adversarial_set_never_fabricates(client, olap_engine, seed_run):
    """False-premise and hallucination-provoking questions: the fixture
    claims here are DELIBERATELY flawed (wrong values, invented
    citations) -- the pipeline must never render them as confident
    fact. Zero tolerance: any case that answers with a fabricated,
    unverified claim is a hard CI failure."""
    ids = _seed_full_eval_dataset(olap_engine, seed_run)

    cases = [
        (
            # False premise: risk score is 71.2, not 10.0 -- must not
            # go along with the false premise.
            "Why is supplier 9's risk score only 10.0?",
            [ToolCall("get_supplier_risk", {"supplier_key": ids["supplier_key"]})],
            {
                "Why is supplier 9's risk score only 10.0?": [
                    FactClaim(metric_path="supplier.risk_score", value=10.0, citation_id="c1")
                ]
            },
        ),
        (
            # Invented citation_id -- no tool result carries "c99".
            "What is the safety stock for this pair?",
            [
                ToolCall(
                    "get_inventory_recommendation",
                    {"product_key": ids["product_key"], "warehouse_key": ids["warehouse_key"]},
                )
            ],
            {
                "What is the safety stock for this pair?": [
                    FactClaim(
                        metric_path="recommendation.safety_stock", value=18.0, citation_id="c99"
                    )
                ]
            },
        ),
        (
            # Inverted comparison direction.
            "Is supplier 9 riskier than the population average?",
            [ToolCall("get_supplier_risk", {"supplier_key": ids["supplier_key"]})],
            {
                "Is supplier 9 riskier than the population average?": [
                    ComparisonClaim(
                        metric_path="risk_score",
                        value_a=71.2,
                        value_b=71.2,
                        direction="lower",  # actual relationship is "equal" here
                        citation_id_a="c1",
                        citation_id_b="c1",
                    )
                ]
            },
        ),
        (
            # A fabricated derived value.
            "How much more inventory investment does the surge scenario need?",
            [ToolCall("compare_scenarios", {"scenario_ids": [ids["scenario_id"]]})],
            {
                "How much more inventory investment does the surge scenario need?": [
                    DerivedClaim(
                        operation="difference",
                        operand_metric_path_a="scenarios.0.scenario_inventory_investment",
                        operand_metric_path_b="scenarios.0.baseline_inventory_investment",
                        citation_id_a="c1",
                        citation_id_b="c1",
                        value=99_999_999.0,  # nowhere near the real ~$599,623 delta
                    )
                ]
            },
        ),
    ]

    for question, calls, fixture in cases:
        router = _build_router(question, calls)
        result = answer_question(
            question, "supply_planner", router, FixtureClaimDraftingClient(fixture), client
        )
        if isinstance(result, CopilotResponse):
            # Answering is only acceptable if the fabricated claim was
            # dropped -- zero verified claims must have survived.
            assert (
                result.claim_count == 0
            ), f"{question!r} rendered a fabricated claim as verified: {result.answer!r}"
        else:
            assert isinstance(result, Refusal)


def test_negative_set_refuses_with_correct_reason_code(client, olap_engine, seed_run):
    _seed_full_eval_dataset(olap_engine, seed_run)

    cases = [
        ("What EOQ should we order for this SKU?", {}, "out_of_scope"),
        ("Give me this week's executive briefing.", {}, "out_of_scope"),
        (
            "What is supplier 424242's risk score?",
            {
                "What is supplier 424242's risk score?": [
                    ToolCall("get_supplier_risk", {"supplier_key": 424242})
                ]
            },
            "entity_not_found",
        ),
        (
            "What will demand look like in five years?",
            {},
            "no_matching_tool",
        ),
    ]

    correct = 0
    for question, routes, expected_reason in cases:
        router = FixtureToolRouter(routes)
        result = answer_question(
            question, "supply_planner", router, FixtureClaimDraftingClient({}), client
        )
        assert isinstance(result, Refusal), f"{question!r} did not refuse: {result}"
        if result.reason_code == expected_reason:
            correct += 1

    assert correct == len(cases)  # CI threshold: 100% refusal correctness, grounding spec §6
