"""Direct tests of the scenario simulation engine
(backend/app/decision_support/scenario_simulation.py). The
transformation functions are tested for exact, hand-computable
before/after values; compute_pair_metrics is tested for correct wiring
into Modules D/B's own already-unit-tested formulas (arithmetic
identities like service_level == 1 - stockout_probability), not
re-deriving their math.
"""

import pytest

from app.decision_support.scenario_simulation import (
    PairBaseline,
    apply_scenario_transformation,
    compute_pair_metrics,
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


def test_demand_surge_scales_demand_and_stddev_by_the_same_factor():
    baseline = _baseline(avg_daily_demand=10.0, demand_stddev=2.0)
    result = apply_scenario_transformation("demand_surge", {"pct": 0.5}, baseline)
    assert result.avg_daily_demand == 15.0  # 10 * 1.5
    assert result.demand_stddev == 3.0  # 2 * 1.5
    assert result.lead_time_days == baseline.lead_time_days  # untouched


def test_demand_decline_scales_demand_and_stddev_down():
    baseline = _baseline(avg_daily_demand=10.0, demand_stddev=2.0)
    result = apply_scenario_transformation("demand_decline", {"pct": 0.2}, baseline)
    assert result.avg_daily_demand == 8.0  # 10 * 0.8
    assert result.demand_stddev == 1.6  # 2 * 0.8


def test_supplier_disruption_only_affects_the_targeted_supplier():
    targeted = _baseline(primary_supplier_key=9, lead_time_stddev_days=1.0)
    untargeted = _baseline(primary_supplier_key=99, lead_time_stddev_days=1.0)

    targeted_result = apply_scenario_transformation(
        "supplier_disruption", {"pct": 1.0}, targeted, target_supplier_key=9
    )
    untargeted_result = apply_scenario_transformation(
        "supplier_disruption", {"pct": 1.0}, untargeted, target_supplier_key=9
    )

    assert targeted_result.lead_time_stddev_days == 2.0  # 1.0 * (1 + 1.0)
    assert untargeted_result == untargeted  # unchanged, exact dataclass equality


def test_lead_time_inflation_adds_days_uniformly_regardless_of_target():
    baseline = _baseline(lead_time_days=7.0)
    result = apply_scenario_transformation("lead_time_inflation", {"added_days": 5}, baseline)
    assert result.lead_time_days == 12.0


def test_warehouse_outage_only_reduces_available_quantity_in_the_targeted_warehouse():
    targeted = _baseline(warehouse_key=1, current_available_quantity=100.0)
    untargeted = _baseline(warehouse_key=2, current_available_quantity=100.0)

    targeted_result = apply_scenario_transformation(
        "warehouse_outage", {"outage_pct": 0.6}, targeted, target_warehouse_key=1
    )
    untargeted_result = apply_scenario_transformation(
        "warehouse_outage", {"outage_pct": 0.6}, untargeted, target_warehouse_key=1
    )

    assert targeted_result.current_available_quantity == 40.0  # 100 * (1 - 0.6)
    assert untargeted_result == untargeted


def test_combined_scenario_applies_every_component_in_sequence():
    baseline = _baseline(avg_daily_demand=10.0, lead_time_days=7.0)
    result = apply_scenario_transformation(
        "combined",
        {
            "components": [
                ("demand_surge", {"pct": 0.5}),
                ("lead_time_inflation", {"added_days": 3}),
            ]
        },
        baseline,
    )
    assert result.avg_daily_demand == 15.0
    assert result.lead_time_days == 10.0


def test_policy_change_scenarios_leave_the_baseline_untouched():
    # These scenarios change the target_service_level argument passed
    # to compute_pair_metrics, not any PairBaseline field.
    baseline = _baseline()
    result = apply_scenario_transformation("inventory_policy_change", {}, baseline)
    assert result == baseline


def test_unknown_scenario_type_raises():
    with pytest.raises(ValueError):
        apply_scenario_transformation("not_a_real_scenario", {}, _baseline())


def test_compute_pair_metrics_wires_module_outputs_correctly():
    baseline = _baseline(avg_daily_demand=10.0, unit_cost=15.0)
    metrics = compute_pair_metrics(baseline, target_service_level=0.95)

    # Arithmetic identities that must hold regardless of the exact
    # stockout/safety-stock values (those formulas are already unit-
    # tested in their own modules) -- this just proves correct wiring.
    assert metrics.service_level == 1 - metrics.stockout_probability
    assert metrics.inventory_investment == metrics.safety_stock * baseline.unit_cost
    assert metrics.procurement_volume == baseline.avg_daily_demand * 30
    assert 0.0 <= metrics.stockout_probability <= 1.0
    assert 0.0 <= metrics.backorder_probability <= 1.0
