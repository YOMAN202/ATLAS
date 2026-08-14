"""Proves the tool layer is real: each tool makes a genuine HTTP call
through the app's TestClient (the same interface a live httpx.Client
satisfies in production, per app.copilot.tools.HttpCaller) against
seeded data, and the resulting citation carries the actual retrieved
model_id/etl_run_id -- never a placeholder.
"""

import json

from sqlalchemy import text

from app.copilot import tools


def _seed_supplier(olap_engine, supplier_id: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_supplier (supplier_id, supplier_code, supplier_name, "
                    "payment_terms_days, default_lead_time_days, is_active, effective_from, "
                    "is_current, source_updated_at) "
                    "VALUES (:sid, :code, 'Acme Supply', 30, 7, 1, '2021-01-01', 1, NOW())"
                ),
                {"sid": supplier_id, "code": f"SUP-{supplier_id}"},
            )
            return conn.execute(
                text("SELECT supplier_key FROM dim_supplier WHERE supplier_id = :sid"),
                {"sid": supplier_id},
            ).scalar_one()


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
                    "INSERT INTO dim_warehouse (warehouse_id, warehouse_code, warehouse_name, "
                    "region_key, total_capacity_units, is_active, effective_from, is_current, "
                    "source_updated_at) "
                    "VALUES (:wid, :code, 'DC1', :region_key, 10000, 1, '2021-01-01', 1, NOW())"
                ),
                {"wid": warehouse_id, "code": f"DC-{warehouse_id}", "region_key": region_key},
            )
            return conn.execute(
                text("SELECT warehouse_key FROM dim_warehouse WHERE warehouse_id = :wid"),
                {"wid": warehouse_id},
            ).scalar_one()


def _seed_model(olap_engine, module: str, model_name: str, params: dict | None = None) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, "
                    "created_at) VALUES (:module, :model_name, CAST(:params AS JSON), 1, NOW())"
                ),
                {"module": module, "model_name": model_name, "params": json.dumps(params or {})},
            )
            return result.lastrowid


def test_get_executive_kpis_works_against_zero_seeded_data(client, seed_run):
    result = tools.get_executive_kpis(client, "executive", citation_id="c1")
    assert result.payload["total_revenue"] == 0
    assert result.citation.citation_id == "c1"
    assert result.citation.endpoint == "/api/v1/dashboards/executive"
    assert result.citation.etl_run_id == seed_run


def test_get_forecast_summary_citation_is_null_with_no_active_model(client, seed_run):
    result = tools.get_forecast_summary(client, "supply_planner", citation_id="c1")
    assert result.citation.model_id is None
    assert result.payload["active_model"] is None


def test_get_forecast_summary_citation_reflects_the_real_active_model(
    client, olap_engine, seed_run
):
    model_id = _seed_model(olap_engine, "demand_forecasting", "moving_average_14d")
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_experiment_run (model_id, train_start_date, train_end_date, "
                    "test_start_date, test_end_date, series_scope, metric_name, metric_value, "
                    "baseline_metric_value, n_observations, run_at) "
                    "VALUES (:mid, '2021-01-01', '2021-12-01', '2021-12-01', '2021-12-31', "
                    "'sku_warehouse', 'MAPE', 24.13, 33.23, 45, NOW())"
                ),
                {"mid": model_id},
            )

    result = tools.get_forecast_summary(client, "supply_planner", citation_id="c1")
    assert result.citation.model_id == model_id
    assert result.citation.model_name == "moving_average_14d"
    assert result.payload["active_model"]["weighted_avg_mape"] == 24.13


