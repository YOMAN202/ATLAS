"""Scenario simulation formulas (Phase 7.2 Module E). Every scenario
recomputes Modules A/C/D/B's own frozen formulas over *perturbed, in-
memory* inputs — never touching a warehouse fact table, never editing
those modules' code. See docs/phase7-2-architecture.md §1 for the full
design rationale ("copied analytical state" = Python values, not a
database copy; a precomputed scenario library, not live user
submission).

`PairBaseline` is the union of what Module D's stockout/backorder
formulas and Module B's policy formula each need — one bundle per
(product, warehouse) pair, loaded once from real data, then either
passed through unmodified (the baseline) or transformed by a scenario
(`apply_scenario_transformation`) before being fed to the same
formulas again.
"""

from dataclasses import dataclass, replace

from app.decision_support.inventory_policy import compute_policy_recommendation
from app.decision_support.service_level import (
    compute_backorder_probability,
    compute_stockout_probability,
)

STOCKOUT_HORIZON_DAYS = 30
HIGH_STOCKOUT_RISK_THRESHOLD = 0.5


@dataclass(frozen=True)
class PairBaseline:
    product_key: int
    warehouse_key: int
    avg_daily_demand: float
    demand_stddev: float
    lead_time_days: float
    lead_time_stddev_days: float
    current_available_quantity: float
    n_historical_days: int
    n_historical_stockout_days: int
    population_stockout_rate: float
    historical_min_available_on_safe_days: float | None
    n_historical_lines: int
    n_historical_backordered_lines: int
    primary_supplier_key: int | None
    active_days: int
    n_deliveries: int
    unit_cost: float


@dataclass
class PairScenarioMetrics:
    stockout_probability: float
    backorder_probability: float
    safety_stock: float
    inventory_investment: float
    service_level: float
    procurement_volume: float


def compute_pair_metrics(
    baseline: PairBaseline, target_service_level: float
) -> PairScenarioMetrics:
    """Runs Modules D's and B's own formulas, unmodified, over whatever
    PairBaseline is handed to it — the real or the transformed one."""
    stockout = compute_stockout_probability(
        baseline.current_available_quantity,
        baseline.n_historical_days,
        baseline.n_historical_stockout_days,
        baseline.population_stockout_rate,
        baseline.historical_min_available_on_safe_days,
        baseline.avg_daily_demand * STOCKOUT_HORIZON_DAYS,
        baseline.demand_stddev * (STOCKOUT_HORIZON_DAYS**0.5),
        baseline.active_days,
    )
    backorder = compute_backorder_probability(
        stockout.probability, baseline.n_historical_lines, baseline.n_historical_backordered_lines
    )
    policy = compute_policy_recommendation(
        product_key=baseline.product_key,
        warehouse_key=baseline.warehouse_key,
        avg_daily_demand=baseline.avg_daily_demand,
        demand_stddev=baseline.demand_stddev,
        lead_time_days=baseline.lead_time_days,
        lead_time_stddev_days=baseline.lead_time_stddev_days,
        current_available_quantity=baseline.current_available_quantity,
        primary_supplier_key=baseline.primary_supplier_key,
        active_days=baseline.active_days,
        n_deliveries=baseline.n_deliveries,
        target_service_level=target_service_level,
    )
    return PairScenarioMetrics(
        stockout_probability=stockout.probability,
        backorder_probability=backorder.probability,
        safety_stock=policy.safety_stock,
        inventory_investment=policy.safety_stock * baseline.unit_cost,
        service_level=1 - stockout.probability,
        procurement_volume=baseline.avg_daily_demand * STOCKOUT_HORIZON_DAYS,
    )


def apply_scenario_transformation(
    scenario_type: str,
    parameters: dict,
    baseline: PairBaseline,
    target_supplier_key: int | None = None,
    target_warehouse_key: int | None = None,
) -> PairBaseline:
    """Returns a NEW PairBaseline with the scenario's perturbation
    applied — the original is never mutated, so the caller always still
    has the real baseline to compare against. A pair not targeted by a
    supplier- or warehouse-scoped scenario is returned unchanged.
    """
    if scenario_type == "demand_surge":
        pct = parameters["pct"]
        return replace(
            baseline,
            avg_daily_demand=baseline.avg_daily_demand * (1 + pct),
            demand_stddev=baseline.demand_stddev * (1 + pct),
        )

    if scenario_type == "demand_decline":
        pct = parameters["pct"]
        return replace(
            baseline,
            avg_daily_demand=baseline.avg_daily_demand * (1 - pct),
            demand_stddev=baseline.demand_stddev * (1 - pct),
        )

    if scenario_type == "supplier_disruption":
        if baseline.primary_supplier_key != target_supplier_key:
            return baseline
        pct = parameters["pct"]
        return replace(
            baseline,
            lead_time_stddev_days=baseline.lead_time_stddev_days * (1 + pct),
        )

    if scenario_type == "lead_time_inflation":
        added_days = parameters["added_days"]
        return replace(baseline, lead_time_days=baseline.lead_time_days + added_days)

    if scenario_type == "warehouse_outage":
        if baseline.warehouse_key != target_warehouse_key:
            return baseline
        outage_pct = parameters["outage_pct"]
        return replace(
            baseline,
            current_available_quantity=baseline.current_available_quantity * (1 - outage_pct),
        )

    if scenario_type in ("inventory_policy_change", "service_level_target_change"):
        # These scenarios change the TARGET service level passed to the
        # formulas, not any PairBaseline field -- handled by the caller
        # (run_module_e.py) via a different target_service_level
        # argument to compute_pair_metrics, not here.
        return baseline

    if scenario_type == "combined":
        result = baseline
        for sub_type, sub_params in parameters["components"]:
            result = apply_scenario_transformation(
                sub_type, sub_params, result, target_supplier_key, target_warehouse_key
            )
        return result

    raise ValueError(f"Unknown scenario_type: {scenario_type}")
