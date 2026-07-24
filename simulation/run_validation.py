"""Phase 3 validation run: full target world size (TDD §10), a 90-day
(~3-month) window — Roadmap risk mitigation: "validate realism early on
a 3-month run before generating the full 5-year run." This is NOT the
full-scale generation; that requires separate approval per the Phase 3
review gate agreed with the project owner.
"""

import time

from simulation.config.world_state import DEFAULT_VALIDATION_CONFIG
from simulation.db import session_scope
from simulation.engine import initialize_world, run


def main() -> None:
    config = DEFAULT_VALIDATION_CONFIG
    print(
        f"Starting validation run: seed={config.seed}, {config.num_days} days, "
        f"{config.num_warehouses} warehouses, {config.num_skus} SKUs, "
        f"{config.num_suppliers} suppliers, {config.num_customers} customers, "
        f"{config.num_carriers} carriers, start={config.start_date}",
        flush=True,
    )

    with session_scope() as session:
        t0 = time.perf_counter()
        world = initialize_world(session, config)
        t1 = time.perf_counter()
        print(f"World initialized in {t1 - t0:.1f}s", flush=True)

        def _report_progress(day_index: int, stats) -> None:
            elapsed = time.perf_counter() - t1
            print(
                f"Day {day_index}/{config.num_days} committed "
                f"({elapsed:.0f}s elapsed, {stats.orders_created} orders so far)",
                flush=True,
            )

        stats = run(
            session,
            world,
            config,
            commit_every_n_days=1,
            on_day_committed=_report_progress,
        )
        t2 = time.perf_counter()
        print(
            f"Simulation run completed in {t2 - t1:.1f}s (total {t2 - t0:.1f}s)",
            flush=True,
        )

        print("--- Stats ---", flush=True)
        for field_name in stats.__dataclass_fields__:
            if field_name.startswith("_"):
                continue
            print(f"{field_name}: {getattr(stats, field_name)}", flush=True)


if __name__ == "__main__":
    main()
