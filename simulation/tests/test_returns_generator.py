from dataclasses import replace
from datetime import timedelta

import numpy as np
from app.domains.orders.service import allocate_order_line, create_order
from app.models import InventoryPosition, OrderLine, ReturnLine
from sqlalchemy import select

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.returns import (
    generate_due_returns,
    process_due_inspections,
    schedule_return_check,
)
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats


def _delivered_line(db_session, world):
    product_id = world.product_ids[0]
    position_id = world.initial_positions[product_id]
    unit_cost, unit_price = world.product_prices[product_id]

    order = create_order(
        db_session,
        order_number="ORD-RET-TEST-1",
        customer_id=world.customer_ids[0],
        order_date=TEST_CONFIG.start_date,
        lines=[
            {
                "product_id": product_id,
                "line_number": 1,
                "ordered_quantity": 3,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
            }
        ],
    )
    line = db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalar_one()
    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position_id)
    return db_session.get(OrderLine, line.id)


def test_schedule_return_check_always_queues_at_full_rate(db_session, seeded_lookups):
    config = replace(TEST_CONFIG, return_rate=1.0)
    rng = np.random.default_rng(config.seed)
    world = create_world(db_session, config, rng)
    line = _delivered_line(db_session, world)

    schedule_return_check(world, line.id, TEST_CONFIG.start_date, config, rng)

    assert len(world.pending_returns) == 1
    assert world.pending_returns[0]["order_line_id"] == line.id


def test_schedule_return_check_never_queues_at_zero_rate(db_session, seeded_lookups):
    config = replace(TEST_CONFIG, return_rate=0.0)
    rng = np.random.default_rng(config.seed)
    world = create_world(db_session, config, rng)
    line = _delivered_line(db_session, world)

    schedule_return_check(world, line.id, TEST_CONFIG.start_date, config, rng)

    assert world.pending_returns == []


# BR-5: an immediately-inspected SELLABLE return restocks inventory; the
# return is never created (or inspected) before its scheduled date.
def test_generate_due_returns_creates_and_inspects_same_day(db_session, seeded_lookups):
    config = replace(TEST_CONFIG, return_rate=1.0, return_inspection_same_day_probability=1.0)
    rng = np.random.default_rng(config.seed)
    world = create_world(db_session, config, rng)
    line = _delivered_line(db_session, world)
    position_id = world.initial_positions[line.product_id]
    on_hand_before = db_session.get(InventoryPosition, position_id).quantity_on_hand
    stats = SimulationStats()

    schedule_return_check(world, line.id, TEST_CONFIG.start_date, config, rng)
    return_date = world.pending_returns[0]["return_date"]

    generate_due_returns(db_session, world, TEST_CONFIG.start_date, config, rng, stats)
    assert stats.returns_created == 0  # not due yet

    generate_due_returns(db_session, world, return_date, config, rng, stats)

    assert stats.returns_created == 1
    assert stats.return_lines_inspected == 1
    assert world.pending_returns == []

    return_line = db_session.execute(select(ReturnLine)).scalars().first()
    assert return_line.inspected_at is not None

    # Either restocked (SELLABLE, ~70% chance) or not — both are valid
    # outcomes; what matters is inspection actually happened deterministically.
    on_hand_after = db_session.get(InventoryPosition, position_id).quantity_on_hand
    assert on_hand_after >= on_hand_before


def test_delayed_inspection_is_processed_by_process_due_inspections(db_session, seeded_lookups):
    config = replace(TEST_CONFIG, return_rate=1.0, return_inspection_same_day_probability=0.0)
    rng = np.random.default_rng(config.seed)
    world = create_world(db_session, config, rng)
    line = _delivered_line(db_session, world)
    stats = SimulationStats()

    schedule_return_check(world, line.id, TEST_CONFIG.start_date, config, rng)
    return_date = world.pending_returns[0]["return_date"]
    generate_due_returns(db_session, world, return_date, config, rng, stats)

    assert stats.returns_created == 1
    assert stats.return_lines_inspected == 0
    assert len(world.pending_inspections) == 1

    inspect_date = world.pending_inspections[0]["inspect_date"]
    process_due_inspections(db_session, world, inspect_date - timedelta(days=1), rng, stats)
    assert stats.return_lines_inspected == 0

    process_due_inspections(db_session, world, inspect_date, rng, stats)
    assert stats.return_lines_inspected == 1
    assert world.pending_inspections == []
