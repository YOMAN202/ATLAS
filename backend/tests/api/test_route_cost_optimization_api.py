"""Proves the Planning dashboard's route/cost optimization endpoints
against known, hand-seeded ds_model_registry/ds_optimization_recommendation
rows — the same reconciliation discipline every other Phase 7 module's
API test uses.
"""

import json

from sqlalchemy import text


def _seed_model(olap_engine, is_active: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO ds_model_registry "
                    "(module, model_name, parameters, is_active, created_at) "
                    "VALUES ('route_cost_optimization', "
                    "'vehicle_right_sizing_and_consolidation_v1', :params, :is_active, NOW())"
                ),
                {
                    "params": json.dumps(
                        {
                            "analysis_window_start": "2021-12-02",
                            "analysis_window_end": "2021-12-31",
                        }
                    ),
                    "is_active": is_active,
                },
            )
            return result.lastrowid


def _seed_region(olap_engine, region_id: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_region "
                    "(region_id, region_code, region_name, source_updated_at) "
                    "VALUES (:rid, 'NA', 'North America', NOW())"
                ),
                {"rid": region_id},
            )
            return conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = :rid"), {"rid": region_id}
            ).scalar_one()


def _seed_warehouse(olap_engine, region_key: int, warehouse_id: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_warehouse "
                    "(warehouse_id, warehouse_code, warehouse_name, region_key, "
                    "total_capacity_units, is_active, effective_from, is_current, "
                    "source_updated_at) "
                    "VALUES (:wid, :code, 'DC1', :region_key, 10000, 1, '2021-01-01', 1, NOW())"
                ),
                {"wid": warehouse_id, "code": f"DC-{warehouse_id}", "region_key": region_key},
            )
            return conn.execute(
                text("SELECT warehouse_key FROM dim_warehouse WHERE warehouse_id = :wid"),
                {"wid": warehouse_id},
            ).scalar_one()


def _seed_recommendation(olap_engine, warehouse_key, model_id, run_id, **overrides) -> None:
    row = {
        "recommendation_type": "right_sizing",
        "origin_warehouse_key": warehouse_key,
        "shipment_date": "2021-12-05",
        "shipment_numbers": json.dumps(["SHIP-2021-12-05-00000001"]),
        "total_quantity": 300,
        "distance_miles": 100.0,
        "current_vehicle_type_code": "SEMI_TRAILER",
        "current_total_cost": 250.0,
        "recommended_vehicle_type_code": "VAN",
        "recommended_total_cost": 110.0,
        "estimated_savings": 140.0,
        "confidence": "high",
        "contributing_factors": json.dumps({"total_quantity": 300}),
        "business_rationale": "This shipment used a SEMI_TRAILER but a VAN would suffice...",
        "model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_optimization_recommendation "
                    "(recommendation_type, origin_warehouse_key, shipment_date, "
                    "shipment_numbers, total_quantity, distance_miles, "
                    "current_vehicle_type_code, current_total_cost, "
                    "recommended_vehicle_type_code, recommended_total_cost, estimated_savings, "
                    "confidence, contributing_factors, business_rationale, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:recommendation_type, :origin_warehouse_key, :shipment_date, "
                    "CAST(:shipment_numbers AS JSON), :total_quantity, :distance_miles, "
                    ":current_vehicle_type_code, :current_total_cost, "
                    ":recommended_vehicle_type_code, :recommended_total_cost, "
                    ":estimated_savings, :confidence, CAST(:contributing_factors AS JSON), "
                    ":business_rationale, :model_id, :etl_run_id, NOW())"
                ),
                row,
            )


def test_optimization_summary_reconciles_to_seeded_recommendations(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_recommendation(
        olap_engine,
        w1,
        model_id,
        seed_run,
        recommendation_type="right_sizing",
        estimated_savings=140.0,
    )
    _seed_recommendation(
        olap_engine,
        w1,
        model_id,
        seed_run,
        recommendation_type="consolidation",
        estimated_savings=132.0,
        shipment_numbers=json.dumps(["SHIP-A", "SHIP-B"]),
    )

    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/summary",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == model_id
    assert body["n_right_sizing_recommendations"] == 1
    assert body["n_consolidation_recommendations"] == 1
    assert body["total_estimated_savings"] == 272.0
    assert body["right_sizing_estimated_savings"] == 140.0
    assert body["consolidation_estimated_savings"] == 132.0
    assert body["analysis_window_start"] == "2021-12-02"


def test_optimization_summary_with_no_active_model_returns_null(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] is None
    assert body["n_right_sizing_recommendations"] == 0


def test_warehouse_impact_groups_by_origin_warehouse(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    w2 = _seed_warehouse(olap_engine, region_key, 2)
    _seed_recommendation(olap_engine, w1, model_id, seed_run, estimated_savings=100.0)
    _seed_recommendation(olap_engine, w2, model_id, seed_run, estimated_savings=500.0)

    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/warehouse-impact",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["origin_warehouse_key"] == w2  # highest savings first
    assert body[0]["total_estimated_savings"] == 500.0


def test_optimization_detail_filters_by_recommendation_type(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_recommendation(olap_engine, w1, model_id, seed_run, recommendation_type="right_sizing")
    _seed_recommendation(
        olap_engine,
        w1,
        model_id,
        seed_run,
        recommendation_type="consolidation",
        shipment_numbers=json.dumps(["SHIP-A", "SHIP-B"]),
    )

    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/detail",
        params={"recommendation_type": "consolidation"},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["recommendation_type"] == "consolidation"
    assert body["data"][0]["shipment_numbers"] == ["SHIP-A", "SHIP-B"]


def test_optimization_dashboard_rejects_executive_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/summary",
        headers={"X-Atlas-Role": "executive"},
    )
    assert resp.status_code == 403


def test_optimization_dashboard_allows_administrator(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/route-cost-optimization/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
