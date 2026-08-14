"""Module E entrypoint: precompute a curated library of named scenarios
(demand surge/decline, supplier disruption, lead-time inflation,
warehouse outage, inventory policy change, service-level target change,
and combined scenarios), each recomputing Modules A/C/D/B's own frozen
formulas over in-memory-perturbed inputs, and persist aggregate
baseline-vs-scenario comparisons. Never writes to a warehouse fact
table — see docs/phase7-2-architecture.md §1 for the full design.

Run as: python -m app.decision_support.run_module_e
"""

import json
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import get_current_etl_run_id
from app.decision_support.db import get_engine
from app.decision_support.inventory_policy import DEFAULT_TARGET_SERVICE_LEVEL
from app.decision_support.scenario_simulation import (
    HIGH_STOCKOUT_RISK_THRESHOLD,
    PairBaseline,
    apply_scenario_transformation,
    compute_pair_metrics,
)
from app.decision_support.series import load_sku_warehouse_series

MODEL_PARAMETERS = {
    "formula": "reuses_modules_a_c_d_b_frozen_formulas_over_perturbed_inputs",
    "state_isolation": "in_memory_only_never_writes_warehouse_facts",
    "default_target_service_level": DEFAULT_TARGET_SERVICE_LEVEL,
}

# Scenario catalog: (scenario_type, scenario_name, parameters, description)
SCENARIO_CATALOG = [
    ("demand_surge", "demand_surge_20pct", {"pct": 0.20}, "Demand increases 20% across all pairs."),
    ("demand_surge", "demand_surge_50pct", {"pct": 0.50}, "Demand increases 50% across all pairs."),
    (
        "demand_decline",
        "demand_decline_20pct",
        {"pct": 0.20},
        "Demand decreases 20% across all pairs.",
    ),
    (
        "demand_decline",
        "demand_decline_40pct",
        {"pct": 0.40},
        "Demand decreases 40% across all pairs.",
    ),
    (
        "supplier_disruption",
        "supplier_disruption_50pct",
        {"pct": 0.50},
        "The most systemically important supplier's lead-time variability increases 50%.",
    ),
    (
        "supplier_disruption",
        "supplier_disruption_100pct",
        {"pct": 1.00},
        "The most systemically important supplier's lead-time variability doubles.",
    ),
    (
        "lead_time_inflation",
        "lead_time_inflation_5days",
        {"added_days": 5},
        "Every supplier's lead time increases by 5 days (a logistics-wide slowdown).",
    ),
    (
        "lead_time_inflation",
        "lead_time_inflation_10days",
        {"added_days": 10},
        "Every supplier's lead time increases by 10 days.",
    ),
    (
        "warehouse_outage",
        "warehouse_outage_severe",
        {"outage_pct": 1.00},
        "The most systemically important warehouse loses effectively all available inventory "
        "(a severe, week-scale supply interruption).",
    ),
    (
        "inventory_policy_change",
        "inventory_policy_90pct",
        {"target_service_level": 0.90},
        "Inventory policy target service level relaxed to 90%.",
    ),
    (
        "inventory_policy_change",
        "inventory_policy_99pct",
        {"target_service_level": 0.99},
        "Inventory policy target service level tightened to 99%.",
    ),
    (
        "service_level_target_change",
        "service_level_target_loose_85pct",
        {"target_service_level": 0.85},
        "Service-level target loosened to 85% (below Module B's own sensitivity range).",
    ),
    (
        "combined",
        "combined_surge_and_leadtime",
        {
            "target_service_level": DEFAULT_TARGET_SERVICE_LEVEL,
            "components": [
                ("demand_surge", {"pct": 0.30}),
                ("lead_time_inflation", {"added_days": 5}),
            ],
        },
        "A realistic joint stress case: 30% demand surge combined with a 5-day lead-time "
        "inflation.",
    ),
]


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


