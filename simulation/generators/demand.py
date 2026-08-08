"""Seasonal demand / order generator (FR-5.3: seasonal/promotional demand
modifiers). Rule-driven, not purely random: the day's order *count* comes
from a seasonality curve (peaking in late November, per typical retail
seasonality) sampled through a Poisson draw, not a flat random number.

Every order is created and allocated through Domain Services only
(ADR-007) — this module never touches OrderLine/InventoryPosition rows
directly. Each order line is allocated against its product's single
seeded inventory position (see generators/world_init.py) — Phase 3 does
not implement multi-warehouse fulfillment routing (FR-2.2 places
"advanced warehouse slotting" out of MVP scope).
"""

import math
from datetime import date

import numpy as np
from app.domains import orders
from app.models import OrderLine
from sqlalchemy import select
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.stats import SimulationStats

_SEASONAL_PEAK_DAY_OF_YEAR = 335  # late November


def _weighted_indices_without_replacement(
    rng: np.random.Generator, weights: np.ndarray, size: int
) -> list[int]:
    """Statistically equivalent to
    rng.choice(len(weights), size=size, replace=False, p=weights), but
    much cheaper: numpy's native replace=False + p= path does real work
    across the *entire* population on every call (an Efraimidis-Spirakis-
    style scheme), regardless of how small `size` is — expensive at
    ~800 calls/day over 5,000 products.

    Instead, draw WITH replacement (cheap: a single vectorized inverse-CDF
    lookup) and re-draw only on collision. This is a standard equivalence
    (rejection sampling for sampling-without-replacement): conditional on
    a draw differing from those already chosen, its distribution is
    exactly proportional to the original weights restricted to the
    remaining items — the same joint "which items get chosen"
    distribution numpy's native path produces, just computed differently.
    Only the *order* items are collected in can differ (a cosmetic detail
    — line_number is a positional label, not something with statistical
    meaning here); which set of products gets chosen is unaffected.
    """

    n = len(weights)
    chosen: list[int] = []
    chosen_set: set[int] = set()
    while len(chosen) < size:
        needed = size - len(chosen)
        for idx in rng.choice(n, size=needed, p=weights):
            idx = int(idx)
            if idx not in chosen_set:
                chosen_set.add(idx)
                chosen.append(idx)
                if len(chosen) == size:
                    break
    return chosen


def seasonal_multiplier(current_date: date, config: WorldStateConfig) -> float:
    """1.0 +/- seasonality_amplitude, peaking at _SEASONAL_PEAK_DAY_OF_YEAR
    and troughing exactly half a year away. Pure function — independently
    testable without a database.
    """

    day_of_year = current_date.timetuple().tm_yday
    phase = 2 * math.pi * (day_of_year - _SEASONAL_PEAK_DAY_OF_YEAR) / 365.0
    return 1.0 + config.seasonality_amplitude * math.cos(phase)


def generate_daily_orders(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    """Build the day's order requests, create them all in one bulk call
    (orders.create_orders_bulk), then allocate every resulting line in a
    second bulk call (orders.allocate_order_lines_bulk).

    Order creation was identified as the single largest per-day cost
    (~34% in steady-state profiling) — it was the one high-volume
    operation left unbatched (~1,000+ individual create_order() calls/day,
    each with its own two flushes) after allocation, dispatch, and status
    advancement were already batched.

    RNG draws (customer, product selection, quantities) happen while
    building each order's request dict, in the same per-order sequence as
    before — no DB writes happen until after all of the day's orders have
    been built, so the draw sequence, and therefore determinism, is
    unaffected by deferring the actual inserts to one bulk call.
    """

    expected_orders = config.base_daily_order_rate * seasonal_multiplier(current_date, config)
    num_orders = int(rng.poisson(expected_orders))

    order_requests = [
        _build_one_order_request(world, current_date, config, rng, stats) for _ in range(num_orders)
    ]
    if not order_requests:
        return

    created_orders = orders.create_orders_bulk(session, orders=order_requests)
    stats.orders_created += len(created_orders)
    stats.order_lines_created += sum(len(request["lines"]) for request in order_requests)

    order_ids = [order.id for order in created_orders]
    created_order_lines = (
        session.execute(select(OrderLine).where(OrderLine.order_id.in_(order_ids))).scalars().all()
    )

    allocations = [
        {
            "order_line_id": order_line.id,
            "inventory_position_id": world.initial_positions[order_line.product_id],
        }
        for order_line in created_order_lines
    ]
    allocated_lines = orders.allocate_order_lines_bulk(session, allocations=allocations)

    for allocated in allocated_lines:
        if allocated.backordered_quantity > 0:
            stats.order_lines_backordered += 1
        else:
            stats.order_lines_fully_allocated += 1


def _build_one_order_request(
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> dict:
    """Draw one order's customer/products/quantities and return it as a
    plain dict — no DB writes here; the caller collects a whole day's
    worth of these and creates them in one bulk call."""

    customer_id = world.customer_ids[int(rng.integers(0, len(world.customer_ids)))]
    num_lines = int(rng.integers(1, config.max_lines_per_order + 1))
    # Weighted by each product's Zipf/Pareto demand share (calibration
    # round 2) rather than uniform — see world_init._assign_demand_weights.
    product_indices = _weighted_indices_without_replacement(
        rng, world.product_demand_weights_array, num_lines
    )

    lines = []
    for line_number, idx in enumerate(product_indices, start=1):
        product_id = world.product_ids[int(idx)]
        unit_cost, unit_price = world.product_prices[product_id]
        quantity = int(rng.integers(config.min_line_quantity, config.max_line_quantity + 1))
        lines.append(
            {
                "product_id": product_id,
                "line_number": line_number,
                "ordered_quantity": quantity,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
            }
        )

    return {
        "order_number": f"ORD-{current_date.isoformat()}-{stats.next_seq():08d}",
        "customer_id": customer_id,
        "order_date": current_date,
        "lines": lines,
    }
