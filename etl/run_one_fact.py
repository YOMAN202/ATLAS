"""One-off runner: process a single named Stage B object, sharing/reusing
an existing etl_run_id if given, else starting a new run. Used to process
large facts individually (detached, logged to a file) so progress
survives a single exec-session interruption — each object is already its
own atomic transaction, so this is a safe, resumable way to build up a
full Stage B run's results across multiple invocations sharing one run_id.
"""

import sys
import time

from etl.audit.logging_config import configure_logging
from etl.audit.run_log import start_run
from etl.db import olap_engine, oltp_engine
from etl.pipeline import _STAGE_B_DIMENSIONS, _STAGE_B_FACTS, _STAGE_B_SUMMARY

logger = configure_logging()

_ALL = {p.__name__: p for p in _STAGE_B_DIMENSIONS + _STAGE_B_FACTS + _STAGE_B_SUMMARY}


def main() -> None:
    name = sys.argv[1]
    run_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    processor = _ALL[name]

    oltp_eng = oltp_engine()
    olap_eng = olap_engine()

    if run_id is None:
        with olap_eng.connect() as c:
            with c.begin():
                run_id = start_run(c, stage="STAGE_B_ONLY")
        print(f"run_id={run_id}", flush=True)

    t0 = time.perf_counter()
    status = "FAILED"
    try:
        with oltp_eng.connect() as oltp_conn:
            with olap_eng.connect() as olap_conn:
                with olap_conn.begin():
                    processor(oltp_conn, olap_conn, run_id)
        status = "SUCCEEDED"
    finally:
        duration = round(time.perf_counter() - t0, 1)
        print(f"{name}: {status} {duration}s (run_id={run_id})", flush=True)


if __name__ == "__main__":
    main()
