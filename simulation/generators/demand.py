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
    expected_orders = config.base_daily_order_rate * seasonal_multiplier(current_date, config)
    num_orders = int(rng.poisson(expected_orders))

    for _ in range(num_orders):
        _generate_one_order(session, world, current_date, config, rng, stats)


def _generate_one_order(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    customer_id = world.customer_ids[int(rng.integers(0, len(world.customer_ids)))]
    num_lines = int(rng.integers(1, config.max_lines_per_order + 1))
    # Weighted by each product's Zipf/Pareto demand share (calibration
    # round 2) rather than uniform — see world_init._assign_demand_weights.
    product_indices = rng.choice(
        len(world.product_ids),
        size=num_lines,
        replace=False,
        p=world.product_demand_weights_array,
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

    order_number = f"ORD-{current_date.isoformat()}-{stats.next_seq():08d}"
    order = orders.create_order(
        session,
        order_number=order_number,
        customer_id=customer_id,
        order_date=current_date,
        lines=lines,
    )
    stats.orders_created += 1
    stats.order_lines_created += len(lines)

    order_lines = (
        session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()
    )
    for order_line in order_lines:
        position_id = world.initial_positions[order_line.product_id]
        allocated = orders.allocate_order_line(
            session, order_line_id=order_line.id, inventory_position_id=position_id
        )
        if allocated.backordered_quantity > 0:
            stats.order_lines_backordered += 1
        else:
            stats.order_lines_fully_allocated += 1
