"""Returns generator (FR-4.3): a realistic fraction of delivered order
lines generate a return, with reason codes, feeding back into sellable
inventory only after inspection (BR-5).

Whether a delivered line returns at all, and after how many days, is
decided once at delivery time via `schedule_return_check` (called by the
engine right after transportation.advance_pending_shipments reports a
delivery) — not re-rolled daily. Every write goes through Domain
Services (ADR-007).
"""

from datetime import date, timedelta

import numpy as np
from app.domains import returns
from app.models import OrderLine, ReturnLine
from sqlalchemy import select
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.stats import SimulationStats
from simulation.time_utils import as_datetime

_REASON_CODES = ["DAMAGED", "WRONG_ITEM", "NO_LONGER_NEEDED", "QUALITY_DEFECT", "OTHER"]
_NON_SELLABLE_DISPOSITION_CODES = ["QUARANTINE", "SCRAP", "RETURN_TO_SUPPLIER"]
_SELLABLE_ON_INSPECTION_PROBABILITY = 0.7
_RETURN_DELAY_DAYS_MAX = 10


def schedule_return_check(
    world: WorldState,
    order_line_id: int,
    delivered_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
) -> None:
    """Decide, once, whether a just-delivered line will generate a
    return; if so, queue it for creation a few days later."""

    if rng.random() >= config.return_rate:
        return

    return_date = delivered_date + timedelta(days=int(rng.integers(1, _RETURN_DELAY_DAYS_MAX + 1)))
    world.pending_returns.append({"order_line_id": order_line_id, "return_date": return_date})


def generate_due_returns(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    still_pending = []
    for entry in world.pending_returns:
        if entry["return_date"] > current_date:
            still_pending.append(entry)
            continue
        _create_return(session, world, entry, current_date, config, rng, stats)

    world.pending_returns = still_pending


def _create_return(
    session: Session,
    world: WorldState,
    entry: dict,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    order_line = session.get(OrderLine, entry["order_line_id"])
    reason_code = _REASON_CODES[int(rng.integers(0, len(_REASON_CODES)))]
    return_number = f"RET-{current_date.isoformat()}-{stats.next_seq():08d}"

    ret = returns.create_return(
        session,
        return_number=return_number,
        order_id=order_line.order_id,
        return_date=current_date,
        lines=[
            {
                "order_line_id": order_line.id,
                "line_number": 1,
                "returned_quantity": order_line.allocated_quantity,
                "reason_code": reason_code,
            }
        ],
    )
    stats.returns_created += 1

    return_line = session.execute(
        select(ReturnLine).where(ReturnLine.return_id == ret.id)
    ).scalar_one()

    if rng.random() < config.return_inspection_same_day_probability:
        _inspect(session, world, return_line.id, order_line.product_id, current_date, rng, stats)
    else:
        inspect_date = current_date + timedelta(
            days=int(rng.integers(1, config.return_inspection_extra_days_max + 1))
        )
        world.pending_inspections.append(
            {
                "return_line_id": return_line.id,
                "product_id": order_line.product_id,
                "inspect_date": inspect_date,
            }
        )


def process_due_inspections(
    session: Session,
    world: WorldState,
    current_date: date,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    still_pending = []
    for entry in world.pending_inspections:
        if entry["inspect_date"] > current_date:
            still_pending.append(entry)
            continue
        _inspect(
            session,
            world,
            entry["return_line_id"],
            entry["product_id"],
            current_date,
            rng,
            stats,
        )

    world.pending_inspections = still_pending


def _inspect(
    session: Session,
    world: WorldState,
    return_line_id: int,
    product_id: int,
    current_date: date,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    is_sellable = rng.random() < _SELLABLE_ON_INSPECTION_PROBABILITY
    warehouse_zone_id = None
    if is_sellable:
        # Cached at world-init (FR-2.2 — a position's zone never changes)
        # instead of a fresh session.get(InventoryPosition, ...).
        warehouse_zone_id = world.product_warehouse_zone[product_id]
        disposition_code = "SELLABLE"
    else:
        disposition_code = _NON_SELLABLE_DISPOSITION_CODES[
            int(rng.integers(0, len(_NON_SELLABLE_DISPOSITION_CODES)))
        ]

    returns.inspect_return_line(
        session,
        return_line_id=return_line_id,
        disposition_code=disposition_code,
        inspected_at=as_datetime(current_date),
        warehouse_zone_id=warehouse_zone_id,
    )
    stats.return_lines_inspected += 1
    if disposition_code == "SELLABLE":
        stats.return_lines_sellable += 1
