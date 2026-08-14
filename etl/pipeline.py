"""Pipeline entrypoint: Stage A (Extract -> Validate -> Quarantine ->
Watermark advance -> Audit, once per source table) followed by Stage B
(Transform -> Load -> Reconcile, once per warehouse object — 7
dimensions, 6 facts, 1 summary table). This module's
`run(fault_injector=...)` is the single entrypoint both real runs and
the failure-recovery test suite use — fault injection tests exercise
this exact code path, not a mock of it. `fault_injector` only applies to
Stage A (its documented, tested purpose); Stage B has no injection hook.

Transaction boundaries (ADR-018): one transaction per table/object. A
fault partway through rolls that unit's transaction back entirely —
simple, correct, and safe to rerun, because every write is
upsert-idempotent and nothing durable (watermark or warehouse row)
moved for the unit that failed.
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
from etl.stage_b import (
    process_dim_carrier,
    process_dim_customer,
    process_dim_product,
    process_dim_region,
    process_dim_supplier,
    process_dim_warehouse,
    process_fact_inventory_snapshot,
    process_fact_orders,
    process_fact_procurement,
    process_fact_returns,
    process_fact_shipments,
    process_fact_supplier_delivery,
    process_summary_daily_revenue_by_region,
)
from etl.validate.fk_lookup import fetch_valid_ids
from etl.validate.quarantine import quarantine_row
from etl.validate.validate import validate_batch

# Dimensions before facts (ADR-019); within each group, order doesn't
# affect correctness but keeps logs/audits readable and deterministic.
_STAGE_B_DIMENSIONS = (
    process_dim_region,
    process_dim_product,
    process_dim_carrier,
    process_dim_customer,
    process_dim_supplier,
    process_dim_warehouse,
)
_STAGE_B_FACTS = (
    process_fact_orders,
    process_fact_procurement,
    process_fact_supplier_delivery,
    process_fact_shipments,
    process_fact_returns,
    process_fact_inventory_snapshot,
)
_STAGE_B_SUMMARY = (process_summary_daily_revenue_by_region,)

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
                extract_seconds=round(time.perf_counter() - t0, 3),
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
            extract_seconds=duration,
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


def _run_stage_a_tables(
    oltp_eng, olap_eng, etl_run_id: int, fault_injector: FaultInjector | None
) -> None:
    with oltp_eng.connect() as oltp_conn:
        for spec in REGISTRY:
            with olap_eng.connect() as olap_conn:
                with olap_conn.begin():
                    _process_table(oltp_conn, olap_conn, etl_run_id, spec, fault_injector)


def _run_stage_b_objects(oltp_eng, olap_eng, etl_run_id: int) -> None:
    with oltp_eng.connect() as oltp_conn:
        for processor in _STAGE_B_DIMENSIONS + _STAGE_B_FACTS + _STAGE_B_SUMMARY:
            with olap_eng.connect() as olap_conn:
                with olap_conn.begin():
                    processor(oltp_conn, olap_conn, etl_run_id)


def run(fault_injector: FaultInjector | None = None) -> int:
    """Stage A only — extract every table in REGISTRY, in order. Returns
    the etl_run_id. Raises on the first table-level failure (including an
    injected fault) — the caller decides whether/when to rerun. Kept as
    its own entrypoint (not folded into run_full_pipeline) so Stage A's
    existing, already-approved test suite keeps testing exactly what it
    always has.
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
        _run_stage_a_tables(oltp_eng, olap_eng, etl_run_id, fault_injector)
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


def run_full_pipeline(fault_injector: FaultInjector | None = None) -> int:
    """Stage A followed by Stage B, sharing one etl_run_id and one
    etl_run_log row — the real, steady-state production entrypoint once
    Stage B exists. `fault_injector` only applies to Stage A (its
    documented, tested purpose); a Stage A failure aborts before Stage B
    starts (dimensions/facts must never transform from a run Stage A
    didn't actually complete).
    """

    run_t0 = time.perf_counter()
    oltp_eng = oltp_engine()
    olap_eng = olap_engine()

    with olap_eng.connect() as run_conn:
        with run_conn.begin():
            etl_run_id = start_run(run_conn, stage="STAGE_A_B")

    logger.info("pipeline_run_started", extra={"etl_run_id": etl_run_id})

    status = "FAILED"
    try:
        stage_a_t0 = time.perf_counter()
        _run_stage_a_tables(oltp_eng, olap_eng, etl_run_id, fault_injector)
        logger.info(
            "stage_a_complete",
            extra={
                "etl_run_id": etl_run_id,
                "duration_seconds": round(time.perf_counter() - stage_a_t0, 3),
            },
        )

        stage_b_t0 = time.perf_counter()
        _run_stage_b_objects(oltp_eng, olap_eng, etl_run_id)
        logger.info(
            "stage_b_complete",
            extra={
                "etl_run_id": etl_run_id,
                "duration_seconds": round(time.perf_counter() - stage_b_t0, 3),
            },
        )
        status = "SUCCEEDED"
    finally:
        duration = round(time.perf_counter() - run_t0, 3)
        with olap_eng.connect() as run_conn:
            with run_conn.begin():
                complete_run(run_conn, etl_run_id, status, duration)
        logger.info(
            "pipeline_run_complete",
            extra={"etl_run_id": etl_run_id, "status": status, "duration_seconds": duration},
        )

    return etl_run_id


if __name__ == "__main__":
    run_full_pipeline()
