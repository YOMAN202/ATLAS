"""Validation for Module B's reorder-point/safety-stock formula. A
policy recommendation is prescriptive ("do this"), not predictive
("this will happen") — so it can't be validated the way Module A
backtests a forecast or Module D calibrates a probability. The
meaningful question instead is: **if a warehouse actually followed
this policy, would it achieve close to the service level it was
designed for?**

This is answered by a deterministic day-by-day (s, Q) inventory
simulation over each pair's own *real* historical daily demand
(the same series Module A already validates) — not synthetic data.
`order_quantity` exists only to make the simulation runnable; it is
explicitly not an EOQ recommendation (out of scope by instruction) and
is never persisted as policy output. The lead time used to schedule
arrivals is deterministic (the pair's own expected lead time, not a
per-order random draw) — required by the "deterministic, reproducible"
standing rule for this whole optimization engine, and disclosed here
as a simplification: a real warehouse's individual order lead times
vary (Module C/D's own lead_time_stddev_days proves that), but the
simulation tests whether the *safety stock sized for that variability*
is sufficient on average, not whether any single simulated order
happens to arrive late.

Running the same simulation at multiple target service levels (90%/
95%/99%) is both this module's validation report AND its policy
sensitivity analysis in one mechanism: the achieved-vs-target
comparison validates the formula, and the safety-stock/inventory-
investment trend across levels is the sensitivity curve.
"""

from dataclasses import dataclass

SIMULATION_ORDER_QUANTITY_LEAD_TIME_MULTIPLE = 2.0


@dataclass
class SimulationResult:
    n_days: int
    n_stockout_days: int
    achieved_service_level: float


def simulate_policy(
    daily_demand: list[float],
    reorder_point: float,
    order_quantity: float,
    lead_time_days: float,
    initial_inventory: float,
) -> SimulationResult:
    """A lost-sales, continuous-review (s, Q) simulation: each day,
    pending orders arrive, demand is deducted (excess demand is lost,
    not backordered -- matching fact_inventory_snapshot's own
    quantity-on-hand semantics), and a new order is placed whenever
    available inventory is at or below the reorder point and no order
    is already in transit.
    """
    if not daily_demand:
        raise ValueError("simulate_policy requires at least one day of demand")

    lead_time_whole_days = max(1, round(lead_time_days))
    available = initial_inventory
    pending_arrival_day: int | None = None
    n_stockout_days = 0

    for day_index, demand in enumerate(daily_demand):
        if pending_arrival_day is not None and day_index >= pending_arrival_day:
            available += order_quantity
            pending_arrival_day = None

        if demand > available:
            n_stockout_days += 1
        available = max(0.0, available - demand)

        if available <= reorder_point and pending_arrival_day is None:
            pending_arrival_day = day_index + lead_time_whole_days

    n_days = len(daily_demand)
    return SimulationResult(
        n_days=n_days,
        n_stockout_days=n_stockout_days,
        achieved_service_level=round(1 - n_stockout_days / n_days, 5),
    )
