"""One-off verification: proves checkpoint/resume produces byte-identical
results to an uninterrupted run, before trusting it for the real 2-year
run. Runs a short (20-day) simulation two ways against the isolated test
schema — straight through, and deliberately interrupted at day 10 then
resumed from a pickled checkpoint — and compares final stats + a few
representative DB aggregates.
"""

import pickle
import subprocess
from dataclasses import replace

from simulation.config.world_state import DEFAULT_VALIDATION_CONFIG
from simulation.db import make_session_factory
from simulation.engine import initialize_world, run

TEST_SCHEMA_URL = "mysql+pymysql://root:changeme_root@mysql:3306/atlas_oltp_test"
VERIFY_DAYS = 20
INTERRUPT_AT_DAY = 10


def _reset_schema() -> None:
    subprocess.run(
        ["alembic", "downgrade", "base"],
        cwd="/backend",
        env={"DATABASE_URL_OLTP": TEST_SCHEMA_URL, "PATH": "/usr/local/bin:/usr/bin:/bin"},
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd="/backend",
        env={"DATABASE_URL_OLTP": TEST_SCHEMA_URL, "PATH": "/usr/local/bin:/usr/bin:/bin"},
        check=True,
        capture_output=True,
    )
    from app.seed.reference_data import seed_reference_data

    factory = make_session_factory(TEST_SCHEMA_URL)
    session = factory()
    seed_reference_data(session)
    session.commit()
    session.close()


def _dataset_snapshot(session) -> dict:
    from sqlalchemy import text

    return {
        table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        for table in (
            "orders",
            "order_lines",
            "purchase_orders",
            "shipments",
            "returns",
            "inventory_transactions",
        )
    }


def main() -> None:
    config = replace(DEFAULT_VALIDATION_CONFIG, num_days=VERIFY_DAYS)

    print("=== Run A: straight through, no interruption ===", flush=True)
    _reset_schema()
    factory = make_session_factory(TEST_SCHEMA_URL)
    session = factory()
    world_a = initialize_world(session, config)
    session.commit()
    stats_a = run(session, world_a, config, commit_every_n_days=1)
    session.commit()
    snapshot_a = _dataset_snapshot(session)
    session.close()
    print(f"Run A final stats: {stats_a}", flush=True)
    print(f"Run A dataset: {snapshot_a}", flush=True)

    print("\n=== Run B: interrupted at day 10, resumed from checkpoint ===", flush=True)
    _reset_schema()
    factory = make_session_factory(TEST_SCHEMA_URL)
    session = factory()
    world_b = initialize_world(session, config)
    session.commit()

    checkpoint = {}

    def _checkpoint_at_10(day_index, stats_now, rng_now):
        if day_index == INTERRUPT_AT_DAY:
            checkpoint["day_index"] = day_index
            checkpoint["world"] = pickle.loads(pickle.dumps(world_b))
            checkpoint["rng"] = pickle.loads(pickle.dumps(rng_now))
            checkpoint["stats"] = pickle.loads(pickle.dumps(stats_now))

    # "Crash" after day 10 by only running num_days=10, capturing a
    # checkpoint via the callback right at the interruption point.
    partial_config = replace(config, num_days=INTERRUPT_AT_DAY)
    run(session, world_b, partial_config, commit_every_n_days=1, on_day_committed=_checkpoint_at_10)
    session.commit()
    session.close()
    print(f"Interrupted after day {INTERRUPT_AT_DAY}, checkpoint captured.", flush=True)

    # Resume: fresh session (simulating a fresh process), using the
    # pickled (round-tripped, exactly as a real crash/resume would) state.
    session = factory()
    stats_b = run(
        session,
        checkpoint["world"],
        config,
        commit_every_n_days=1,
        resume_from_day_index=checkpoint["day_index"],
        rng=checkpoint["rng"],
        initial_stats=checkpoint["stats"],
    )
    session.commit()
    snapshot_b = _dataset_snapshot(session)
    session.close()
    print(f"Run B final stats: {stats_b}", flush=True)
    print(f"Run B dataset: {snapshot_b}", flush=True)

    print("\n=== Comparison ===", flush=True)
    stats_match = stats_a == stats_b
    dataset_match = snapshot_a == snapshot_b
    print(f"Stats match: {stats_match}", flush=True)
    print(f"Dataset counts match: {dataset_match}", flush=True)
    if not stats_match:
        print(f"  A: {stats_a}", flush=True)
        print(f"  B: {stats_b}", flush=True)
    if not dataset_match:
        print(f"  A: {snapshot_a}", flush=True)
        print(f"  B: {snapshot_b}", flush=True)

    if stats_match and dataset_match:
        print("\nVERIFIED: checkpoint/resume produces identical results.", flush=True)
    else:
        print("\nFAILED: checkpoint/resume produces DIFFERENT results.", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
