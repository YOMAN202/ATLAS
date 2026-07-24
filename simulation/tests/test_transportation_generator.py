from datetime import timedelta

import numpy as np
from app.domains.orders.service import allocate_order_line, create_order
from app.domains.shared.lookups import get_code_by_id
from app.models import InventoryPosition, OrderLine, Shipment, ShipmentStatus
from sqlalchemy import select

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.transportation import (
    advance_pending_shipments,
    generate_shipments_for_allocated_lines,
)
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats


def _fully_allocated_line(db_session, world):
    product_id = world.product_ids[0]
    position_id = world.initial_positions[product_id]
    unit_cost, unit_price = world.product_prices[product_id]
    customer_id = world.customer_ids[0]

    order = create_order(
        db_session,
        order_number="ORD-SIM-TEST-1",
        customer_id=customer_id,
        order_date=TEST_CONFIG.start_date,
        lines=[
            {
                "product_id": product_id,
                "line_number": 1,
                "ordered_quantity": 5,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
            }
        ],
    )
    line = db_session.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalar_one()
    allocate_order_line(db_session, order_line_id=line.id, inventory_position_id=position_id)
    return db_session.get(OrderLine, line.id)


# Dispatch: a fully-allocated line is picked (inventory decrements) and
# linked to the shipment fulfilling it.
def test_dispatch_picks_inventory_and_links_shipment(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    line = _fully_allocated_line(db_session, world)
    position_id = world.initial_positions[line.product_id]
    on_hand_before = db_session.get(InventoryPosition, position_id).quantity_on_hand
    stats = SimulationStats()

    generate_shipments_for_allocated_lines(
        db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats
    )

    reloaded_line = db_session.get(OrderLine, line.id)
    assert reloaded_line.shipment_id is not None
    assert stats.shipments_created == 1

    position = db_session.get(InventoryPosition, position_id)
    assert position.quantity_on_hand == on_hand_before - 5
    assert position.quantity_reserved == 0

    shipment = db_session.get(Shipment, reloaded_line.shipment_id)
    assert get_code_by_id(db_session, ShipmentStatus, shipment.status_id) == "CREATED"
    assert len(world.pending_shipments) == 1


def test_shipment_never_dispatched_twice(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    _fully_allocated_line(db_session, world)
    stats = SimulationStats()

    generate_shipments_for_allocated_lines(
        db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats
    )
    generate_shipments_for_allocated_lines(
        db_session, world, TEST_CONFIG.start_date + timedelta(days=1), TEST_CONFIG, rng, stats
    )

    assert stats.shipments_created == 1


# FR-3.3: the shipment progresses CREATED -> PICKED -> IN_TRANSIT -> DELIVERED
# across the following days, never skipping ahead of its schedule.
def test_shipment_lifecycle_advances_and_reports_delivery(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    line = _fully_allocated_line(db_session, world)
    stats = SimulationStats()
    generate_shipments_for_allocated_lines(
        db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats
    )
    shipment_id = db_session.get(OrderLine, line.id).shipment_id

    current_date = TEST_CONFIG.start_date
    delivered_events = []
    for _ in range(15):
        current_date += timedelta(days=1)
        delivered_events += advance_pending_shipments(db_session, world, current_date, stats)
        if not world.pending_shipments:
            break

    assert stats.shipments_delivered == 1
    assert len(delivered_events) == 1
    assert delivered_events[0][0] == line.id

    shipment = db_session.get(Shipment, shipment_id)
    assert get_code_by_id(db_session, ShipmentStatus, shipment.status_id) == "DELIVERED"
    assert shipment.actual_delivery_date is not None
