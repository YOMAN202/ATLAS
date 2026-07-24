from datetime import timedelta

import numpy as np
from app.models import InventoryPosition

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.procurement import run_reorder_heuristic
from simulation.generators.supplier_delivery import process_due_deliveries
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats
from simulation.tests.helpers import drain_below_threshold


def test_delivery_not_processed_before_due_date(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    product_id = world.product_ids[0]
    drain_below_threshold(db_session, world, product_id, TEST_CONFIG)
    stats = SimulationStats()
    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    process_due_deliveries(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    assert stats.purchase_order_lines_received == 0
    assert product_id in world.products_with_open_po


# BR-2/FR-1.3: the delivery increases on-hand and the PO reaches FULFILLED
# once its actual (possibly late) delivery date arrives.
def test_delivery_processed_on_actual_delivery_date(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    product_id = world.product_ids[0]
    drain_below_threshold(db_session, world, product_id, TEST_CONFIG)
    stats = SimulationStats()
    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    position_id = world.initial_positions[product_id]
    on_hand_before = db_session.get(InventoryPosition, position_id).quantity_on_hand

    entry = next(e for e in world.pending_po_deliveries if e["product_id"] == product_id)
    due_date = entry["actual_delivery_date"]

    process_due_deliveries(db_session, world, due_date, TEST_CONFIG, rng, stats)

    assert stats.purchase_order_lines_received == 1
    assert stats.purchase_orders_fulfilled == 1
    assert product_id not in world.products_with_open_po
    assert not any(e["product_id"] == product_id for e in world.pending_po_deliveries)

    on_hand_after = db_session.get(InventoryPosition, position_id).quantity_on_hand
    assert on_hand_after > on_hand_before


def test_delivery_far_future_date_never_processed_early(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    product_id = world.product_ids[0]
    drain_below_threshold(db_session, world, product_id, TEST_CONFIG)
    stats = SimulationStats()
    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    entry = next(e for e in world.pending_po_deliveries if e["product_id"] == product_id)
    day_before_due = entry["actual_delivery_date"] - timedelta(days=1)

    process_due_deliveries(db_session, world, day_before_due, TEST_CONFIG, rng, stats)

    assert stats.purchase_order_lines_received == 0
