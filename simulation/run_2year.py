"""Phase 3 final artifact: the 730-day (2-year) generation run.

Full target world size (TDD §10), full target duration for this revised
Phase 3 scope (2 years, changed down from the original 5-year target for
practical overnight runtime — see the Phase 3 final optimization + 2-year
validation review). Gated behind the Phase A/B/C optimization and
validation work; not to be run without that review having passed.

Checkpointed: the in-memory WorldState, RNG, and stats are pickled to
disk every CHECKPOINT_EVERY_N_DAYS, right after that day's DB commit
(never before — a checkpoint must always describe a state that's already
durable in the database, or resuming from it could re-derive data
inconsistent with what's actually committed). On a crash, re-running this
script resumes from the last checkpoint instead of redoing the whole run.
The checkpoint file lives under simulation/ (the host-mounted directory),
so it survives a container recreation, not just a container restart.
"""

import pickle
import time
from dataclasses import replace
from pathlib import Path

from simulation.config.world_state import DEFAULT_VALIDATION_CONFIG
from simulation.db import session_scope
from simulation.engine import initialize_world, run

NUM_DAYS = 730
PROGRESS_EVERY_N_DAYS = 10
CHECKPOINT_EVERY_N_DAYS = 10
CHECKPOINT_PATH = Path(__file__).parent / ".run_2year_checkpoint.pkl"


def main() -> None:
    config = replace(DEFAULT_VALIDATION_CONFIG, num_days=NUM_DAYS)
    checkpoint = _load_checkpoint()

    with session_scope() as session:
        t0 = time.perf_counter()

        if checkpoint is None:
            print(
                f"Starting 2-year run: seed={config.seed}, {config.num_days} days, "
                f"{config.num_warehouses} warehouses, {config.num_skus} SKUs, "
                f"{config.num_suppliers} suppliers, {config.num_customers} customers, "
                f"{config.num_carriers} carriers, start={config.start_date}",
                flush=True,
            )
            world = initialize_world(session, config)
            start_day_index = 0
            rng = None
            initial_stats = None
            t1 = time.perf_counter()
            print(f"World initialized in {t1 - t0:.1f}s", flush=True)
        else:
            world = checkpoint["world"]
            start_day_index = checkpoint["day_index"]
            rng = checkpoint["rng"]
            initial_stats = checkpoint["stats"]
            t1 = time.perf_counter()
            print(
                f"Resuming from checkpoint: day {start_day_index}/{config.num_days} "
                f"already committed ({initial_stats.orders_created} orders so far)",
                flush=True,
            )

        def _on_day_committed(day_index: int, stats_now, rng_now) -> None:
            if day_index % CHECKPOINT_EVERY_N_DAYS == 0 or day_index == config.num_days:
                _save_checkpoint(day_index, world, rng_now, stats_now)
            if day_index % PROGRESS_EVERY_N_DAYS != 0 and day_index != config.num_days:
                return
            elapsed = time.perf_counter() - t1
            days_done_this_session = day_index - start_day_index
            avg_per_day = elapsed / days_done_this_session if days_done_this_session else 0
            remaining = (config.num_days - day_index) * avg_per_day
            print(
                f"Day {day_index}/{config.num_days} committed "
                f"({elapsed:.0f}s elapsed this session, {avg_per_day:.1f}s/day avg, "
                f"~{remaining:.0f}s remaining, {stats_now.orders_created} orders so far)",
                flush=True,
            )

        stats = run(
            session,
            world,
            config,
            commit_every_n_days=1,
            on_day_committed=_on_day_committed,
            resume_from_day_index=start_day_index,
            rng=rng,
            initial_stats=initial_stats,
        )
        t2 = time.perf_counter()
        print(
            f"2-year run completed in {t2 - t1:.1f}s this session (total {t2 - t0:.1f}s)",
            flush=True,
        )

        print("--- Stats ---", flush=True)
        for field_name in stats.__dataclass_fields__:
            if field_name.startswith("_"):
                continue
            print(f"{field_name}: {getattr(stats, field_name)}", flush=True)

    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print("Run completed successfully — checkpoint file removed.", flush=True)


def _load_checkpoint() -> dict | None:
    if not CHECKPOINT_PATH.exists():
        return None
    with CHECKPOINT_PATH.open("rb") as f:
        return pickle.load(f)


def _save_checkpoint(day_index: int, world, rng, stats) -> None:
    tmp_path = CHECKPOINT_PATH.with_suffix(".pkl.tmp")
    with tmp_path.open("wb") as f:
        pickle.dump({"day_index": day_index, "world": world, "rng": rng, "stats": stats}, f)
    tmp_path.replace(CHECKPOINT_PATH)  # atomic on POSIX — never leaves a half-written checkpoint


if __name__ == "__main__":
    main()
