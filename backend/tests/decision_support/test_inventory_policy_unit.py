"""Direct tests of the inventory policy formulas
(backend/app/decision_support/inventory_policy.py) against hand-
computable expected values — the same discipline every prior module's
unit tests use: every formula must be independently verifiable by
hand, not just "runs without error" (ADR-004, "no black-box outputs").
"""

from app.decision_support.inventory_policy import (
    compute_policy_recommendation,
    compute_z_score,
)


def test_z_score_is_zero_at_fifty_percent_service_level():
    # The standard-normal distribution's median is 0 exactly -- the
    # one target service level whose Z-score is hand-verifiable
    # without a table.
    assert compute_z_score(0.5) == 0.0


def test_z_score_matches_the_well_known_ninety_five_percent_constant():
    # 1.6449 is the standard, independently-checkable Z-score for a
    # 95% one-sided service level (any statistics textbook/table).
    assert round(compute_z_score(0.95), 4) == 1.6449


def test_policy_recommendation_has_zero_safety_stock_at_fifty_percent_target():
    # z=0 -> safety_stock=0 exactly -> reorder_point = avg_daily_demand
    # * lead_time_days exactly (10 * 7 = 70), a fully hand-verifiable case.
    result = compute_policy_recommendation(
        product_key=1,
        warehouse_key=1,
        avg_daily_demand=10,
        demand_stddev=5,
        lead_time_days=7,
        lead_time_stddev_days=2,
        current_available_quantity=70,
        primary_supplier_key=9,
        active_days=100,
        n_deliveries=50,
        target_service_level=0.5,
    )
    assert result.safety_stock == 0.0
    assert result.reorder_point == 70.0
    assert result.service_level_inventory_target == 70.0
    assert result.balancing_recommendation == "adequate"  # available (70) == ROP (70), not below


def test_policy_recommendation_flags_reorder_now_below_reorder_point():
    result = compute_policy_recommendation(
        product_key=1,
        warehouse_key=1,
        avg_daily_demand=10,
        demand_stddev=5,
        lead_time_days=7,
        lead_time_stddev_days=2,
        current_available_quantity=50,  # below the 70-unit ROP at 50% target
        primary_supplier_key=9,
        active_days=100,
        n_deliveries=50,
        target_service_level=0.5,
    )
    assert result.balancing_recommendation == "reorder_now"
    assert "reorder now" in result.business_rationale.lower()


def test_policy_recommendation_flags_excess_inventory_above_multiplier():
    # EXCESS_INVENTORY_MULTIPLIER (3.0) * ROP (70) = 210
    result = compute_policy_recommendation(
        product_key=1,
        warehouse_key=1,
        avg_daily_demand=10,
        demand_stddev=5,
        lead_time_days=7,
        lead_time_stddev_days=2,
        current_available_quantity=250,
        primary_supplier_key=9,
        active_days=100,
        n_deliveries=50,
        target_service_level=0.5,
    )
    assert result.balancing_recommendation == "excess_inventory"


def test_policy_recommendation_confidence_requires_both_demand_and_supplier_sufficiency():
    both_sufficient = compute_policy_recommendation(
        1, 1, 10, 5, 7, 2, 70, 9, active_days=100, n_deliveries=50, target_service_level=0.5
    )
    thin_demand_history = compute_policy_recommendation(
        1, 1, 10, 5, 7, 2, 70, 9, active_days=40, n_deliveries=50, target_service_level=0.5
    )
    thin_supplier_history = compute_policy_recommendation(
        1, 1, 10, 5, 7, 2, 70, 9, active_days=100, n_deliveries=5, target_service_level=0.5
    )
    assert both_sufficient.confidence == "high"
    assert thin_demand_history.confidence == "medium"
    assert thin_supplier_history.confidence == "medium"


def test_policy_recommendation_contributing_factors_are_traceable():
    result = compute_policy_recommendation(
        1, 1, 10, 5, 7, 2, 70, 9, active_days=100, n_deliveries=50, target_service_level=0.5
    )
    assert result.contributing_factors["avg_daily_demand"] == 10
    assert result.contributing_factors["lead_time_days"] == 7
    assert result.contributing_factors["primary_supplier_key"] == 9
    assert result.contributing_factors["target_service_level"] == 0.5


def test_policy_recommendation_handles_unresolved_supplier_gracefully():
    result = compute_policy_recommendation(
        1, 1, 10, 5, 7, 2, 70, None, active_days=100, n_deliveries=0, target_service_level=0.5
    )
    assert result.contributing_factors["primary_supplier_key"] is None
    assert "unresolved supplier" in result.business_rationale
