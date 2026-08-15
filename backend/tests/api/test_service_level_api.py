"""Proves the Planning dashboard's service-level endpoints against known,
hand-seeded ds_model_registry/ds_service_level_prediction/ds_experiment_run
/ds_calibration_bucket rows — the same reconciliation discipline
test_forecast_api.py/test_supplier_risk_api.py use for Modules A/C.
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
                    "VALUES ('service_level_prediction', 'statistical_composite_v1', "
                    ":params, :is_active, NOW())"
                ),
                {"params": json.dumps({"stockout_horizon_days": 30}), "is_active": is_active},
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


def _seed_prediction(
    olap_engine, product_key, warehouse_key, model_id, run_id, **overrides
) -> None:
    row = {
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "stockout_probability": 0.65,
        "stockout_confidence": "high",
        "stockout_contributing_factors": json.dumps({"available_quantity": 5}),
        "backorder_probability": 0.12,
        "backorder_confidence": "medium",
        "backorder_contributing_factors": json.dumps({"historical_backorder_rate": 0.12}),
        "fulfillment_delay_probability": 0.08,
        "fulfillment_delay_confidence": "high",
        "fulfillment_delay_contributing_factors": json.dumps({"primary_supplier_key": 1}),
        "primary_supplier_key": None,
        "source_forecast_model_id": model_id,
        "source_supplier_model_id": None,
        "model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_service_level_prediction "
                    "(product_key, warehouse_key, stockout_probability, stockout_confidence, "
                    "stockout_contributing_factors, backorder_probability, backorder_confidence, "
                    "backorder_contributing_factors, fulfillment_delay_probability, "
                    "fulfillment_delay_confidence, fulfillment_delay_contributing_factors, "
                    "primary_supplier_key, source_forecast_model_id, source_supplier_model_id, "
                    "model_id, etl_run_id, generated_at) "
                    "VALUES (:product_key, :warehouse_key, :stockout_probability, "
                    ":stockout_confidence, CAST(:stockout_contributing_factors AS JSON), "
                    ":backorder_probability, :backorder_confidence, "
                    "CAST(:backorder_contributing_factors AS JSON), "
                    ":fulfillment_delay_probability, :fulfillment_delay_confidence, "
                    "CAST(:fulfillment_delay_contributing_factors AS JSON), :primary_supplier_key, "
                    ":source_forecast_model_id, :source_supplier_model_id, :model_id, :etl_run_id, "
                    "NOW())"
                ),
                row,
            )


def test_service_level_summary_reconciles_to_seeded_predictions(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    p1 = _seed_product(olap_engine, 1)
    p2 = _seed_product(olap_engine, 2)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_prediction(
        olap_engine,
        p1,
        w1,
        model_id,
        seed_run,
        stockout_probability=0.65,
        backorder_probability=0.10,
    )
    _seed_prediction(
        olap_engine,
        p2,
        w1,
        model_id,
        seed_run,
        stockout_probability=0.15,
        backorder_probability=0.05,
    )

    resp = client.get(
        "/api/v1/dashboards/planning/service-level/summary",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == model_id
    assert body["model_name"] == "statistical_composite_v1"
    assert body["n_predictions"] == 2
    assert body["n_with_delay_prediction"] == 2
    assert body["avg_stockout_probability"] == 0.4  # (0.65 + 0.15) / 2
    assert body["n_high_stockout_risk"] == 1  # only the 0.65 row exceeds 0.5


def test_service_level_summary_with_no_active_model_returns_null(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/service-level/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] is None
    assert body["n_predictions"] == 0


def test_service_level_detail_filters_by_min_stockout(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    p1 = _seed_product(olap_engine, 1)
    p2 = _seed_product(olap_engine, 2)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    _seed_prediction(olap_engine, p1, w1, model_id, seed_run, stockout_probability=0.65)
    _seed_prediction(olap_engine, p2, w1, model_id, seed_run, stockout_probability=0.15)

    resp = client.get(
        "/api/v1/dashboards/planning/service-level/detail",
        params={"min_stockout": 0.5},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["product_key"] == p1
    assert body["data"][0]["stockout_probability"] == 0.65
    assert body["data"][0]["stockout_contributing_factors"] == {"available_quantity": 5}


def test_service_level_calibration_reconciles_to_seeded_experiment_run(
    client, olap_engine, seed_run
):
    model_id = _seed_model(olap_engine)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_experiment_run "
                    "(model_id, train_start_date, train_end_date, test_start_date, test_end_date, "
                    "series_scope, metric_name, metric_value, baseline_metric_value, "
                    "n_observations, run_at) "
                    "VALUES (:model_id, '2021-01-01', '2021-11-30', '2021-12-01', '2021-12-30', "
                    "'stockout', 'BRIER_SCORE', 0.0291, 0.0301, 2290, NOW())"
                ),
                {"model_id": model_id},
            )
            conn.execute(
                text(
                    "INSERT INTO ds_calibration_bucket "
                    "(model_id, prediction_type, bucket_index, predicted_probability_mean, "
                    "actual_outcome_rate, n_observations, etl_run_id, generated_at) "
                    "VALUES (:model_id, 'stockout', 0, 0.01, 0.02, 229, :run_id, NOW()), "
                    "(:model_id, 'stockout', 9, 0.55, 0.60, 229, :run_id, NOW())"
                ),
                {"model_id": model_id, "run_id": seed_run},
            )

    resp = client.get(
        "/api/v1/dashboards/planning/service-level/calibration",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["prediction_type"] == "stockout"
    assert body[0]["brier_score"] == 0.0291
    assert body[0]["baseline_brier_score"] == 0.0301
    assert len(body[0]["buckets"]) == 2
    assert body[0]["buckets"][0]["actual_outcome_rate"] == 0.02
    assert body[0]["buckets"][1]["actual_outcome_rate"] == 0.6


def test_service_level_dashboard_rejects_operations_analyst_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/service-level/summary",
        headers={"X-Atlas-Role": "operations_analyst"},
    )
    assert resp.status_code == 403


def test_service_level_dashboard_allows_executive(client, seed_run):
    # executive was added to this gate for the v2 executive dashboard,
    # which surfaces stockout/backorder risk alongside other modules' KPIs.
    resp = client.get(
        "/api/v1/dashboards/planning/service-level/summary", headers={"X-Atlas-Role": "executive"}
    )
    assert resp.status_code == 200


def test_service_level_dashboard_allows_administrator(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/service-level/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
