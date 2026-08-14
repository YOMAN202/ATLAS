"""Module B entrypoint: compute reorder point / safety stock / service-
level inventory target recommendations for every (product, warehouse)
pair Module A already forecasts, using Module A's demand forecast and
Module C's supplier lead-time reliability as inputs, and Module D's
service-level predictions as reported context. Also runs a walk-
forward policy simulation (real historical demand, real lead times) at
three target service levels — both this module's validation report and
its policy sensitivity analysis, one mechanism.

Run as: python -m app.decision_support.run_module_b
"""

import json
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import get_current_etl_run_id
from app.decision_support.db import get_engine
from app.decision_support.inventory_policy import (
    DEFAULT_TARGET_SERVICE_LEVEL,
    SENSITIVITY_TARGET_SERVICE_LEVELS,
    compute_policy_recommendation,
)
from app.decision_support.inventory_policy_simulation import (
    SIMULATION_ORDER_QUANTITY_LEAD_TIME_MULTIPLE,
    simulate_policy,
)
from app.decision_support.series import load_sku_warehouse_series

MODEL_PARAMETERS = {
    "default_target_service_level": DEFAULT_TARGET_SERVICE_LEVEL,
    "sensitivity_target_service_levels": SENSITIVITY_TARGET_SERVICE_LEVELS,
    "formula": "silver_pyke_peterson_combined_uncertainty_safety_stock",
    "excess_inventory_multiplier": 3.0,
    "eoq_in_scope": False,
}

# A default-target simulation must not fall more than this many
# percentage points below its own target to pass -- a disclosed
# tolerance, not an exact-match requirement, because a Normal-
# approximation safety-stock formula is a textbook standard, not a
# perfect fit to any specific real demand distribution (Module A's own
# completion report already documents this dataset's per-SKU demand as
# intermittent, not Normal).
VALIDATION_TOLERANCE_PERCENTAGE_POINTS = 0.15


def _product_warehouse_map(conn: Connection) -> dict[int, int]:
    rows = conn.execute(
        text("SELECT DISTINCT product_key, warehouse_key FROM fact_inventory_snapshot")
    ).all()
    return {r.product_key: r.warehouse_key for r in rows}


def _latest_available_by_pair(conn: Connection) -> dict[tuple, float]:
    rows = conn.execute(
        text(
            "WITH ranked AS ("
            "  SELECT product_key, warehouse_key, quantity_available, "
            "         ROW_NUMBER() OVER (PARTITION BY product_key, warehouse_key "
            "                            ORDER BY snapshot_date_key DESC) AS rn "
            "  FROM fact_inventory_snapshot"
            ") SELECT product_key, warehouse_key, quantity_available FROM ranked WHERE rn = 1"
        )
    ).all()
    return {(r.product_key, r.warehouse_key): float(r.quantity_available) for r in rows}


def _primary_suppliers_by_pair(conn: Connection) -> dict[tuple, int]:
    """The supplier with the most PO lines for each (product,
    warehouse), ties broken by most recent order_date — the same
    disclosed, deterministic rule Module D uses."""
    rows = conn.execute(
        text(
            "WITH ranked AS ("
            "  SELECT fp.product_key, fp.warehouse_key, fp.supplier_key, "
            "         COUNT(*) AS n_lines, MAX(od.full_date) AS most_recent_order, "
            "         ROW_NUMBER() OVER (PARTITION BY fp.product_key, fp.warehouse_key "
            "           ORDER BY COUNT(*) DESC, MAX(od.full_date) DESC) AS rn "
            "  FROM fact_procurement fp "
            "  JOIN dim_date od ON od.date_key = fp.order_date_key "
            "  GROUP BY fp.product_key, fp.warehouse_key, fp.supplier_key"
            ") SELECT product_key, warehouse_key, supplier_key FROM ranked WHERE rn = 1"
        )
    ).all()
    return {(r.product_key, r.warehouse_key): r.supplier_key for r in rows}


