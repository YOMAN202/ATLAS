"""Shared test-only helpers for simulation generator tests."""

from app.domains import inventory
from app.models import InventoryPosition

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.time_utils import as_datetime


def drain_below_threshold(
    db_session, world: WorldState, product_id: int, config: WorldStateConfig
) -> None:
    """Pick enough stock from a product's seeded position to push it
    below the reorder threshold, so a test can exercise the reorder
    heuristic without waiting for organic demand to deplete it."""

    position_id = world.initial_positions[product_id]
    position = db_session.get(InventoryPosition, position_id)
    drain = position.quantity_on_hand - config.reorder_threshold_units + 1
    inventory.record_transaction(
        db_session,
        inventory_position_id=position_id,
        transaction_type_code="PICK",
        quantity_delta=-drain,
        occurred_at=as_datetime(config.start_date),
    )