def test_get_supplier_risk_lookup_finds_the_real_row(client, olap_engine, seed_run):
    model_id = _seed_model(
        olap_engine, "supplier_risk_scoring", "composite_risk_score_v1", {"weights": {}}
    )
    supplier_key = _seed_supplier(olap_engine)
    with olap_engine.connect() as conn:
        with conn.begin():
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
                    "'degrading', 500000.0, 0.05, 10, 3, 200, CAST(:metrics AS JSON), :mid, "
                    ":run_id, NOW())"
                ),
                {
                    "supplier_key": supplier_key,
                    "metrics": json.dumps(["on_time_rate"]),
                    "mid": model_id,
                    "run_id": seed_run,
                },
            )

    result = tools.get_supplier_risk(
        client, "supply_planner", citation_id="c1", supplier_key=supplier_key
    )
    assert result.payload["supplier"]["risk_score"] == 71.2
    assert result.citation.model_id == model_id
    assert result.citation.etl_run_id == seed_run


def test_get_supplier_risk_lookup_miss_returns_null_supplier(client, olap_engine, seed_run):
    _seed_model(olap_engine, "supplier_risk_scoring", "composite_risk_score_v1", {"weights": {}})
    result = tools.get_supplier_risk(client, "supply_planner", citation_id="c1", supplier_key=99999)
    assert result.payload["supplier"] is None


def test_get_inventory_recommendation_citation_includes_upstream_source_models(
    client, olap_engine, seed_run
):
    forecast_model_id = _seed_model(olap_engine, "demand_forecasting", "moving_average_14d")
    inv_model_id = _seed_model(olap_engine, "inventory_policy", "reorder_point_safety_stock_v1")
    region_key = _seed_region(olap_engine)
    p1 = _seed_product(olap_engine, 1)
    w1 = _seed_warehouse(olap_engine, region_key, 1)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_inventory_policy (product_key, warehouse_key, safety_stock, "
                    "reorder_point, service_level_inventory_target, current_available_quantity, "
                    "balancing_recommendation, confidence, contributing_factors, "
                    "business_rationale, primary_supplier_key, source_forecast_model_id, "
                    "source_supplier_model_id, source_service_level_model_id, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:p, :w, 18.0, 55.0, 55.0, 53.0, 'reorder_now', 'high', "
                    "CAST(:factors AS JSON), 'rationale text', NULL, :fmid, NULL, NULL, :imid, "
                    ":run_id, NOW())"
                ),
                {
                    "p": p1,
                    "w": w1,
                    "factors": json.dumps({"avg_daily_demand": 2.0}),
                    "fmid": forecast_model_id,
                    "imid": inv_model_id,
                    "run_id": seed_run,
                },
            )

    result = tools.get_inventory_recommendation(
        client, "supply_planner", citation_id="c1", product_key=p1, warehouse_key=w1
    )
    assert result.payload["recommendation"]["safety_stock"] == 18.0
    assert result.citation.model_id == inv_model_id
    assert result.citation.source_forecast_model_id == forecast_model_id


def test_compare_scenarios_citation_reflects_real_source_versions(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine, "scenario_simulation", "perturbed_reuse_v1")
    forecast_model_id = _seed_model(olap_engine, "demand_forecasting", "moving_average_14d")
    with olap_engine.connect() as conn:
        with conn.begin():
            scenario_result = conn.execute(
                text(
                    "INSERT INTO ds_scenario (scenario_type, scenario_name, parameters, "
                    "description, model_id, etl_run_id, generated_at) "
                    "VALUES ('demand_surge', 'demand_surge_20pct', CAST(:params AS JSON), "
                    "'desc', :mid, :run_id, NOW())"
                ),
                {"params": json.dumps({"pct": 0.2}), "mid": model_id, "run_id": seed_run},
            )
            scenario_id = scenario_result.lastrowid
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
                {"sid": scenario_id, "fmid": forecast_model_id, "run_id": seed_run},
            )

    result = tools.compare_scenarios(
        client, "supply_planner", citation_id="c1", scenario_ids=[scenario_id]
    )
    assert result.payload["scenarios"][0]["scenario_inventory_investment"] == 3597927.95
    assert result.citation.source_forecast_model_id == forecast_model_id