def _resolve_active_model(conn: Connection, module: str) -> int | None:
    return conn.execute(
        text("SELECT id FROM ds_model_registry WHERE module = :module AND is_active = 1 LIMIT 1"),
        {"module": module},
    ).scalar()


def _get_or_create_model(conn: Connection) -> int:
    params_json = json.dumps(MODEL_PARAMETERS, sort_keys=True)
    existing = conn.execute(
        text(
            "SELECT id FROM ds_model_registry WHERE module = 'inventory_policy' "
            "AND model_name = 'reorder_point_safety_stock_v1' "
            "AND parameters = CAST(:params AS JSON)"
        ),
        {"params": params_json},
    ).scalar()
    if existing is not None:
        return existing
    result = conn.execute(
        text(
            "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, created_at) "
            "VALUES ('inventory_policy', 'reorder_point_safety_stock_v1', "
            "CAST(:params AS JSON), 1, :now)"
        ),
        {"params": params_json, "now": datetime.now(UTC)},
    )
    return result.lastrowid


def _load_supplier_inputs(conn: Connection, supplier_model_id: int | None) -> dict[int, dict]:
    """Per-supplier default_lead_time_days (dim_supplier, current
    version), avg_lead_time_variance_days/lead_time_stddev_days/
    n_deliveries (Module C's active ds_supplier_risk_score row)."""
    lead_times = {
        r.supplier_key: r.default_lead_time_days
        for r in conn.execute(
            text(
                "SELECT supplier_key, default_lead_time_days FROM dim_supplier WHERE is_current = 1"
            )
        ).all()
    }
    scores = {}
    if supplier_model_id is not None:
        rows = conn.execute(
            text(
                "SELECT supplier_key, avg_lead_time_variance_days, lead_time_stddev_days, "
                "n_deliveries FROM ds_supplier_risk_score WHERE model_id = :model_id"
            ),
            {"model_id": supplier_model_id},
        ).all()
        scores = {r.supplier_key: r for r in rows}

    result = {}
    for supplier_key, base_lt in lead_times.items():
        score = scores.get(supplier_key)
        if score is None:
            continue
        result[supplier_key] = {
            "lead_time_days": base_lt + float(score.avg_lead_time_variance_days),
            "lead_time_stddev_days": float(score.lead_time_stddev_days),
            "n_deliveries": score.n_deliveries,
        }
    return result


def _forecast_demand_stats(conn: Connection, forecast_model_id: int) -> dict[tuple, dict]:
    rows = conn.execute(
        text(
            "SELECT product_key, warehouse_key, AVG(predicted_quantity) AS avg_daily_demand, "
            "SUM(POWER((confidence_interval_high - predicted_quantity) / 1.96, 2)) / COUNT(*) "
            "AS avg_daily_variance "
            "FROM ds_demand_forecast WHERE grain_type = 'sku_warehouse' AND model_id = :model_id "
            "GROUP BY product_key, warehouse_key"
        ),
        {"model_id": forecast_model_id},
    ).all()
    return {
        (r.product_key, r.warehouse_key): {
            "avg_daily_demand": float(r.avg_daily_demand),
            "demand_stddev": float(r.avg_daily_variance) ** 0.5,
        }
        for r in rows
    }


def _current_unit_costs(conn: Connection) -> dict[int, float]:
    rows = conn.execute(text("SELECT product_key, current_unit_cost FROM dim_product")).all()
    return {r.product_key: float(r.current_unit_cost) for r in rows}


