"""Versioned answer snapshots (authorization: "Add versioned answer
snapshots for a representative subset of evaluation questions so
regressions can be detected across future model or prompt changes").
tests/copilot/snapshots/answers.json is checked into the repo and
reviewed like a code change on any diff -- the same principle
docs/phase8-grounding-spec.md §5 applies to the eval sets themselves,
extended to their recorded outputs.

These snapshots are only exactly reproducible because the renderer is
a deterministic template over verified claims (app/copilot/renderer.py),
never a second LLM call -- if that ever changed, these tests would
(correctly) start failing on every run, not just on real regressions.
"""

import json
from pathlib import Path

from app.copilot.claims import DerivedClaim, FactClaim
from app.copilot.llm_client import FixtureClaimDraftingClient
from app.copilot.pipeline import FixtureToolRouter, ToolCall, answer_question
from tests.copilot.test_eval_harness import _seed_full_eval_dataset

_SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "answers.json"


def _load_snapshots() -> dict:
    return json.loads(_SNAPSHOT_PATH.read_text())


def test_supplier_risk_classification_snapshot(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)
    snapshot = _load_snapshots()["supplier_risk_classification"]
    question = snapshot["question"]

    router = FixtureToolRouter(
        {question: [ToolCall("get_supplier_risk", {"supplier_key": ids["supplier_key"]})]}
    )
    claims = {
        question: [
            FactClaim(metric_path="supplier.risk_classification", value="High", citation_id="c1")
        ]
    }
    result = answer_question(
        question, "supply_planner", router, FixtureClaimDraftingClient(claims), client
    )

    assert result.answer == snapshot["answer"]
    assert result.claim_count == snapshot["claim_count"]
    assert [s.endpoint for s in result.sources] == snapshot["source_endpoints"]


def test_inventory_safety_stock_snapshot(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)
    snapshot = _load_snapshots()["inventory_safety_stock"]
    question = snapshot["question"]

    router = FixtureToolRouter(
        {
            question: [
                ToolCall(
                    "get_inventory_recommendation",
                    {"product_key": ids["product_key"], "warehouse_key": ids["warehouse_key"]},
                )
            ]
        }
    )
    claims = {
        question: [
            FactClaim(metric_path="recommendation.safety_stock", value=18.0, citation_id="c1")
        ]
    }
    result = answer_question(
        question, "supply_planner", router, FixtureClaimDraftingClient(claims), client
    )

    assert result.answer == snapshot["answer"]
    assert result.claim_count == snapshot["claim_count"]
    assert [s.endpoint for s in result.sources] == snapshot["source_endpoints"]


def test_scenario_investment_delta_snapshot(client, olap_engine, seed_run):
    ids = _seed_full_eval_dataset(olap_engine, seed_run)
    snapshot = _load_snapshots()["scenario_investment_delta"]
    question = snapshot["question"]

    router = FixtureToolRouter(
        {question: [ToolCall("compare_scenarios", {"scenario_ids": [ids["scenario_id"]]})]}
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

    assert result.answer == snapshot["answer"]
    assert result.claim_count == snapshot["claim_count"]
    assert [s.endpoint for s in result.sources] == snapshot["source_endpoints"]
