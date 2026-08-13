"""etl_run_table_metrics writer + structured-log emission — one
computation feeding both (never two separately-computed values that
could drift), per the pipeline-observability requirement.

Stage A scoping (documented, not hidden): inserted_count/updated_count/
unchanged_count are always 0 for tables that only went through Stage A
(no load stage). Stage B populates real values for load-processed
tables.

Per-stage timing (ADR-022): extract_seconds/transform_seconds/
load_seconds/reconcile_seconds are each nullable — a given table may not
exercise every stage in a given run. duration_seconds is the sum of
whichever stage seconds are populated (never a separately-tracked total
that could drift from its parts).
"""

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

logger = logging.getLogger("etl")


@dataclass
class TableMetrics:
    source_table: str
    extracted_count: int
    quarantined_count: int
    rejected_count: int
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    extract_seconds: float | None = None
    transform_seconds: float | None = None
    load_seconds: float | None = None
    reconcile_seconds: float | None = None

    @property
    def duration_seconds(self) -> float:
        return round(
            sum(
                s
                for s in (
                    self.extract_seconds,
                    self.transform_seconds,
                    self.load_seconds,
                    self.reconcile_seconds,
                )
                if s is not None
            ),
            3,
        )

    @property
    def rows_per_second(self) -> float | None:
        if self.duration_seconds <= 0:
            return None
        return round(self.extracted_count / self.duration_seconds, 2)


def record_and_log(conn: Connection, etl_run_id: int, metrics: TableMetrics) -> None:
    duration_seconds = metrics.duration_seconds
    rows_per_second = metrics.rows_per_second

    conn.execute(
        text(
            "INSERT INTO etl_run_table_metrics "
            "(etl_run_id, source_table, extracted_count, inserted_count, updated_count, "
            " unchanged_count, quarantined_count, rejected_count, duration_seconds, "
            " rows_per_second, extract_seconds, transform_seconds, load_seconds, "
            " reconcile_seconds) "
            "VALUES (:run_id, :t, :extracted, :inserted, :updated, :unchanged, :quarantined, "
            " :rejected, :duration, :rps, :extract_s, :transform_s, :load_s, :reconcile_s) "
            "ON DUPLICATE KEY UPDATE "
            "extracted_count = :extracted, inserted_count = :inserted, updated_count = :updated, "
            "unchanged_count = :unchanged, quarantined_count = :quarantined, "
            "rejected_count = :rejected, duration_seconds = :duration, rows_per_second = :rps, "
            "extract_seconds = :extract_s, transform_seconds = :transform_s, "
            "load_seconds = :load_s, reconcile_seconds = :reconcile_s"
        ),
        {
            "run_id": etl_run_id,
            "t": metrics.source_table,
            "extracted": metrics.extracted_count,
            "inserted": metrics.inserted_count,
            "updated": metrics.updated_count,
            "unchanged": metrics.unchanged_count,
            "quarantined": metrics.quarantined_count,
            "rejected": metrics.rejected_count,
            "duration": duration_seconds,
            "rps": rows_per_second,
            "extract_s": metrics.extract_seconds,
            "transform_s": metrics.transform_seconds,
            "load_s": metrics.load_seconds,
            "reconcile_s": metrics.reconcile_seconds,
        },
    )

    logger.info(
        "etl_table_metrics",
        extra={
            "etl_run_id": etl_run_id,
            "source_table": metrics.source_table,
            "extracted_count": metrics.extracted_count,
            "inserted_count": metrics.inserted_count,
            "updated_count": metrics.updated_count,
            "unchanged_count": metrics.unchanged_count,
            "quarantined_count": metrics.quarantined_count,
            "rejected_count": metrics.rejected_count,
            "duration_seconds": duration_seconds,
            "rows_per_second": rows_per_second,
            "extract_seconds": metrics.extract_seconds,
            "transform_seconds": metrics.transform_seconds,
            "load_seconds": metrics.load_seconds,
            "reconcile_seconds": metrics.reconcile_seconds,
        },
    )