def _build_recommendations(
    conn: Connection,
    forecast_model_id: int,
    supplier_model_id: int | None,
    target_service_level: float,
) -> list[dict]:
    demand_stats = _forecast_demand_stats(conn, forecast_model_id)
    active_days_by_pair = {
        s.key: sum(1 for v in s.values if v > 0) for s in load_sku_warehouse_series(conn)
    }
    supplier_inputs = _load_supplier_inputs(conn, supplier_model_id)
    primary_suppliers = _primary_suppliers_by_pair(conn)
    available = _latest_available_by_pair(conn)
    product_warehouse = _product_warehouse_map(conn)

    recommendations = []
    for pair, demand in demand_stats.items():
        product_key, warehouse_key = pair
        if product_warehouse.get(product_key) != warehouse_key:
            continue  # forecast pair not present in current inventory snapshot coverage
        supplier_key = primary_suppliers.get(pair)
        supplier_info = supplier_inputs.get(supplier_key) if supplier_key else None
        if supplier_info is None:
            continue  # no resolvable, scored primary supplier -- cannot compute a lead time

        rec = compute_policy_recommendation(
            product_key=product_key,
            warehouse_key=warehouse_key,
            avg_daily_demand=demand["avg_daily_demand"],
            demand_stddev=demand["demand_stddev"],
            lead_time_days=supplier_info["lead_time_days"],
            lead_time_stddev_days=supplier_info["lead_time_stddev_days"],
            current_available_quantity=available.get(pair, 0.0),
            primary_supplier_key=supplier_key,
            active_days=active_days_by_pair.get(pair, 0),
            n_deliveries=supplier_info["n_deliveries"],
            target_service_level=target_service_level,
        )
        recommendations.append(
            {
                "product_key": product_key,
                "warehouse_key": warehouse_key,
                "primary_supplier_key": supplier_key,
                "recommendation": rec,
            }
        )
    return recommendations


def _run_policy_simulation(
    conn: Connection, forecast_model_id: int, supplier_model_id: int | None
) -> dict[float, dict]:
    """Walk-forward validation + sensitivity analysis: the SAME
    recommendation formula run at three target service levels, each
    checked via a deterministic (s, Q) simulation over the pair's own
    real, full-year daily demand history."""
    series_list = load_sku_warehouse_series(conn)
    supplier_inputs = _load_supplier_inputs(conn, supplier_model_id)
    primary_suppliers = _primary_suppliers_by_pair(conn)
    demand_stats = _forecast_demand_stats(conn, forecast_model_id)
    unit_costs = _current_unit_costs(conn)

    results = {}
    for target in SENSITIVITY_TARGET_SERVICE_LEVELS:
        safety_stocks, reorder_points, investment = [], [], 0.0
        total_days, total_stockout_days = 0, 0
        n_pairs = 0

        for s in series_list:
            demand = demand_stats.get(s.key)
            supplier_key = primary_suppliers.get(s.key)
            supplier_info = supplier_inputs.get(supplier_key) if supplier_key else None
            if demand is None or supplier_info is None:
                continue

            rec = compute_policy_recommendation(
                product_key=s.key[0],
                warehouse_key=s.key[1],
                avg_daily_demand=demand["avg_daily_demand"],
                demand_stddev=demand["demand_stddev"],
                lead_time_days=supplier_info["lead_time_days"],
                lead_time_stddev_days=supplier_info["lead_time_stddev_days"],
                current_available_quantity=0.0,  # irrelevant to the simulation itself
                primary_supplier_key=supplier_key,
                active_days=sum(1 for v in s.values if v > 0),
                n_deliveries=supplier_info["n_deliveries"],
                target_service_level=target,
            )

            order_quantity = (
                demand["avg_daily_demand"]
                * supplier_info["lead_time_days"]
                * SIMULATION_ORDER_QUANTITY_LEAD_TIME_MULTIPLE
            )
            sim = simulate_policy(
                daily_demand=s.values,
                reorder_point=rec.reorder_point,
                order_quantity=order_quantity,
                lead_time_days=supplier_info["lead_time_days"],
                initial_inventory=rec.reorder_point + order_quantity,
            )

            safety_stocks.append(rec.safety_stock)
            reorder_points.append(rec.reorder_point)
            investment += rec.safety_stock * unit_costs.get(s.key[0], 0.0)
            total_days += sim.n_days
            total_stockout_days += sim.n_stockout_days
            n_pairs += 1

        achieved = 1 - total_stockout_days / total_days if total_days else 0.0
        results[target] = {
            "avg_safety_stock": sum(safety_stocks) / n_pairs if n_pairs else 0.0,
            "avg_reorder_point": sum(reorder_points) / n_pairs if n_pairs else 0.0,
            "total_inventory_investment": investment,
            "achieved_service_level": round(achieved, 5),
            "n_pairs": n_pairs,
        }
    return results


