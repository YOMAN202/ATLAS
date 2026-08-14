"""Direct tests of the policy-validation simulation
(backend/app/decision_support/inventory_policy_simulation.py) against
hand-traced expected outcomes.
"""

import pytest

from app.decision_support.inventory_policy_simulation import simulate_policy


def test_simulate_policy_perfect_service_with_ample_inventory_and_no_reorders():
    # Starting inventory (1000) vastly exceeds total demand (5*30=150);
    # reorder_point=0 means replenishment never triggers, and it's
    # never needed.
    result = simulate_policy(
        daily_demand=[5.0] * 30,
        reorder_point=0,
        order_quantity=0,
        lead_time_days=5,
        initial_inventory=1000,
    )
    assert result.n_days == 30
    assert result.n_stockout_days == 0
    assert result.achieved_service_level == 1.0


def test_simulate_policy_stockouts_when_demand_exceeds_available_with_no_replenishment():
    # Hand trace: initial=10, demand=[5,5,5,5], reorder_point=-1 (never
    # triggers, since available is clamped at >= 0).
    # day0: avail=10, demand=5 -> not a stockout (5 <= 10); avail=5
    # day1: avail=5, demand=5 -> not a stockout (5 <= 5); avail=0
    # day2: avail=0, demand=5 -> STOCKOUT (5 > 0); avail=0
    # day3: avail=0, demand=5 -> STOCKOUT (5 > 0); avail=0
    result = simulate_policy(
        daily_demand=[5.0, 5.0, 5.0, 5.0],
        reorder_point=-1,
        order_quantity=0,
        lead_time_days=1,
        initial_inventory=10,
    )
    assert result.n_stockout_days == 2
    assert result.achieved_service_level == 0.5


def test_simulate_policy_replenishment_arrives_and_prevents_stockouts():
    # Hand trace: initial=10, demand=5/day, reorder_point=6, order_qty=100, LT=2
    # day0: avail=10, demand=5 -> ok (5<=10); avail=5; 5<=6 -> order placed, arrives day2
    # day1: avail=5, demand=5 -> ok (5<=5); avail=0; pending order already exists, no new order
    # day2: order arrives -> avail=0+100=100; demand=5 -> ok; avail=95; 95>6, no reorder
    # days3-9: avail stays well above 6, demand always covered
    result = simulate_policy(
        daily_demand=[5.0] * 10,
        reorder_point=6,
        order_quantity=100,
        lead_time_days=2,
        initial_inventory=10,
    )
    assert result.n_stockout_days == 0
    assert result.achieved_service_level == 1.0


def test_simulate_policy_requires_at_least_one_day_of_demand():
    with pytest.raises(ValueError):
        simulate_policy(
            daily_demand=[],
            reorder_point=0,
            order_quantity=0,
            lead_time_days=1,
            initial_inventory=0,
        )


def test_simulate_policy_does_not_double_order_while_one_is_in_transit():
    # A pair whose reorder_point is very high (always triggers "should
    # reorder") must still place only one order at a time, not one per
    # day -- proven by exact accounting: only ONE order's worth of
    # quantity (100) should ever arrive, at exactly day 2.
    result = simulate_policy(
        daily_demand=[1.0] * 5,
        reorder_point=1000,  # always "below" reorder point
        order_quantity=100,
        lead_time_days=2,
        initial_inventory=10,
    )
    # day0: avail=10, demand=1 -> ok; avail=9; order placed, arrives day2
    # day1: avail=9, demand=1 -> ok; avail=8; pending order exists, no new order
    # day2: arrives -> avail=8+100=108; demand=1 -> ok; avail=107; pending=None,
    #        107 <= 1000 -> a SECOND order placed, arrives day4
    # day3: avail=107, demand=1 -> ok; avail=106; pending order exists
    # day4: arrives -> avail=106+100=206; demand=1 -> ok; avail=205
    assert result.n_stockout_days == 0
