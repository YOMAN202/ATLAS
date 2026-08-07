"""Supplier delivery generator (TDD §5: "supplier delivery generator
(lead-time distribution + occasional lateness)"). Consumes entries the
procurement reorder heuristic queued in WorldState.pending_po_deliveries
and receives each one through the procurement Domain Service — the only
write path for a PO receipt (BR-1) — applying FR-1.3's quality rejection
rate.

Lateness itself is decided once, at PO-creation time (see
generators/procurement.py), by rolling the actual delivery date forward;
this generator just checks whether that date has arrived.
"""

from datetime import date

import numpy as np
from app.domains import procurement
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.stats import SimulationStats
from simulation.time_utils import as_datetime


def process_due_deliveries(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    still_pending = []

    for entry in world.pending_po_deliveries:
        if entry["actual_delivery_date"] > current_date:
            still_pending.append(entry)
            continue

        _receive_delivery(session, world, entry, current_date, config, rng, stats)

    world.pending_po_deliveries = still_pending


def _receive_delivery(
    session: Session,
    world: WorldState,
    entry: dict,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    ordered_quantity = entry["ordered_quantity"]
    quality_rejected = int(rng.binomial(ordered_quantity, config.quality_rejection_rate))

    # A position's zone never changes after world-init (FR-2.2 — no
    # cross-zone bin-picking), so this is a cached lookup, not a fresh
    # session.get(InventoryPosition, ...) per delivery.
    warehouse_zone_id = world.product_warehouse_zone[entry["product_id"]]

    procurement.receive_purchase_order_line(
        session,
        po_line_id=entry["po_line_id"],
        received_quantity=ordered_quantity,
        quality_rejected_quantity=quality_rejected,
        delivery_date=current_date,
        warehouse_zone_id=warehouse_zone_id,
        occurred_at=as_datetime(current_date),
    )
    stats.purchase_order_lines_received += 1
    # Every reorder-heuristic PO has exactly one line, received in full
    # (quality_rejected is a subset of received_quantity, not a shortfall)
    # so this receipt always satisfies PO_RECEIPT_TOLERANCE and the PO
    # always reaches FULFILLED here — no separate query needed to confirm it.
    stats.purchase_orders_fulfilled += 1

    world.products_with_open_po.discard(entry["product_id"])
