"""Proves the Planning dashboard's scenario simulation endpoints
against known, hand-seeded ds_model_registry/ds_scenario/
ds_scenario_result rows — the same reconciliation discipline every
other Phase 7 module's API test uses.
"""

import json

import pytest
from sqlalchemy import text


def _seed_model(olap_engine, is_active: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO ds_model_registry "
                    "(module, model_name, parameters, is_active, created_at) "
                    "VALUES ('scenario_simulation', 'perturbed_reuse_v1', "
                    ":params, :is_active, NOW())"
                ),
                {"params": json.dumps({"formula": "test"}), "is_active": is_active},
            )
            return result.lastrowid


def _seed_scenario(olap_engine, model_id, run_id, **overrides) -> int:
    row = {
        "scenario_type": "demand_surge",
        "scenario_name": "demand_surge_20pct",
        "parameters": json.dumps({"pct": 0.2}),
        "description": "Demand increases 20% across all pairs.",
        "model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO ds_scenario "
                    "(scenario_type, scenario_name, parameters, description, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:scenario_type, :scenario_name, CAST(:parameters AS JSON), "
                    ":description, :model_id, :etl_run_id, NOW())"
                ),
                row,
            )
            return result.lastrowid


def _seed_result(olap_engine, scenario_id, model_id, run_id, **overrides) -> None:
    row = {
        "scenario_id": scenario_id,
        "baseline_avg_stockout_probability": 0.11297,
        "scenario_avg_stockout_probability": 0.11297,
        "baseline_n_high_stockout_risk": 245,
        "scenario_n_high_stockout_risk": 245,
        "baseline_avg_backorder_probability": 0.07467,
        "scenario_avg_backorder_probability": 0.07467,
        "baseline_inventory_investment": 2998304.58,
        "scenario_inventory_investment": 3597927.95,
        "baseline_avg_service_level": 0.88703,
        "scenario_avg_service_level": 0.88703,
        "baseline_procurement_volume": 210780.9,
        "scenario_procurement_volume": 252936.06,
        "baseline_n_suppliers_utilized": 100,
        "scenario_n_suppliers_utilized": 100,
        "changed_assumptions": json.dumps({"scenario_type": "demand_surge", "pct": 0.2}),
        "affected_modules": json.dumps(
            ["demand_forecasting", "service_level_prediction", "inventory_policy"]
        ),
        "key_drivers": json.dumps(["inventory_investment moved from 2998305 to 3597928"]),
        "confidence": "high",
        "sensitivity_indicators": json.dumps(
            {"stockout_probability_delta": 0.0, "investment_delta": 599623.37}
        ),
        "n_pairs_evaluated": 2290,
        "source_forecast_model_id": model_id,
        "source_supplier_model_id": model_id,
        "source_service_level_model_id": model_id,
        "source_inventory_policy_model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
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
                    "VALUES (:scenario_id, :baseline_avg_stockout_probability, "
                    ":scenario_avg_stockout_probability, :baseline_n_high_stockout_risk, "
                    ":scenario_n_high_stockout_risk, :baseline_avg_backorder_probability, "
                    ":scenario_avg_backorder_probability, :baseline_inventory_investment, "
                    ":scenario_inventory_investment, :baseline_avg_service_level, "
                    ":scenario_avg_service_level, :baseline_procurement_volume, "
                    ":scenario_procurement_volume, :baseline_n_suppliers_utilized, "
                    ":scenario_n_suppliers_utilized, CAST(:changed_assumptions AS JSON), "
                    "CAST(:affected_modules AS JSON), CAST(:key_drivers AS JSON), :confidence, "
                    "CAST(:sensitivity_indicators AS JSON), :n_pairs_evaluated, "
                    ":source_forecast_model_id, :source_supplier_model_id, "
                    ":source_service_level_model_id, :source_inventory_policy_model_id, "
                    ":etl_run_id, NOW())"
                ),
                row,
            )


def test_scenario_list_reconciles_to_seeded_rows(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    s1 = _seed_scenario(olap_engine, model_id, seed_run)
    _seed_result(olap_engine, s1, model_id, seed_run)

    resp = client.get(
        "/api/v1/dashboards/planning/scenarios/list",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == s1
    assert body[0]["scenario_name"] == "demand_surge_20pct"
    assert body[0]["stockout_probability_delta"] == 0.0
    assert body[0]["investment_delta"] == pytest.approx(599623.37)


def test_scenario_compare_returns_requested_ids_only(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    s1 = _seed_scenario(olap_engine, model_id, seed_run)
    s2 = _seed_scenario(
        olap_engine,
        model_id,
        seed_run,
        scenario_type="warehouse_outage",
        scenario_name="warehouse_outage_severe",
        description="Severe warehouse outage.",
        parameters=json.dumps({"outage_pct": 1.0}),
    )
    _seed_result(olap_engine, s1, model_id, seed_run)
    _seed_result(
        olap_engine,
        s2,
        model_id,
        seed_run,
        scenario_avg_stockout_probability=0.23434,
        scenario_avg_service_level=0.76566,
        scenario_inventory_investment=2998304.58,
    )

    resp = client.get(
        "/api/v1/dashboards/planning/scenarios/compare",
        params={"ids": f"{s1},{s2}"},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body] == [s1, s2]
    assert body[1]["scenario_avg_stockout_probability"] == 0.23434


def test_scenario_detail_returns_full_row(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    s1 = _seed_scenario(olap_engine, model_id, seed_run)
    _seed_result(olap_engine, s1, model_id, seed_run)

    resp = client.get(
        f"/api/v1/dashboards/planning/scenarios/{s1}",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == s1
    assert body["key_drivers"] == ["inventory_investment moved from 2998305 to 3597928"]
    assert body["affected_modules"] == [
        "demand_forecasting",
        "service_level_prediction",
        "inventory_policy",
    ]


def test_scenario_detail_404_for_unknown_id(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/scenarios/999999",
        headers={"X-Atlas-Role": "supply_planner"},
    )
    assert resp.status_code == 404


def test_scenario_dashboard_rejects_executive_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/scenarios/list",
        headers={"X-Atlas-Role": "executive"},
    )
    assert resp.status_code == 403


def test_scenario_dashboard_allows_administrator(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    s1 = _seed_scenario(olap_engine, model_id, seed_run)
    _seed_result(olap_engine, s1, model_id, seed_run)

    resp = client.get(
        "/api/v1/dashboards/planning/scenarios/list",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