def _historical_stockout_stats(conn: Connection) -> dict[tuple, tuple[int, int, float | None]]:
    rows = conn.execute(
        text(
            "SELECT product_key, warehouse_key, COUNT(*) AS n_days, "
            "SUM(is_stockout) AS n_stockout_days, "
            "MIN(CASE WHEN is_stockout = 0 THEN quantity_available END) "
            "AS min_available_on_safe_days "
            "FROM fact_inventory_snapshot GROUP BY product_key, warehouse_key"
        )
    ).all()
    return {
        (r.product_key, r.warehouse_key): (
            r.n_days,
            int(r.n_stockout_days or 0),
            (
                float(r.min_available_on_safe_days)
                if r.min_available_on_safe_days is not None
                else None
            ),
        )
        for r in rows
    }


def _population_stockout_rate(conn: Connection) -> float:
    rate = conn.execute(text("SELECT AVG(is_stockout) FROM fact_inventory_snapshot")).scalar()
    return float(rate) if rate is not None else 0.0


def _backorder_history_by_pair(
    conn: Connection, product_warehouse: dict[int, int]
) -> dict[tuple, tuple[int, int]]:
    rows = conn.execute(
        text(
            "SELECT product_key, COUNT(*) AS n_lines, "
            "SUM(backordered_quantity > 0) AS n_backordered "
            "FROM fact_orders GROUP BY product_key"
        )
    ).all()
    result: dict[tuple, tuple[int, int]] = {}
    for r in rows:
        wh = product_warehouse.get(r.product_key)
        if wh is None:
            continue
        result[(r.product_key, wh)] = (r.n_lines, int(r.n_backordered or 0))
    return result


def _primary_suppliers_by_pair(conn: Connection) -> dict[tuple, int]:
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


def _supplier_lead_time_inputs(conn: Connection, supplier_model_id: int | None) -> dict[int, dict]:
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


def _resolve_active_model(conn: Connection, module: str) -> int | None:
    return conn.execute(
        text("SELECT id FROM ds_model_registry WHERE module = :module AND is_active = 1 LIMIT 1"),
        {"module": module},
    ).scalar()


def _get_or_create_model(conn: Connection) -> int:
    params_json = json.dumps(MODEL_PARAMETERS, sort_keys=True)
    existing = conn.execute(
        text(
            "SELECT id FROM ds_model_registry WHERE module = 'scenario_simulation' "
            "AND model_name = 'perturbed_reuse_v1' AND parameters = CAST(:params AS JSON)"
        ),
        {"params": params_json},
    ).scalar()
    if existing is not None:
        return existing
    result = conn.execute(
        text(
            "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, created_at) "
            "VALUES ('scenario_simulation', 'perturbed_reuse_v1', CAST(:params AS JSON), 1, :now)"
        ),
        {"params": params_json, "now": datetime.now(UTC)},
    )
    return result.lastrowid


def _load_baselines(
    conn: Connection, forecast_model_id: int, supplier_model_id: int | None
) -> list[PairBaseline]:
    demand_stats = _forecast_demand_stats(conn, forecast_model_id)
    active_days_by_pair = {
        s.key: sum(1 for v in s.values if v > 0) for s in load_sku_warehouse_series(conn)
    }
    supplier_inputs = _supplier_lead_time_inputs(conn, supplier_model_id)
    primary_suppliers = _primary_suppliers_by_pair(conn)
    available = _latest_available_by_pair(conn)
    product_warehouse = _product_warehouse_map(conn)
    stockout_stats = _historical_stockout_stats(conn)
    population_rate = _population_stockout_rate(conn)
    backorder_hist = _backorder_history_by_pair(conn, product_warehouse)
    unit_costs = _current_unit_costs(conn)

    baselines = []
    for pair, demand in demand_stats.items():
        product_key, warehouse_key = pair
        if product_warehouse.get(product_key) != warehouse_key:
            continue
        supplier_key = primary_suppliers.get(pair)
        supplier_info = supplier_inputs.get(supplier_key) if supplier_key else None
        if supplier_info is None:
            continue
        n_days, n_stockout_days, min_safe = stockout_stats.get(pair, (0, 0, None))
        n_lines, n_backordered = backorder_hist.get(pair, (0, 0))
        baselines.append(
            PairBaseline(
                product_key=product_key,
                warehouse_key=warehouse_key,
                avg_daily_demand=demand["avg_daily_demand"],
                demand_stddev=demand["demand_stddev"],
                lead_time_days=supplier_info["lead_time_days"],
                lead_time_stddev_days=supplier_info["lead_time_stddev_days"],
                current_available_quantity=available.get(pair, 0.0),
                n_historical_days=n_days,
                n_historical_stockout_days=n_stockout_days,
                population_stockout_rate=population_rate,
                historical_min_available_on_safe_days=min_safe,
                n_historical_lines=n_lines,
                n_historical_backordered_lines=n_backordered,
                primary_supplier_key=supplier_key,
                active_days=active_days_by_pair.get(pair, 0),
                n_deliveries=supplier_info["n_deliveries"],
                unit_cost=unit_costs.get(product_key, 0.0),
            )
        )
    return baselines


