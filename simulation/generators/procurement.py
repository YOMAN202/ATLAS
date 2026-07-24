"""Purchase Order Generator — the simulation's internal reorder heuristic
(FR-1.2), which triggers PO creation during data generation through the
procurement Domain Service to populate procurement history.

This heuristic is deliberately simple (a fixed on-hand threshold and a
fixed reorder quantity, both config-driven) and is a *separate code path*
from the Phase 7 Decision Support reorder recommendation (BR-3: average
daily demand x lead time + safety stock, computed from the OLAP
warehouse). The two must never be conflated or share logic — this
generator does not import anything from a future decision_support module,
and does not implement BR-3's formula.
"""

from datetime import date, timedelta

import numpy as np
from app.domains import procurement
from app.models import InventoryPosition, PurchaseOrderLine, Supplier
from sqlalchemy import select
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.stats import SimulationStats


def run_reorder_heuristic(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    for product_id in world.product_ids:
        if product_id in world.products_with_open_po:
            continue

        position_id = world.initial_positions[product_id]
        position = session.get(InventoryPosition, position_id)
        if position.quantity_on_hand >= config.reorder_threshold_units:
            continue

        _create_reorder(session, world, product_id, position, current_date, config, rng, stats)


def _create_reorder(
    session: Session,
    world: WorldState,
    product_id: int,
    position: InventoryPosition,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    supplier_ids = world.product_suppliers[product_id]
    supplier_id = supplier_ids[int(rng.integers(0, len(supplier_ids)))]
    supplier = session.get(Supplier, supplier_id)

    expected_delivery_date = current_date + timedelta(days=supplier.default_lead_time_days)
    unit_cost, _ = world.product_prices[product_id]

    po_number = f"PO-{current_date.isoformat()}-{stats.next_seq():08d}"
    po = procurement.create_purchase_order(
        session,
        po_number=po_number,
        supplier_id=supplier_id,
        warehouse_id=position.warehouse_id,
        order_date=current_date,
        expected_delivery_date=expected_delivery_date,
        lines=[
            {
                "product_id": product_id,
                "line_number": 1,
                "ordered_quantity": config.reorder_quantity_units,
                "unit_cost": unit_cost,
                "expected_delivery_date": expected_delivery_date,
            }
        ],
    )
    procurement.submit_purchase_order(session, po.id)
    procurement.confirm_purchase_order(session, po.id)
    stats.purchase_orders_created += 1

    po_line = session.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
    ).scalar_one()

    is_late = rng.random() < config.late_delivery_probability
    extra_days = int(rng.integers(1, config.late_delivery_extra_days_max + 1)) if is_late else 0
    actual_delivery_date = expected_delivery_date + timedelta(days=extra_days)

    world.pending_po_deliveries.append(
        {
            "po_id": po.id,
            "po_line_id": po_line.id,
            "product_id": product_id,
            "ordered_quantity": config.reorder_quantity_units,
            "actual_delivery_date": actual_delivery_date,
        }
    )
    world.products_with_open_po.add(product_id)
