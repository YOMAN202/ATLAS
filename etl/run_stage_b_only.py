"""One-off runner: Stage B only, against already-staged Stage A data
(etl_extract_staging is already fully populated from the accepted Stage A
run — no need to re-extract). Not part of the pipeline's public API;
used to produce the real Stage B completion-report numbers without
re-paying Stage A's already-measured/accepted cost.
"""

import time

from etl.audit.logging_config import configure_logging
from etl.audit.run_log import complete_run, start_run
from etl.db import olap_engine, oltp_engine
from etl.pipeline import _STAGE_B_DIMENSIONS, _STAGE_B_FACTS, _STAGE_B_SUMMARY

logger = configure_logging()


def main() -> None:
    oltp_eng = oltp_engine()
    olap_eng = olap_engine()

    with olap_eng.connect() as run_conn:
        with run_conn.begin():
            etl_run_id = start_run(run_conn, stage="STAGE_B_ONLY")
    print(f"etl_run_id={etl_run_id}", flush=True)

    status = "FAILED"
    run_t0 = time.perf_counter()
    try:
        with oltp_eng.connect() as oltp_conn:
            for processor in _STAGE_B_DIMENSIONS + _STAGE_B_FACTS + _STAGE_B_SUMMARY:
                t0 = time.perf_counter()
                with olap_eng.connect() as olap_conn:
                    with olap_conn.begin():
                        processor(oltp_conn, olap_conn, etl_run_id)
                print(f"{processor.__name__}: {round(time.perf_counter() - t0, 1)}s", flush=True)
        status = "SUCCEEDED"
    finally:
        duration = round(time.perf_counter() - run_t0, 3)
        with olap_eng.connect() as run_conn:
            with run_conn.begin():
                complete_run(run_conn, etl_run_id, status, duration)
        print(f"status={status} total={duration}s", flush=True)


if __name__ == "__main__":
    main()
