"""Day-advancing simulation engine (Phase 3): the single place that
orchestrates the generators in a fixed order, once per simulated day.

Determinism: one seeded numpy Generator is created here and threaded
through every generator call, in the same fixed order every day, so the
same WorldStateConfig always produces the same sequence of writes.
Nothing here reads the OLAP warehouse or Decision Support output
(Master Prompt §9) — this is a pure OLTP producer via Domain Services
(ADR-007); it never writes to a table directly.
"""

from collections.abc import Callable
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


def run(
    session: Session,
    world: WorldState,
    config: WorldStateConfig,
    *,
    commit_every_n_days: int | None = None,
    on_day_committed: Callable[[int, SimulationStats, np.random.Generator], None] | None = None,
    resume_from_day_index: int = 0,
    rng: np.random.Generator | None = None,
    initial_stats: SimulationStats | None = None,
) -> SimulationStats:
    """Advance the simulation config.num_days days from config.start_date,
    calling generators in the same fixed order every day. Returns the
    accumulated run statistics.

    commit_every_n_days is opt-in and None by default, which preserves the
    original behavior relied on by tests (flush only; a single session
    owned and committed once by the caller, per db.py's contract) — tests
    run inside a SAVEPOINT-based transaction that a mid-test commit() would
    break (see conftest.py).

    Long standalone runs (e.g. run_validation.py) should pass a real value:
    without it, one multi-day transaction and one ever-growing SQLAlchemy
    identity map both accumulate for the entire run, and per-operation cost
    was observed to degrade substantially over a multi-hour run (~178
    rows/sec average dropping to ~61 rows/sec after ~1.5M rows). Committing
    and expunging periodically keeps both bounded, and also gives durable,
    observable per-day progress instead of an opaque single final commit.

    Resuming after a crash (resume_from_day_index > 0): pass the exact
    `rng` and `initial_stats` objects recovered from a checkpoint taken
    right after resume_from_day_index days were committed — anything else
    breaks determinism (wrong rng stream position) and business-key
    uniqueness (stats._sequence would restart and collide with already-
    committed order/PO/shipment numbers). The caller is responsible for
    having actually committed exactly that many days already; this
    function trusts resume_from_day_index and starts at
    config.start_date + resume_from_day_index days. on_day_committed
    receives the live `rng` object so callers can checkpoint it.
    """

    rng = rng if rng is not None else np.random.default_rng(config.seed)
    stats = initial_stats if initial_stats is not None else SimulationStats()
    current_date = config.start_date + timedelta(days=resume_from_day_index)

    for day_index in range(resume_from_day_index, config.num_days):
        _advance_day(session, world, current_date, config, rng, stats)
        session.flush()
        current_date += timedelta(days=1)

        if commit_every_n_days and (day_index + 1) % commit_every_n_days == 0:
            session.commit()
            session.expunge_all()
            if on_day_committed:
                on_day_committed(day_index + 1, stats, rng)

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
