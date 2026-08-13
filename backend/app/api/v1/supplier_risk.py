"""Planning dashboard — supplier risk scoring (Phase 7 Module C).
Read-only, via the dashboard API's existing atlas_reporting connection
(schema-wide SELECT already covers the new ds_supplier_risk_score
table — no new grant needed). Scores themselves are written exclusively
by the batch process (backend/app/decision_support/run_module_c.py, via
the separate atlas_decision_support role).

Role: supply_planner, administrator — same actor as Module A's
forecasting dashboard (SRS §3's Supply Planner "reviews reorder/risk
recommendations").
"""

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.api.schemas import PageEnvelope
from app.core.security import ADMINISTRATOR, SUPPLY_PLANNER, require_role

router = APIRouter(prefix="/api/v1/dashboards/planning/supplier-risk", tags=["planning"])


class ClassificationBreakdown(BaseModel):
    low: int
    medium: int
    high: int


class SupplierRiskSummary(BaseModel):
    etl_run_id: int
    model_id: int | None
    model_name: str | None
    scoring_weights: dict | None
    generated_at: str | None
    n_suppliers: int
    avg_risk_score: float | None
    classification_breakdown: ClassificationBreakdown


class SupplierRiskRow(BaseModel):
    supplier_key: int
    risk_score: float
    risk_classification: str
    on_time_rate: float
    quality_rejection_rate: float
    fill_rate: float
    lead_time_stddev_days: float
    on_time_rate_trend_delta: float
    trend_direction: str
    total_spend: float
    share_of_total_spend: float
    distinct_products_supplied: int
    distinct_warehouses_served: int
    n_deliveries: int
    triggering_metrics: list[str]


@router.get("/summary", response_model=SupplierRiskSummary)
def get_supplier_risk_summary(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> SupplierRiskSummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("supplier_risk_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    model_row = conn.execute(
        text(
            "SELECT id, model_name, parameters FROM ds_model_registry "
            "WHERE module = 'supplier_risk_scoring' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()

    totals = conn.execute(
        text(
            "SELECT COUNT(*) AS n, AVG(risk_score) AS avg_score, "
            "MAX(generated_at) AS generated_at, "
            "SUM(risk_classification = 'Low') AS n_low, "
            "SUM(risk_classification = 'Medium') AS n_medium, "
            "SUM(risk_classification = 'High') AS n_high "
            "FROM ds_supplier_risk_score"
        )
    ).one()

    result = SupplierRiskSummary(
        etl_run_id=etl_run_id,
        model_id=model_row.id if model_row else None,
        model_name=model_row.model_name if model_row else None,
        scoring_weights=json.loads(model_row.parameters)["weights"] if model_row else None,
        generated_at=str(totals.generated_at) if totals.generated_at else None,
        n_suppliers=int(totals.n),
        avg_risk_score=float(totals.avg_score) if totals.avg_score is not None else None,
        classification_breakdown=ClassificationBreakdown(
            low=int(totals.n_low or 0),
            medium=int(totals.n_medium or 0),
            high=int(totals.n_high or 0),
        ),
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[SupplierRiskRow])
def get_supplier_risk_detail(
    risk_classification: str | None = Query(None, pattern="^(Low|Medium|High)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> PageEnvelope[SupplierRiskRow]:
    filter_clause = "(:classification IS NULL OR risk_classification = :classification)"
    params = {"classification": risk_classification}

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM ds_supplier_risk_score WHERE {filter_clause}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT supplier_key, risk_score, risk_classification, on_time_rate, "
            "quality_rejection_rate, fill_rate, lead_time_stddev_days, on_time_rate_trend_delta, "
            "trend_direction, total_spend, share_of_total_spend, distinct_products_supplied, "
            "distinct_warehouses_served, n_deliveries, triggering_metrics "
            f"FROM ds_supplier_risk_score WHERE {filter_clause} "
            "ORDER BY risk_score DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            SupplierRiskRow(
                supplier_key=r.supplier_key,
                risk_score=float(r.risk_score),
                risk_classification=r.risk_classification,
                on_time_rate=float(r.on_time_rate),
                quality_rejection_rate=float(r.quality_rejection_rate),
                fill_rate=float(r.fill_rate),
                lead_time_stddev_days=float(r.lead_time_stddev_days),
                on_time_rate_trend_delta=float(r.on_time_rate_trend_delta),
                trend_direction=r.trend_direction,
                total_spend=float(r.total_spend),
                share_of_total_spend=float(r.share_of_total_spend),
                distinct_products_supplied=r.distinct_products_supplied,
                distinct_warehouses_served=r.distinct_warehouses_served,
                n_deliveries=r.n_deliveries,
                triggering_metrics=json.loads(r.triggering_metrics),
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
