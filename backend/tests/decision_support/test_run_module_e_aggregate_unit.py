"""Direct tests of run_module_e.py's own aggregation logic
(_aggregate), which turns a list of per-pair PairScenarioMetrics into
the scenario-level summary ds_scenario_result persists. Everything
this aggregates from (compute_pair_metrics, apply_scenario_transformation)
is already unit-tested in test_scenario_simulation_unit.py — this file
only proves the aggregation arithmetic itself, with hand-computable
values.
"""

import pytest

from app.decision_support.run_module_e import SCENARIO_CATALOG, _aggregate
from app.decision_support.scenario_simulation import (
    HIGH_STOCKOUT_RISK_THRESHOLD,
    PairBaseline,
    PairScenarioMetrics,
)


def _baseline(**overrides) -> PairBaseline:
    defaults = dict(
        product_key=1,
        warehouse_key=1,
        avg_daily_demand=10.0,
        demand_stddev=2.0,
        lead_time_days=7.0,
        lead_time_stddev_days=1.0,
        current_available_quantity=100.0,
        n_historical_days=200,
        n_historical_stockout_days=5,
        population_stockout_rate=0.02,
        historical_min_available_on_safe_days=10.0,
        n_historical_lines=50,
        n_historical_backordered_lines=3,
        primary_supplier_key=9,
        active_days=150,
        n_deliveries=40,
        unit_cost=15.0,
    )
    defaults.update(overrides)
    return PairBaseline(**defaults)


def _metrics(**overrides) -> PairScenarioMetrics:
    defaults = dict(
        stockout_probability=0.1,
        backorder_probability=0.05,
        safety_stock=20.0,
        inventory_investment=300.0,
        service_level=0.9,
        procurement_volume=300.0,
    )
    defaults.update(overrides)
    return PairScenarioMetrics(**defaults)


def test_aggregate_averages_probabilities_and_sums_totals():
    baselines = [
        _baseline(product_key=1, primary_supplier_key=9),
        _baseline(product_key=2, primary_supplier_key=10),
    ]
    metrics = [
        _metrics(stockout_probability=0.10, inventory_investment=300.0, procurement_volume=300.0),
        _metrics(stockout_probability=0.20, inventory_investment=500.0, procurement_volume=400.0),
    ]

    agg = _aggregate(metrics, baselines)

    assert agg["avg_stockout_probability"] == pytest.approx(0.15)  # (0.10 + 0.20) / 2
    assert agg["inventory_investment"] == 800.0  # 300 + 500 (a total, not an average)
    assert agg["procurement_volume"] == 700.0
    assert agg["n_suppliers_utilized"] == 2  # two distinct primary_supplier_key values


def test_aggregate_counts_distinct_suppliers_not_pairs():
    # Two pairs sharing the SAME primary supplier must count as 1
    # supplier utilized, not 2 -- the whole point of "supplier
    # utilization" as a distinct metric from pair count.
    baselines = [
        _baseline(product_key=1, primary_supplier_key=9),
        _baseline(product_key=2, primary_supplier_key=9),
        _baseline(product_key=3, primary_supplier_key=None),
    ]
    metrics = [_metrics() for _ in baselines]

    agg = _aggregate(metrics, baselines)

    assert agg["n_suppliers_utilized"] == 1


def test_aggregate_counts_high_stockout_risk_pairs_above_threshold():
    baselines = [_baseline(product_key=i) for i in range(3)]
    metrics = [
        _metrics(stockout_probability=HIGH_STOCKOUT_RISK_THRESHOLD + 0.01),
        _metrics(stockout_probability=HIGH_STOCKOUT_RISK_THRESHOLD),  # not strictly greater
        _metrics(stockout_probability=HIGH_STOCKOUT_RISK_THRESHOLD - 0.01),
    ]

    agg = _aggregate(metrics, baselines)

    assert agg["n_high_stockout_risk"] == 1


def test_scenario_catalog_names_are_unique():
    # ds_scenario.uq_ds_scenario_name_model requires this -- a
    # duplicate name would silently overwrite one scenario's row on
    # persist rather than failing loudly.
    names = [name for _type, name, _params, _desc in SCENARIO_CATALOG]
    assert len(names) == len(set(names))


def test_scenario_catalog_every_entry_has_a_description():
    for _type, _name, _params, description in SCENARIO_CATALOG:
        assert isinstance(description, str)
        assert len(description) > 0
