"""Proves the Planning dashboard's supplier risk endpoints against known,
hand-seeded ds_model_registry/ds_supplier_risk_score/dim_supplier rows —
the same reconciliation discipline test_forecast_api.py uses for
Module A.
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
                    "VALUES ('supplier_risk_scoring', 'weighted_composite_v1', "
                    ":params, :is_active, NOW())"
                ),
                {
                    "params": json.dumps(
                        {
                            "weights": {
                                "on_time": 0.35,
                                "quality": 0.30,
                                "variability": 0.20,
                                "trend": 0.15,
                            }
                        }
                    ),
                    "is_active": is_active,
                },
            )
            return result.lastrowid


def _seed_supplier(olap_engine, supplier_id: int = 1) -> int:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_supplier "
                    "(supplier_id, supplier_code, supplier_name, payment_terms_days, "
                    "default_lead_time_days, is_active, effective_from, is_current, "
                    "source_updated_at) "
                    "VALUES (:sid, :code, :name, 30, 7, 1, '2021-01-01', 1, NOW())"
                ),
                {
                    "sid": supplier_id,
                    "code": f"SUP{supplier_id}",
                    "name": f"Supplier {supplier_id}",
                },
            )
            return conn.execute(
                text("SELECT supplier_key FROM dim_supplier WHERE supplier_id = :sid"),
                {"sid": supplier_id},
            ).scalar_one()


def _seed_score(olap_engine, supplier_key, model_id, run_id, **overrides) -> None:
    row = {
        "supplier_key": supplier_key,
        "risk_score": 76.46,
        "risk_classification": "High",
        "on_time_rate": 0.8698,
        "quality_rejection_rate": 0.0200,
        "fill_rate": 1.0,
        "avg_lead_time_variance_days": 0.5,
        "lead_time_stddev_days": 1.08,
        "on_time_rate_trend_delta": 0.0648,
        "trend_direction": "degrading",
        "total_spend": 3480391.20,
        "share_of_total_spend": 0.0162,
        "distinct_products_supplied": 82,
        "distinct_warehouses_served": 8,
        "n_deliveries": 215,
        "triggering_metrics": json.dumps(["on-time rate declined 6.5%"]),
        "model_id": model_id,
        "etl_run_id": run_id,
    }
    row.update(overrides)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO ds_supplier_risk_score "
                    "(supplier_key, risk_score, risk_classification, on_time_rate, "
                    "quality_rejection_rate, fill_rate, avg_lead_time_variance_days, "
                    "lead_time_stddev_days, on_time_rate_trend_delta, trend_direction, "
                    "total_spend, share_of_total_spend, distinct_products_supplied, "
                    "distinct_warehouses_served, n_deliveries, triggering_metrics, model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:supplier_key, :risk_score, :risk_classification, :on_time_rate, "
                    ":quality_rejection_rate, :fill_rate, :avg_lead_time_variance_days, "
                    ":lead_time_stddev_days, :on_time_rate_trend_delta, :trend_direction, "
                    ":total_spend, :share_of_total_spend, :distinct_products_supplied, "
                    ":distinct_warehouses_served, :n_deliveries, "
                    "CAST(:triggering_metrics AS JSON), :model_id, :etl_run_id, NOW())"
                ),
                row,
            )


def test_supplier_risk_summary_reconciles_to_seeded_scores(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    sk1 = _seed_supplier(olap_engine, 1)
    sk2 = _seed_supplier(olap_engine, 2)
    _seed_score(olap_engine, sk1, model_id, seed_run, risk_score=76.46, risk_classification="High")
    _seed_score(olap_engine, sk2, model_id, seed_run, risk_score=20.00, risk_classification="Low")

    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/summary",
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == model_id
    assert body["model_name"] == "weighted_composite_v1"
    assert body["n_suppliers"] == 2
    assert body["avg_risk_score"] == 48.23
    assert body["classification_breakdown"] == {"low": 1, "medium": 0, "high": 1}


def test_supplier_risk_summary_with_no_active_model_returns_null(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] is None
    assert body["n_suppliers"] == 0
    assert body["classification_breakdown"] == {"low": 0, "medium": 0, "high": 0}


def test_supplier_risk_detail_filters_by_classification(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    sk1 = _seed_supplier(olap_engine, 1)
    sk2 = _seed_supplier(olap_engine, 2)
    _seed_score(olap_engine, sk1, model_id, seed_run, risk_score=76.46, risk_classification="High")
    _seed_score(olap_engine, sk2, model_id, seed_run, risk_score=20.00, risk_classification="Low")

    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/detail",
        params={"risk_classification": "High"},
        headers={"X-Atlas-Role": "supply_planner"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["supplier_key"] == sk1
    assert body["data"][0]["risk_score"] == 76.46
    assert body["data"][0]["triggering_metrics"] == ["on-time rate declined 6.5%"]


def test_supplier_risk_detail_orders_by_risk_score_descending(client, olap_engine, seed_run):
    model_id = _seed_model(olap_engine)
    sk1 = _seed_supplier(olap_engine, 1)
    sk2 = _seed_supplier(olap_engine, 2)
    _seed_score(olap_engine, sk1, model_id, seed_run, risk_score=20.00, risk_classification="Low")
    _seed_score(olap_engine, sk2, model_id, seed_run, risk_score=76.46, risk_classification="High")

    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/detail",
        headers={"X-Atlas-Role": "administrator"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert [r["supplier_key"] for r in body["data"]] == [sk2, sk1]


def test_supplier_risk_dashboard_rejects_executive_role(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/summary", headers={"X-Atlas-Role": "executive"}
    )
    assert resp.status_code == 403


def test_supplier_risk_dashboard_allows_administrator(client, seed_run):
    resp = client.get(
        "/api/v1/dashboards/planning/supplier-risk/summary",
        headers={"X-Atlas-Role": "administrator"},
    )
    assert resp.status_code == 200
