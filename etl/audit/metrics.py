"""etl_run_table_metrics writer + structured-log emission — one
computation feeding both (never two separately-computed values that
could drift), per the pipeline-observability requirement.

Stage A scoping (documented, not hidden): inserted_count/updated_count/
unchanged_count are always 0 here — nothing is loaded yet. They exist in
the schema now so it doesn't change when Stage B's load stage adds real
values for them.
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
    duration_seconds: float
    inserted_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0

    @property
    def rows_per_second(self) -> float | None:
        if self.duration_seconds <= 0:
            return None
        return round(self.extracted_count / self.duration_seconds, 2)


def record_and_log(conn: Connection, etl_run_id: int, metrics: TableMetrics) -> None:
    rows_per_second = metrics.rows_per_second

    conn.execute(
        text(
            "INSERT INTO etl_run_table_metrics "
            "(etl_run_id, source_table, extracted_count, inserted_count, updated_count, "
            " unchanged_count, quarantined_count, rejected_count, duration_seconds, "
            " rows_per_second) "
            "VALUES (:run_id, :t, :extracted, :inserted, :updated, :unchanged, :quarantined, "
            " :rejected, :duration, :rps) "
            "ON DUPLICATE KEY UPDATE "
            "extracted_count = :extracted, inserted_count = :inserted, updated_count = :updated, "
            "unchanged_count = :unchanged, quarantined_count = :quarantined, "
            "rejected_count = :rejected, duration_seconds = :duration, rows_per_second = :rps"
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
            "duration": metrics.duration_seconds,
            "rps": rows_per_second,
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
            "duration_seconds": metrics.duration_seconds,
            "rows_per_second": rows_per_second,
        },
    )
