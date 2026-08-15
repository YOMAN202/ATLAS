"""Proves the Planning dashboard's inventory policy endpoints against
known, hand-seeded ds_model_registry/ds_inventory_policy/
ds_policy_sensitivity rows — the same reconciliation discipline every
other Phase 7 module's API test uses.
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
                    "VALUES ('inventory_policy', 'reorder_point_safety_stock_v1', "
                    ":params, :is_active, NOW())"
                ),
                {
                    "params": json.dumps({"default_target_service_level": 0.95}),
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


def _seed_product(olap_engine, product_id: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_product (product_id, sku, product_name, unit_of_measure, "
                    "current_unit_cost, current_unit_price, is_active, source_updated_at) "
                    "VALUES (:pid, :sku, 'Widget', 'EA', 10.00, 20.00, 1, NOW())"
                ),
                {"pid": product_id, "sku": f"SKU-{product_id}"},
            )
            return conn.execute(
                text("SELECT product_key FROM dim_product WHERE product_id = :pid"),
                {"pid": product_id},
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


def _seed_recommendation(
    olap_engine, product_key, warehouse_key, model_id, run_id, **overrides
) -> None:
    row = {
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "safety_stock": 18.0,
        "reorder_point": 55.0,
        "service_level_inventory_target": 55.0,
        "current_available_quantity": 53.0,
        "balancing_recommendation": "reorder_now",
        "confidence": "high",
        "contributing_factors": json.dumps({"avg_daily_demand": 2.0}),
        "business_rationale": "Average daily demand of 2.0 units...",
        "primary_supplier_key": None,
        "source_forecast_model_id": model_id,
        "source_supplier_model_id": None,
        "source_service_level_model_id": None,
        "model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_inventory_policy "
                    "(product_key, warehouse_key, safety_stock, reorder_point, "
                    "service_level_inventory_target, current_available_quantity, "
                    "balancing_recommendation, confidence, contributing_factors, "
                    "business_rationale, primary_supplier_key, source_forecast_model_id, "
                    "source_supplier_model_id, source_service_level_model_id, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:product_key, :warehouse_key, :safety_stock, :reorder_point, "
                    ":service_level_inventory_target, :current_available_quantity, "
                    ":balancing_recommendation, :confidence, "
                    "CAST(:contributing_factors AS JSON), :business_rationale, "
                    ":primary_supplier_key, :source_forecast_model_id, :source_supplier_model_id, "
                    ":source_service_level_model_id, :model_id, :etl_run_id, NOW())"
                ),
                row,
            )


def test_inventory_policy_summary_reconciles_to_seeded_recommendations(
    client, olap_engine, seed_run
):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    p1 = _seed_product(olap_engine, 1)
    p2 = _seed_product(olap_engine, 2)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_recommendation(
        olap_engine,
        p1,
        w1,
        model_id,
        seed_run,
        safety_stock=18.0,
        balancing_recommendation="reorder_now",
    )
    _seed_recommendation(
        olap_engine,
        p2,
        w1,
        model_id,
        seed_run,
        safety_stock=10.0,
        balancing_recommendation="adequate",
    )

    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/summary",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == model_id
    assert body["model_name"] == "reorder_point_safety_stock_v1"
    assert body["n_recommendations"] == 2
    assert body["avg_safety_stock"] == 14.0  # (18 + 10) / 2
    assert body["balancing_breakdown"] == {"reorder_now": 1, "adequate": 1, "excess_inventory": 0}


def test_inventory_policy_summary_with_no_active_model_returns_null(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] is None
    assert body["n_recommendations"] == 0


def test_inventory_policy_detail_filters_by_balancing_recommendation(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    p1 = _seed_product(olap_engine, 1)
    p2 = _seed_product(olap_engine, 2)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_recommendation(
        olap_engine, p1, w1, model_id, seed_run, balancing_recommendation="reorder_now"
    )
    _seed_recommendation(
        olap_engine, p2, w1, model_id, seed_run, balancing_recommendation="adequate"
    )

    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/detail",
        params={"balancing_recommendation": "reorder_now"},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["product_key"] == p1
    assert body["data"][0]["balancing_recommendation"] == "reorder_now"
    assert body["data"][0]["contributing_factors"] == {"avg_daily_demand": 2.0}


def test_inventory_policy_sensitivity_reconciles_to_seeded_scenarios(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_policy_sensitivity "
                    "(model_id, target_service_level, avg_safety_stock, avg_reorder_point, "
                    "total_inventory_investment, achieved_service_level, n_pairs, etl_run_id, "
                    "generated_at) "
                    "VALUES "
                    "(:model_id, 0.90, 10.4, 45.1, 2336061.42, 0.97731, 2290, :run_id, NOW()), "
                    "(:model_id, 0.95, 13.3, 48.0, 2998304.58, 0.97962, 2290, :run_id, NOW())"
                ),
                {"model_id": model_id, "run_id": seed_run},
            )

    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/sensitivity",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["target_service_level"] == 0.9
    assert body[0]["achieved_service_level"] == 0.97731
    assert body[1]["target_service_level"] == 0.95


def test_inventory_policy_dashboard_rejects_operations_analyst_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/summary",
        headers={"X-Atlas-Role": "operations_analyst"},
    )
    assert resp.status_code == 403


def test_inventory_policy_dashboard_allows_executive(client, seed_run):
    # executive was added to this gate for the v2 executive dashboard,
    # which surfaces the reorder-now count alongside other modules' KPIs.
    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/summary",
        headers={"X-Atlas-Role": "executive"},
    )
    assert resp.status_code == 200


def test_inventory_policy_dashboard_allows_administrator(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/inventory-policy/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