def _aggregate(metrics_list: list, baselines: list[PairBaseline]) -> dict:
    n = len(metrics_list)
    n_suppliers = len(
        {b.primary_supplier_key for b in baselines if b.primary_supplier_key is not None}
    )
    return {
        "avg_stockout_probability": sum(m.stockout_probability for m in metrics_list) / n,
        "n_high_stockout_risk": sum(
            1 for m in metrics_list if m.stockout_probability > HIGH_STOCKOUT_RISK_THRESHOLD
        ),
        "avg_backorder_probability": sum(m.backorder_probability for m in metrics_list) / n,
        "inventory_investment": sum(m.inventory_investment for m in metrics_list),
        "avg_service_level": sum(m.service_level for m in metrics_list) / n,
        "procurement_volume": sum(m.procurement_volume for m in metrics_list),
        "n_suppliers_utilized": n_suppliers,
    }


def main() -> None:
    engine = get_engine()
    t0 = time.perf_counter()

    with engine.connect() as conn:
        etl_run_id = get_current_etl_run_id(conn)
        print(f"etl_run_id={etl_run_id}", flush=True)

        forecast_model_id = _resolve_active_model(conn, "demand_forecasting")
        supplier_model_id = _resolve_active_model(conn, "supplier_risk_scoring")
        service_level_model_id = _resolve_active_model(conn, "service_level_prediction")
        inventory_policy_model_id = _resolve_active_model(conn, "inventory_policy")
        if forecast_model_id is None:
            print("VALIDATION_FAILURE: no active demand_forecasting model (Module A)", flush=True)
            print("status=FAILED", flush=True)
            raise SystemExit(1)

        baselines = _load_baselines(conn, forecast_model_id, supplier_model_id)
        print(f"n_pairs_loaded={len(baselines)}", flush=True)

        baseline_metrics = [
            compute_pair_metrics(b, DEFAULT_TARGET_SERVICE_LEVEL) for b in baselines
        ]
        real_baseline_agg = _aggregate(baseline_metrics, baselines)

        # --- Validation: baseline equivalence ---
        # A "null" (zero-perturbation) demand_surge scenario must
        # reproduce the real baseline aggregate exactly.
        null_metrics = [
            compute_pair_metrics(
                apply_scenario_transformation("demand_surge", {"pct": 0.0}, b),
                DEFAULT_TARGET_SERVICE_LEVEL,
            )
            for b in baselines
        ]
        null_agg = _aggregate(null_metrics, baselines)
        if round(null_agg["avg_stockout_probability"], 10) != round(
            real_baseline_agg["avg_stockout_probability"], 10
        ):
            print(
                "VALIDATION_FAILURE: null scenario does not reproduce the real baseline", flush=True
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
        print("baseline_equivalence_check=PASSED", flush=True)

        # Most systemically important supplier / warehouse, for the
        # supplier_disruption / warehouse_outage scenarios.
        supplier_pair_counts: dict[int, int] = {}
        warehouse_pair_counts: dict[int, int] = {}
        for b in baselines:
            if b.primary_supplier_key is not None:
                supplier_pair_counts[b.primary_supplier_key] = (
                    supplier_pair_counts.get(b.primary_supplier_key, 0) + 1
                )
            warehouse_pair_counts[b.warehouse_key] = (
                warehouse_pair_counts.get(b.warehouse_key, 0) + 1
            )
        target_supplier_key = max(supplier_pair_counts, key=supplier_pair_counts.get)
        target_warehouse_key = max(warehouse_pair_counts, key=warehouse_pair_counts.get)
        n_supplier_pairs = supplier_pair_counts[target_supplier_key]
        n_warehouse_pairs = warehouse_pair_counts[target_warehouse_key]
        print(
            f"target_supplier_key={target_supplier_key} (n_pairs={n_supplier_pairs}) "
            f"target_warehouse_key={target_warehouse_key} (n_pairs={n_warehouse_pairs})",
            flush=True,
        )

        model_id = _get_or_create_model(conn)
        print(f"model_id={model_id}", flush=True)

        scenario_aggregates: dict[str, dict] = {}
        for scenario_type, scenario_name, parameters, _description in SCENARIO_CATALOG:
            target_service_level = parameters.get(
                "target_service_level", DEFAULT_TARGET_SERVICE_LEVEL
            )
            metrics_list = []
            for b in baselines:
                transformed = apply_scenario_transformation(
                    scenario_type,
                    parameters,
                    b,
                    target_supplier_key=target_supplier_key,
                    target_warehouse_key=target_warehouse_key,
                )
                metrics_list.append(compute_pair_metrics(transformed, target_service_level))
            agg = _aggregate(metrics_list, baselines)
            scenario_aggregates[scenario_name] = agg
            print(
                f"scenario[{scenario_name}] avg_stockout={agg['avg_stockout_probability']:.4f} "
                f"(baseline {real_baseline_agg['avg_stockout_probability']:.4f}) "
                f"investment={agg['inventory_investment']:.0f}",
                flush=True,
            )

        # --- Validation: sensitivity ---
        # A larger demand surge must show a higher (or equal) average
        # stockout probability than a smaller one.
        if (
            scenario_aggregates["demand_surge_50pct"]["avg_stockout_probability"]
            < scenario_aggregates["demand_surge_20pct"]["avg_stockout_probability"]
        ):
            print(
                "VALIDATION_FAILURE: demand_surge_50pct does not show higher stockout risk "
                "than demand_surge_20pct",
                flush=True,
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
        print("sensitivity_check=PASSED", flush=True)

        # --- Persist ---
        conn.execute(
            text(
                "DELETE FROM ds_scenario_result WHERE scenario_id IN "
                "(SELECT id FROM ds_scenario WHERE model_id = :model_id)"
            ),
            {"model_id": model_id},
        )
        conn.execute(
            text("DELETE FROM ds_scenario WHERE model_id = :model_id"), {"model_id": model_id}
        )
        now = datetime.now(UTC)

        for scenario_type, scenario_name, parameters, description in SCENARIO_CATALOG:
            scenario_result = conn.execute(
                text(
                    "INSERT INTO ds_scenario "
                    "(scenario_type, scenario_name, parameters, description, "
                    "model_id, etl_run_id, generated_at) "
                    "VALUES (:scenario_type, :scenario_name, CAST(:parameters AS JSON), "
                    ":description, :model_id, :etl_run_id, :now)"
                ),
                {
                    "scenario_type": scenario_type,
                    "scenario_name": scenario_name,
                    "parameters": json.dumps(parameters),
                    "description": description,
                    "model_id": model_id,
                    "etl_run_id": etl_run_id,
                    "now": now,
                },
            )
            scenario_id = scenario_result.lastrowid
            agg = scenario_aggregates[scenario_name]

            changed_assumptions = {"scenario_type": scenario_type, **parameters}
            affected_modules = ["demand_forecasting"]
            if scenario_type in ("supplier_disruption", "lead_time_inflation"):
                affected_modules.append("supplier_risk_scoring")
            if scenario_type in ("inventory_policy_change",):
                affected_modules.append("inventory_policy")
            affected_modules.append("service_level_prediction")
            affected_modules.append("inventory_policy")

            b_stockout_str = f"{real_baseline_agg['avg_stockout_probability']:.4f}"
            s_stockout_str = f"{agg['avg_stockout_probability']:.4f}"
            b_investment_str = f"{real_baseline_agg['inventory_investment']:.0f}"
            s_investment_str = f"{agg['inventory_investment']:.0f}"
            key_drivers = [
                f"avg_stockout_probability moved from {b_stockout_str} to {s_stockout_str}",
                f"inventory_investment moved from {b_investment_str} to {s_investment_str}",
            ]
            sensitivity_indicators = {
                "stockout_probability_delta": round(
                    agg["avg_stockout_probability"] - real_baseline_agg["avg_stockout_probability"],
                    5,
                ),
                "service_level_delta": round(
                    agg["avg_service_level"] - real_baseline_agg["avg_service_level"], 5
                ),
                "investment_delta": round(
                    agg["inventory_investment"] - real_baseline_agg["inventory_investment"], 2
                ),
            }
            confidence = "high" if len(baselines) >= 1000 else "medium"

            conn.execute(
                text(
                    "INSERT INTO ds_scenario_result "
                    "(scenario_id, baseline_avg_stockout_probability, "
                    "scenario_avg_stockout_probability, "
                    "baseline_n_high_stockout_risk, scenario_n_high_stockout_risk, "
                    "baseline_avg_backorder_probability, scenario_avg_backorder_probability, "
                    "baseline_inventory_investment, scenario_inventory_investment, "
                    "baseline_avg_service_level, scenario_avg_service_level, "
                    "baseline_procurement_volume, scenario_procurement_volume, "
                    "baseline_n_suppliers_utilized, scenario_n_suppliers_utilized, "
                    "changed_assumptions, affected_modules, key_drivers, confidence, "
                    "sensitivity_indicators, n_pairs_evaluated, "
                    "source_forecast_model_id, source_supplier_model_id, "
                    "source_service_level_model_id, source_inventory_policy_model_id, "
                    "etl_run_id, generated_at) "
                    "VALUES (:scenario_id, :b_stockout, :s_stockout, :b_high, :s_high, "
                    ":b_backorder, :s_backorder, :b_investment, :s_investment, "
                    ":b_service, :s_service, :b_procurement, :s_procurement, "
                    ":b_suppliers, :s_suppliers, "
                    "CAST(:changed_assumptions AS JSON), CAST(:affected_modules AS JSON), "
                    "CAST(:key_drivers AS JSON), :confidence, "
                    "CAST(:sensitivity_indicators AS JSON), "
                    ":n_pairs, :source_forecast_model_id, :source_supplier_model_id, "
                    ":source_service_level_model_id, :source_inventory_policy_model_id, "
                    ":etl_run_id, :now)"
                ),
                {
                    "scenario_id": scenario_id,
                    "b_stockout": real_baseline_agg["avg_stockout_probability"],
                    "s_stockout": agg["avg_stockout_probability"],
                    "b_high": real_baseline_agg["n_high_stockout_risk"],
                    "s_high": agg["n_high_stockout_risk"],
                    "b_backorder": real_baseline_agg["avg_backorder_probability"],
                    "s_backorder": agg["avg_backorder_probability"],
                    "b_investment": real_baseline_agg["inventory_investment"],
                    "s_investment": agg["inventory_investment"],
                    "b_service": real_baseline_agg["avg_service_level"],
                    "s_service": agg["avg_service_level"],
                    "b_procurement": real_baseline_agg["procurement_volume"],
                    "s_procurement": agg["procurement_volume"],
                    "b_suppliers": real_baseline_agg["n_suppliers_utilized"],
                    "s_suppliers": agg["n_suppliers_utilized"],
                    "changed_assumptions": json.dumps(changed_assumptions),
                    "affected_modules": json.dumps(affected_modules),
                    "key_drivers": json.dumps(key_drivers),
                    "confidence": confidence,
                    "sensitivity_indicators": json.dumps(sensitivity_indicators),
                    "n_pairs": len(baselines),
                    "source_forecast_model_id": forecast_model_id,
                    "source_supplier_model_id": supplier_model_id,
                    "source_service_level_model_id": service_level_model_id,
                    "source_inventory_policy_model_id": inventory_policy_model_id,
                    "etl_run_id": etl_run_id,
                    "now": now,
                },
            )
        conn.commit()

        print(f"scenarios_persisted={len(SCENARIO_CATALOG)}", flush=True)
        print(f"timing total_seconds={time.perf_counter() - t0:.1f}", flush=True)

    print("status=SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()
