"""Stage A pipeline entrypoint: Extract -> Validate -> Quarantine ->
Watermark advance -> Audit, once per source table in etl.extract.registry.

Transform, SCD2, fact transforms, Load, reconciliation, and scoring
(Stage B) are explicitly not implemented here — see the Phase 5 plan's
Stage A/Stage B split. This module's `run(fault_injector=...)` is the
single entrypoint both real runs and the failure-recovery test suite use
— fault injection tests exercise this exact code path, not a mock of it.

Transaction boundaries (ADR-018): one transaction per table. A fault
partway through a table's processing rolls that table's transaction back
entirely (nothing staged, nothing quarantined, watermark unchanged for
that table) — simple, correct, and safe to rerun, because every write is
upsert-idempotent and the watermark for that table never moved.
"""

import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from datetime import time as dtime

from sqlalchemy.engine import Connection

from etl.audit.logging_config import configure_logging
from etl.audit.metrics import TableMetrics, record_and_log
from etl.audit.run_log import complete_run, start_run
from etl.db import olap_engine, oltp_engine
from etl.extract.extract import extract_batch
from etl.extract.registry import REGISTRY, TableSpec
from etl.extract.staging import stage_row
from etl.extract.watermark import advance_if_later, get_watermark
from etl.validate.fk_lookup import fetch_valid_ids
from etl.validate.quarantine import quarantine_row
from etl.validate.validate import validate_batch

logger = configure_logging()

FaultInjector = Callable[
    [str, int], None
]  # (source_table, row_index) -> None; raises to inject a fault


def _to_datetime(value: date | datetime) -> datetime:
    return value if isinstance(value, datetime) else datetime.combine(value, dtime.min)


def _process_table(
    oltp_conn: Connection,
    olap_conn: Connection,
    etl_run_id: int,
    spec: TableSpec,
    fault_injector: FaultInjector | None,
) -> None:
    t0 = time.perf_counter()

    since = get_watermark(olap_conn, spec.name)
    rows = extract_batch(oltp_conn, spec, since)

    if not rows:
        record_and_log(
            olap_conn,
            etl_run_id,
            TableMetrics(
                source_table=spec.name,
                extracted_count=0,
                quarantined_count=0,
                rejected_count=0,
                duration_seconds=round(time.perf_counter() - t0, 3),
            ),
        )
        return

    valid_ids_by_table = fetch_valid_ids(oltp_conn, spec)
    accepted, quarantined = validate_batch(rows, spec, valid_ids_by_table)

    now = datetime.now(UTC)
    max_watermark: datetime | None = None
    row_index = 0

    for row in accepted:
        if fault_injector:
            fault_injector(spec.name, row_index)
        row_index += 1
        stage_row(
            olap_conn,
            etl_run_id,
            spec.name,
            row[spec.pk_column],
            row,
            _to_datetime(row[spec.watermark_column]),
        )
        row_watermark = _to_datetime(row[spec.watermark_column])
        if max_watermark is None or row_watermark > max_watermark:
            max_watermark = row_watermark

    for row, violations in quarantined:
        for rule, detail in violations:
            if fault_injector:
                fault_injector(spec.name, row_index)
            row_index += 1
            quarantine_row(
                olap_conn,
                etl_run_id,
                spec.name,
                row.get(spec.pk_column),
                rule,
                detail,
                row,
                now,
            )
        row_watermark = _to_datetime(row[spec.watermark_column])
        if max_watermark is None or row_watermark > max_watermark:
            max_watermark = row_watermark

    if max_watermark is not None:
        advance_if_later(olap_conn, spec.name, max_watermark)

    duration = round(time.perf_counter() - t0, 3)
    record_and_log(
        olap_conn,
        etl_run_id,
        TableMetrics(
            source_table=spec.name,
            extracted_count=len(rows),
            quarantined_count=len(quarantined),
            rejected_count=0,
            duration_seconds=duration,
        ),
    )
    logger.info(
        "stage_a_table_complete",
        extra={
            "etl_run_id": etl_run_id,
            "source_table": spec.name,
            "extracted": len(rows),
            "accepted": len(accepted),
            "quarantined": len(quarantined),
        },
    )


def run(fault_injector: FaultInjector | None = None) -> int:
    """Runs Stage A for every table in REGISTRY, in order. Returns the
    etl_run_id. Raises on the first table-level failure (including an
    injected fault) — the caller decides whether/when to rerun.
    """

    run_t0 = time.perf_counter()
    oltp_eng = oltp_engine()
    olap_eng = olap_engine()

    with olap_eng.connect() as run_conn:
        with run_conn.begin():
            etl_run_id = start_run(run_conn, stage="STAGE_A")

    logger.info("stage_a_run_started", extra={"etl_run_id": etl_run_id})

    status = "FAILED"
    try:
        with oltp_eng.connect() as oltp_conn:
            for spec in REGISTRY:
                with olap_eng.connect() as olap_conn:
                    with olap_conn.begin():
                        _process_table(oltp_conn, olap_conn, etl_run_id, spec, fault_injector)
        status = "SUCCEEDED"
    finally:
        # Runs on both the success and exception paths. On exception, this
        # records FAILED + duration and then the original exception keeps
        # propagating to the caller unchanged — callers (including the
        # failure-recovery tests) see the real fault, not a wrapped one.
        duration = round(time.perf_counter() - run_t0, 3)
        with olap_eng.connect() as run_conn:
            with run_conn.begin():
                complete_run(run_conn, etl_run_id, status, duration)
        logger.info(
            "stage_a_run_complete",
            extra={"etl_run_id": etl_run_id, "status": status, "duration_seconds": duration},
        )

    return etl_run_id


if __name__ == "__main__":
    run()
