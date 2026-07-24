from datetime import timedelta

import numpy as np
from app.domains.shared.lookups import get_code_by_id
from app.models import POStatus, PurchaseOrder, Supplier

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.procurement import run_reorder_heuristic
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats
from simulation.tests.helpers import drain_below_threshold


# FR-1.2: on-hand below threshold triggers a PO through the procurement
# Domain Service, distinct from the (not-yet-built) Phase 7 recommendation.
def test_reorder_triggers_when_below_threshold(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    product_id = world.product_ids[0]
    drain_below_threshold(db_session, world, product_id, TEST_CONFIG)
    stats = SimulationStats()

    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    assert product_id in world.products_with_open_po
    assert stats.purchase_orders_created >= 1
    matching = [e for e in world.pending_po_deliveries if e["product_id"] == product_id]
    assert len(matching) == 1

    po = db_session.get(PurchaseOrder, matching[0]["po_id"])
    assert get_code_by_id(db_session, POStatus, po.status_id) == "CONFIRMED"

    supplier = db_session.get(Supplier, po.supplier_id)
    assert po.expected_delivery_date == TEST_CONFIG.start_date + timedelta(
        days=supplier.default_lead_time_days
    )


def test_reorder_does_not_duplicate_while_po_open(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    product_id = world.product_ids[0]
    drain_below_threshold(db_session, world, product_id, TEST_CONFIG)
    stats = SimulationStats()

    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)
    first_count = stats.purchase_orders_created

    run_reorder_heuristic(
        db_session, world, TEST_CONFIG.start_date + timedelta(days=1), TEST_CONFIG, rng, stats
    )

    assert stats.purchase_orders_created == first_count


def test_reorder_does_not_trigger_above_threshold(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)
    stats = SimulationStats()

    # Freshly seeded positions are always initial_inventory_multiplier x
    # their own product's threshold — by construction, above that
    # threshold for every product — so nothing should reorder yet.
    run_reorder_heuristic(db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, stats)

    assert stats.purchase_orders_created == 0