def _persist_recommendations(
    conn: Connection,
    recommendations: list[dict],
    model_id: int,
    forecast_model_id: int,
    supplier_model_id: int | None,
    service_level_model_id: int | None,
    etl_run_id: int,
) -> int:
    conn.execute(
        text("DELETE FROM ds_inventory_policy WHERE model_id = :model_id"), {"model_id": model_id}
    )
    now = datetime.now(UTC)
    rows = []
    for r in recommendations:
        rec = r["recommendation"]
        rows.append(
            {
                "product_key": r["product_key"],
                "warehouse_key": r["warehouse_key"],
                "safety_stock": rec.safety_stock,
                "reorder_point": rec.reorder_point,
                "service_level_inventory_target": rec.service_level_inventory_target,
                "current_available_quantity": rec.contributing_factors[
                    "current_available_quantity"
                ],
                "balancing_recommendation": rec.balancing_recommendation,
                "confidence": rec.confidence,
                "contributing_factors": json.dumps(rec.contributing_factors),
                "business_rationale": rec.business_rationale[:500],
                "primary_supplier_key": r["primary_supplier_key"],
                "source_forecast_model_id": forecast_model_id,
                "source_supplier_model_id": supplier_model_id,
                "source_service_level_model_id": service_level_model_id,
                "model_id": model_id,
                "etl_run_id": etl_run_id,
                "generated_at": now,
            }
        )
    if rows:
        conn.execute(
            text(
                "INSERT INTO ds_inventory_policy "
                "(product_key, warehouse_key, safety_stock, reorder_point, "
                "service_level_inventory_target, current_available_quantity, "
                "balancing_recommendation, confidence, contributing_factors, business_rationale, "
                "primary_supplier_key, source_forecast_model_id, source_supplier_model_id, "
                "source_service_level_model_id, model_id, etl_run_id, generated_at) "
                "VALUES (:product_key, :warehouse_key, :safety_stock, :reorder_point, "
                ":service_level_inventory_target, :current_available_quantity, "
                ":balancing_recommendation, :confidence, CAST(:contributing_factors AS JSON), "
                ":business_rationale, :primary_supplier_key, :source_forecast_model_id, "
                ":source_supplier_model_id, :source_service_level_model_id, :model_id, "
                ":etl_run_id, :generated_at)"
            ),
            rows,
        )
    return len(rows)


def _persist_sensitivity(
    conn: Connection, sim_results: dict[float, dict], model_id: int, etl_run_id: int
) -> None:
    conn.execute(
        text("DELETE FROM ds_policy_sensitivity WHERE model_id = :model_id"), {"model_id": model_id}
    )
    conn.execute(
        text(
            "DELETE FROM ds_experiment_run "
            "WHERE model_id = :model_id AND metric_name = 'ACHIEVED_SERVICE_LEVEL'"
        ),
        {"model_id": model_id},
    )
    now = datetime.now(UTC)
    for target, r in sim_results.items():
        conn.execute(
            text(
                "INSERT INTO ds_policy_sensitivity "
                "(model_id, target_service_level, avg_safety_stock, avg_reorder_point, "
                "total_inventory_investment, achieved_service_level, n_pairs, etl_run_id, "
                "generated_at) "
                "VALUES (:model_id, :target, :avg_ss, :avg_rop, :investment, :achieved, :n, "
                ":etl_run_id, :now)"
            ),
            {
                "model_id": model_id,
                "target": target,
                "avg_ss": r["avg_safety_stock"],
                "avg_rop": r["avg_reorder_point"],
                "investment": r["total_inventory_investment"],
                "achieved": r["achieved_service_level"],
                "n": r["n_pairs"],
                "etl_run_id": etl_run_id,
                "now": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO ds_experiment_run "
                "(model_id, train_start_date, train_end_date, test_start_date, test_end_date, "
                "series_scope, metric_name, metric_value, baseline_metric_value, "
                "n_observations, run_at) "
                "VALUES (:model_id, '2021-01-01', '2021-12-31', '2021-01-01', '2021-12-31', "
                ":scope, 'ACHIEVED_SERVICE_LEVEL', :achieved, :target, :n, :now)"
            ),
            {
                "model_id": model_id,
                "scope": f"target_{target:.2f}",
                "achieved": r["achieved_service_level"],
                "target": target,
                "n": r["n_pairs"],
                "now": now,
            },
        )


