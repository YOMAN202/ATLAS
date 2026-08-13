"""Data Quality dashboard (SRS FR-7.5). Source: etl_run_log,
etl_run_table_metrics, dq_quarantine — all already fully built and
validated by Stage A/B (docs/phase5-validation.md §7), nothing new
computed here beyond aggregation.

Run duration is computed by summing etl_run_table_metrics rather than
trusting etl_run_log.duration_seconds directly — docs/phase5-validation.md
§8 documents that column as unreliable for runs finalized via the
one-off run_one_fact.py helper (a real, disclosed bookkeeping gap, not
silently worked around here).

Role: operations_analyst, administrator (SRS §14: "As an Operations
Analyst, I want to see the data quality score of each warehouse load,
so I can trust ... the numbers on my dashboards").
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.api.schemas import PageEnvelope
from app.core.security import ADMINISTRATOR, OPERATIONS_ANALYST, require_role

router = APIRouter(prefix="/api/v1/dashboards/data-quality", tags=["data-quality"])


class TableQualityRow(BaseModel):
    source_table: str
    extracted_count: int
    quarantined_count: int
    rejected_count: int
    dq_score: float | None


class RunTrendPoint(BaseModel):
    etl_run_id: int
    started_at: datetime
    stage: str
    overall_dq_score: float | None
    total_extracted: int
    total_quarantined: int


class DataQualitySummary(BaseModel):
    etl_run_id: int
    overall_dq_score: float | None
    quarantine_rate: float | None
    referential_integrity_failure_rate: float | None
    duration_seconds: float
    per_table: list[TableQualityRow]
    run_trend: list[RunTrendPoint]


class QuarantineRow(BaseModel):
    id: int
    etl_run_id: int
    source_table: str
    source_id: int | None
    rule_violated: str
    rule_detail: str
    quarantined_at: datetime


@router.get("", response_model=DataQualitySummary)
def get_data_quality_summary(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, ADMINISTRATOR)),
) -> DataQualitySummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("data_quality_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    per_table_rows = conn.execute(
        text(
            "SELECT source_table, extracted_count, quarantined_count, rejected_count "
            "FROM etl_run_table_metrics WHERE etl_run_id = :run_id ORDER BY source_table"
        ),
        {"run_id": etl_run_id},
    ).all()

    per_table = [
        TableQualityRow(
            source_table=r.source_table,
            extracted_count=r.extracted_count,
            quarantined_count=r.quarantined_count,
            rejected_count=r.rejected_count,
            dq_score=(
                (r.extracted_count - r.quarantined_count - r.rejected_count) / r.extracted_count
                if r.extracted_count
                else None
            ),
        )
        for r in per_table_rows
    ]

    total_extracted = sum(r.extracted_count for r in per_table)
    total_quarantined = sum(r.quarantined_count for r in per_table)
    total_rejected = sum(r.rejected_count for r in per_table)
    overall_dq_score = (
        (total_extracted - total_quarantined - total_rejected) / total_extracted
        if total_extracted
        else None
    )
    quarantine_rate = total_quarantined / total_extracted if total_extracted else None

    dq3_count = conn.execute(
        text(
            "SELECT COUNT(*) FROM dq_quarantine "
            "WHERE etl_run_id = :run_id AND rule_violated = 'DQ-3'"
        ),
        {"run_id": etl_run_id},
    ).scalar_one()
    ref_integrity_failure_rate = dq3_count / total_extracted if total_extracted else None

    duration = conn.execute(
        text(
            "SELECT COALESCE(SUM(duration_seconds), 0) FROM etl_run_table_metrics "
            "WHERE etl_run_id = :run_id"
        ),
        {"run_id": etl_run_id},
    ).scalar_one()

    trend_rows = conn.execute(
        text(
            "SELECT l.id AS etl_run_id, l.started_at, l.stage, "
            "COALESCE(SUM(m.extracted_count), 0) AS extracted, "
            "COALESCE(SUM(m.quarantined_count), 0) AS quarantined, "
            "COALESCE(SUM(m.rejected_count), 0) AS rejected "
            "FROM etl_run_log l "
            "LEFT JOIN etl_run_table_metrics m ON m.etl_run_id = l.id "
            "WHERE l.status = 'SUCCEEDED' "
            "GROUP BY l.id, l.started_at, l.stage ORDER BY l.id"
        )
    ).all()

    result = DataQualitySummary(
        etl_run_id=etl_run_id,
        overall_dq_score=overall_dq_score,
        quarantine_rate=quarantine_rate,
        referential_integrity_failure_rate=ref_integrity_failure_rate,
        duration_seconds=float(duration),
        per_table=per_table,
        run_trend=[
            RunTrendPoint(
                etl_run_id=r.etl_run_id,
                started_at=r.started_at,
                stage=r.stage,
                overall_dq_score=(
                    (r.extracted - r.quarantined - r.rejected) / r.extracted
                    if r.extracted
                    else None
                ),
                total_extracted=int(r.extracted),
                total_quarantined=int(r.quarantined),
            )
            for r in trend_rows
        ],
    )
    set_cached(key, result)
    return result


@router.get("/quarantine", response_model=PageEnvelope[QuarantineRow])
def get_quarantine_detail(
    etl_run_id: int | None = Query(None),
    source_table: str | None = Query(None),
    rule_violated: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, ADMINISTRATOR)),
) -> PageEnvelope[QuarantineRow]:
    filter_clause = (
        "(:etl_run_id IS NULL OR etl_run_id = :etl_run_id) "
        "AND (:source_table IS NULL OR source_table = :source_table) "
        "AND (:rule_violated IS NULL OR rule_violated = :rule_violated)"
    )
    params = {
        "etl_run_id": etl_run_id,
        "source_table": source_table,
        "rule_violated": rule_violated,
    }

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM dq_quarantine WHERE {filter_clause}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT id, etl_run_id, source_table, source_id, rule_violated, "
            "rule_detail, quarantined_at "
            f"FROM dq_quarantine WHERE {filter_clause} "
            "ORDER BY id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            QuarantineRow(
                id=r.id,
                etl_run_id=r.etl_run_id,
                source_table=r.source_table,
                source_id=r.source_id,
                rule_violated=r.rule_violated,
                rule_detail=r.rule_detail,
                quarantined_at=r.quarantined_at,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
