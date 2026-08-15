"""Proves the Planning dashboard's forecast endpoints against known,
hand-seeded ds_model_registry/ds_experiment_run/ds_demand_forecast rows
— the same reconciliation discipline every other Phase 6/7 dashboard
test in this suite uses.
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
                    "VALUES ('demand_forecasting', 'moving_average_7d', :params, :is_active, NOW())"
                ),
                {"params": json.dumps({"window": 7}), "is_active": is_active},
            )
            return result.lastrowid


def _seed_region(olap_engine) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_region "
                    "(region_id, region_code, region_name, source_updated_at) "
                    "VALUES (1, 'NA', 'North America', NOW())"
                )
            )
            return conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = 1")
            ).scalar_one()


def test_forecast_summary_reconciles_to_seeded_active_model(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)

    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_experiment_run "
                    "(model_id, train_start_date, train_end_date, test_start_date, test_end_date, "
                    "series_scope, metric_name, metric_value, baseline_metric_value, "
                    "n_observations, run_at) "
                    "VALUES (:model_id, '2021-01-01', '2021-11-30', '2021-12-01', '2021-12-30', "
                    "'region:(1,)', 'MAPE', 8.5, 12.0, 30, NOW())"
                ),
                {"model_id": model_id},
            )
            conn.execute(
                text(
                    "INSERT INTO ds_demand_forecast "
                    "(grain_type, region_key, forecast_date, predicted_quantity, "
                    "confidence_interval_low, confidence_interval_high, model_id, etl_run_id, "
                    "generated_at) "
                    "VALUES "
                    "('region', :rk, '2022-01-01', 1000.00, 900.00, 1100.00, :model_id, "
                    ":run_id, NOW()), "
                    "('region', :rk, '2022-01-02', 1050.00, 950.00, 1150.00, :model_id, "
                    ":run_id, NOW())"
                ),
                {"rk": region_key, "model_id": model_id, "run_id": seed_run},
            )

    resp = client.get(
        "/api/v1/dashboards/planning/forecast/summary", headers={"X-Atlas-Role": "supply_planner"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["active_model"]["model_id"] == model_id
    assert body["active_model"]["model_name"] == "moving_average_7d"
    assert body["active_model"]["parameters"] == {"window": 7}
    assert body["active_model"]["weighted_avg_mape"] == 8.5
    assert body["active_model"]["baseline_mape"] == 12.0
    assert body["total_predicted_demand_next_30d"] == 2050.0  # 1000.00 + 1050.00
    assert body["n_region_series"] == 1


def test_forecast_summary_with_no_active_model_returns_null(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/forecast/summary", headers={"X-Atlas-Role": "administrator"}
    )
    assert resp.status_code == 200
    assert resp.json()["active_model"] is None


def test_forecast_detail_filters_by_grain_type(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    region_key = _seed_region(olap_engine)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_demand_forecast "
                    "(grain_type, region_key, forecast_date, predicted_quantity, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES ('region', :rk, '2022-01-01', 500.00, :model_id, :run_id, NOW())"
                ),
                {"rk": region_key, "model_id": model_id, "run_id": seed_run},
            )

    resp = client.get(
        "/api/v1/dashboards/planning/forecast/detail",
        params={"grain_type": "region"},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["region_key"] == region_key
    assert body["data"][0]["predicted_quantity"] == 500.0
    assert body["data"][0]["model_name"] == "moving_average_7d"


def test_forecast_experiments_lists_seeded_backtests(client, olap_engine, seed_run):
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
                    "'region:(1,)', 'MAPE', 8.5, 12.0, 30, NOW())"
                ),
                {"model_id": model_id},
            )

    resp = client.get(
        "/api/v1/dashboards/planning/forecast/experiments",
        headers={"X-Atlas-Role": "administrator"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["model_name"] == "moving_average_7d"
    assert body[0]["metric_value"] == 8.5
    assert body[0]["baseline_metric_value"] == 12.0
    assert body[0]["n_observations"] == 30


def test_planning_dashboard_rejects_operations_analyst_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/forecast/summary",
        headers={"X-Atlas-Role": "operations_analyst"},
    )
    assert resp.status_code == 403


def test_planning_dashboard_allows_executive(client, seed_run):
    # executive was added to this gate for the v2 executive dashboard,
    # which surfaces forecast accuracy alongside other modules' KPIs.
    resp = client.get(
        "/api/v1/dashboards/planning/forecast/summary", headers={"X-Atlas-Role": "executive"}
    )
    assert resp.status_code == 200


def test_planning_dashboard_allows_administrator(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/forecast/summary", headers={"X-Atlas-Role": "administrator"}
    )
    assert resp.status_code == 200
