"""Day-advancing simulation engine (Phase 3): the single place that
orchestrates the generators in a fixed order, once per simulated day.

Determinism: one seeded numpy Generator is created here and threaded
through every generator call, in the same fixed order every day, so the
same WorldStateConfig always produces the same sequence of writes.
Nothing here reads the OLAP warehouse or Decision Support output
(Master Prompt §9) — this is a pure OLTP producer via Domain Services
(ADR-007); it never writes to a table directly.
"""

from datetime import date, timedelta

import numpy as np
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators import demand, procurement, returns, supplier_delivery, transportation
from simulation.generators.world_init import WorldState, create_world
from simulation.stats import SimulationStats


def initialize_world(session: Session, config: WorldStateConfig) -> WorldState:
    rng = np.random.default_rng(config.seed)
    return create_world(session, config, rng)


def run(session: Session, world: WorldState, config: WorldStateConfig) -> SimulationStats:
    """Advance the simulation config.num_days days from config.start_date,
    calling generators in the same fixed order every day. Returns the
    accumulated run statistics.
    """

    rng = np.random.default_rng(config.seed)
    stats = SimulationStats()
    current_date = config.start_date

    for _ in range(config.num_days):
        _advance_day(session, world, current_date, config, rng, stats)
        session.flush()
        current_date += timedelta(days=1)

    return stats


def _advance_day(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    demand.generate_daily_orders(session, world, current_date, config, rng, stats)
    procurement.run_reorder_heuristic(session, world, current_date, config, rng, stats)
    supplier_delivery.process_due_deliveries(session, world, current_date, config, rng, stats)
    transportation.generate_shipments_for_allocated_lines(
        session, world, current_date, config, rng, stats
    )
    newly_delivered = transportation.advance_pending_shipments(session, world, current_date, stats)
    for order_line_id, delivered_date in newly_delivered:
        returns.schedule_return_check(world, order_line_id, delivered_date, config, rng)
    returns.generate_due_returns(session, world, current_date, config, rng, stats)
    returns.process_due_inspections(session, world, current_date, rng, stats)
