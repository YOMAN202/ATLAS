"""End-to-end engine tests: determinism (Master Prompt §9 — same config +
seed yields the same dataset) and rule-consistency across a full,
multi-generator run (Roadmap Phase 3 Testing Requirements).
"""

from app.models import InventoryPosition, OrderLine, PurchaseOrderLine
from app.seed.reference_data import seed_reference_data
from sqlalchemy import select

from simulation.config.world_state import TEST_CONFIG
from simulation.engine import initialize_world, run


def _stats_snapshot(stats) -> dict:
    return {
        "orders_created": stats.orders_created,
        "order_lines_created": stats.order_lines_created,
        "order_lines_fully_allocated": stats.order_lines_fully_allocated,
        "order_lines_backordered": stats.order_lines_backordered,
        "purchase_orders_created": stats.purchase_orders_created,
        "purchase_order_lines_received": stats.purchase_order_lines_received,
        "purchase_orders_fulfilled": stats.purchase_orders_fulfilled,
        "shipments_created": stats.shipments_created,
        "shipments_delivered": stats.shipments_delivered,
        "returns_created": stats.returns_created,
        "return_lines_inspected": stats.return_lines_inspected,
    }


def test_full_run_is_deterministic_given_same_seed(db_session, seeded_lookups):
    world1 = initialize_world(db_session, TEST_CONFIG)
    stats1 = run(db_session, world1, TEST_CONFIG)
    snapshot1 = _stats_snapshot(stats1)

    # Rolling back clears the seeded lookups too — re-seed (idempotent)
    # before the second run.
    db_session.rollback()
    seed_reference_data(db_session)

    world2 = initialize_world(db_session, TEST_CONFIG)
    stats2 = run(db_session, world2, TEST_CONFIG)
    snapshot2 = _stats_snapshot(stats2)

    assert snapshot1 == snapshot2
    assert snapshot1["orders_created"] > 0


def test_full_run_never_violates_inventory_or_order_invariants(db_session, seeded_lookups):
    world = initialize_world(db_session, TEST_CONFIG)
    run(db_session, world, TEST_CONFIG)

    positions = db_session.execute(select(InventoryPosition)).scalars().all()
    assert positions
    for position in positions:
        assert position.quantity_on_hand >= 0
        assert position.quantity_reserved >= 0
        assert position.quantity_reserved <= position.quantity_on_hand

    order_lines = db_session.execute(select(OrderLine)).scalars().all()
    assert order_lines
    for line in order_lines:
        assert line.allocated_quantity + line.backordered_quantity <= line.ordered_quantity

    po_lines = db_session.execute(select(PurchaseOrderLine)).scalars().all()
    for po_line in po_lines:
        assert po_line.received_quantity >= 0
        assert po_line.quality_rejected_quantity <= po_line.received_quantity