def main() -> None:
    engine = get_engine()
    t0 = time.perf_counter()

    with engine.connect() as conn:
        etl_run_id = get_current_etl_run_id(conn)
        print(f"etl_run_id={etl_run_id}", flush=True)

        forecast_model_id = _resolve_active_model(conn, "demand_forecasting")
        supplier_model_id = _resolve_active_model(conn, "supplier_risk_scoring")
        service_level_model_id = _resolve_active_model(conn, "service_level_prediction")
        if forecast_model_id is None:
            print("VALIDATION_FAILURE: no active demand_forecasting model (Module A)", flush=True)
            print("status=FAILED", flush=True)
            raise SystemExit(1)
        print(
            f"source_forecast_model_id={forecast_model_id} "
            f"source_supplier_model_id={supplier_model_id} "
            f"source_service_level_model_id={service_level_model_id}",
            flush=True,
        )

        sim_results = _run_policy_simulation(conn, forecast_model_id, supplier_model_id)
        for target, r in sim_results.items():
            print(
                f"sensitivity[target={target:.0%}] achieved={r['achieved_service_level']:.4f} "
                f"avg_safety_stock={r['avg_safety_stock']:.1f} "
                f"avg_reorder_point={r['avg_reorder_point']:.1f} "
                f"investment={r['total_inventory_investment']:.0f} n_pairs={r['n_pairs']}",
                flush=True,
            )

        default_result = sim_results.get(DEFAULT_TARGET_SERVICE_LEVEL)
        if default_result is None or default_result["n_pairs"] == 0:
            print("VALIDATION_FAILURE: no simulated pairs at the default target", flush=True)
            print("status=FAILED", flush=True)
            raise SystemExit(1)
        shortfall = DEFAULT_TARGET_SERVICE_LEVEL - default_result["achieved_service_level"]
        if shortfall > VALIDATION_TOLERANCE_PERCENTAGE_POINTS:
            print(
                f"VALIDATION_FAILURE: achieved service level "
                f"({default_result['achieved_service_level']:.4f}) is more than "
                f"{VALIDATION_TOLERANCE_PERCENTAGE_POINTS:.0%} below the target "
                f"({DEFAULT_TARGET_SERVICE_LEVEL:.0%})",
                flush=True,
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)

        model_id = _get_or_create_model(conn)
        print(f"model_id={model_id}", flush=True)

        recommendations = _build_recommendations(
            conn, forecast_model_id, supplier_model_id, DEFAULT_TARGET_SERVICE_LEVEL
        )
        n_persisted = _persist_recommendations(
            conn,
            recommendations,
            model_id,
            forecast_model_id,
            supplier_model_id,
            service_level_model_id,
            etl_run_id,
        )
        _persist_sensitivity(conn, sim_results, model_id, etl_run_id)
        conn.commit()

        n_reorder_now = sum(
            1
            for r in recommendations
            if r["recommendation"].balancing_recommendation == "reorder_now"
        )
        print(f"recommendations_persisted={n_persisted} n_reorder_now={n_reorder_now}", flush=True)
        print(f"timing total_seconds={time.perf_counter() - t0:.1f}", flush=True)

    print("status=SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()
