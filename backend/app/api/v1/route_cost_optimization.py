"""Planning dashboard — route and cost optimization (Phase 7.2 Module
F). Read-only, via the dashboard API's existing atlas_reporting
connection (its schema-wide SELECT on atlas_olap already covers the
new ds_* tables — no new grant needed). Recommendations are written
exclusively by the batch process
(backend/app/decision_support/run_module_f.py, via the separate
atlas_decision_support role).

Role: supply_planner, administrator — same actor as Modules A/C/D/B/E's
dashboards.
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

router = APIRouter(prefix="/api/v1/dashboards/planning/route-cost-optimization", tags=["planning"])


class OptimizationSummary(BaseModel):
    etl_run_id: int
    model_id: int | None
    model_name: str | None
    generated_at: str | None
    analysis_window_start: str | None
    analysis_window_end: str | None
    n_right_sizing_recommendations: int
    n_consolidation_recommendations: int
    total_estimated_savings: float
    right_sizing_estimated_savings: float
    consolidation_estimated_savings: float


class WarehouseImpactRow(BaseModel):
    origin_warehouse_key: int
    n_right_sizing_recommendations: int
    n_consolidation_recommendations: int
    total_estimated_savings: float


class OptimizationRecommendationRow(BaseModel):
    id: int
    recommendation_type: str
    origin_warehouse_key: int
    shipment_date: str
    shipment_numbers: list[str]
    total_quantity: int
    distance_miles: float
    current_vehicle_type_code: str
    current_total_cost: float
    recommended_vehicle_type_code: str
    recommended_total_cost: float
    estimated_savings: float
    confidence: str
    contributing_factors: dict
    business_rationale: str


@router.get("/summary", response_model=OptimizationSummary)
def get_optimization_summary(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> OptimizationSummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("route_cost_optimization_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    model_row = conn.execute(
        text(
            "SELECT id, model_name, parameters FROM ds_model_registry "
            "WHERE module = 'route_cost_optimization' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()

    totals = conn.execute(
        text(
            "SELECT COUNT(*) AS n, MAX(generated_at) AS generated_at, "
            "SUM(recommendation_type = 'right_sizing') AS n_right_sizing, "
            "SUM(recommendation_type = 'consolidation') AS n_consolidation, "
            "SUM(estimated_savings) AS total_savings, "
            "SUM(CASE WHEN recommendation_type = 'right_sizing' THEN estimated_savings "
            "ELSE 0 END) AS right_sizing_savings, "
            "SUM(CASE WHEN recommendation_type = 'consolidation' THEN estimated_savings "
            "ELSE 0 END) AS consolidation_savings "
            "FROM ds_optimization_recommendation"
        )
    ).one()

    params = json.loads(model_row.parameters) if model_row else {}
    result = OptimizationSummary(
        etl_run_id=etl_run_id,
        model_id=model_row.id if model_row else None,
        model_name=model_row.model_name if model_row else None,
        generated_at=str(totals.generated_at) if totals.generated_at else None,
        analysis_window_start=params.get("analysis_window_start"),
        analysis_window_end=params.get("analysis_window_end"),
        n_right_sizing_recommendations=int(totals.n_right_sizing or 0),
        n_consolidation_recommendations=int(totals.n_consolidation or 0),
        total_estimated_savings=float(totals.total_savings or 0.0),
        right_sizing_estimated_savings=float(totals.right_sizing_savings or 0.0),
        consolidation_estimated_savings=float(totals.consolidation_savings or 0.0),
    )
    set_cached(key, result)
    return result


@router.get("/warehouse-impact", response_model=list[WarehouseImpactRow])
def get_warehouse_impact(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[WarehouseImpactRow]:
    """The "Transportation Impact" deliverable's per-warehouse rollup —
    given the confirmed single-warehouse-per-product model, genuine
    cross-warehouse product reallocation isn't actionable, so this is a
    per-warehouse rollup of right-sizing/consolidation opportunity."""
    rows = conn.execute(
        text(
            "SELECT origin_warehouse_key, "
            "SUM(recommendation_type = 'right_sizing') AS n_right_sizing, "
            "SUM(recommendation_type = 'consolidation') AS n_consolidation, "
            "SUM(estimated_savings) AS total_savings "
            "FROM ds_optimization_recommendation GROUP BY origin_warehouse_key "
            "ORDER BY total_savings DESC"
        )
    ).all()
    return [
        WarehouseImpactRow(
            origin_warehouse_key=r.origin_warehouse_key,
            n_right_sizing_recommendations=int(r.n_right_sizing or 0),
            n_consolidation_recommendations=int(r.n_consolidation or 0),
            total_estimated_savings=float(r.total_savings or 0.0),
        )
        for r in rows
    ]


_DETAIL_FILTER = (
    "(:recommendation_type IS NULL OR recommendation_type = :recommendation_type) "
    "AND (:origin_warehouse_key IS NULL OR origin_warehouse_key = :origin_warehouse_key)"
)


@router.get("/detail", response_model=PageEnvelope[OptimizationRecommendationRow])
def get_optimization_detail(
    recommendation_type: str | None = Query(None, pattern="^(right_sizing|consolidation)$"),
    origin_warehouse_key: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> PageEnvelope[OptimizationRecommendationRow]:
    params = {
        "recommendation_type": recommendation_type,
        "origin_warehouse_key": origin_warehouse_key,
    }

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM ds_optimization_recommendation WHERE {_DETAIL_FILTER}"),
        params,
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT id, recommendation_type, origin_warehouse_key, shipment_date, "
            "shipment_numbers, total_quantity, distance_miles, current_vehicle_type_code, "
            "current_total_cost, recommended_vehicle_type_code, recommended_total_cost, "
            "estimated_savings, confidence, contributing_factors, business_rationale "
            f"FROM ds_optimization_recommendation WHERE {_DETAIL_FILTER} "
            "ORDER BY estimated_savings DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            OptimizationRecommendationRow(
                id=r.id,
                recommendation_type=r.recommendation_type,
                origin_warehouse_key=r.origin_warehouse_key,
                shipment_date=str(r.shipment_date),
                shipment_numbers=json.loads(r.shipment_numbers),
                total_quantity=r.total_quantity,
                distance_miles=float(r.distance_miles),
                current_vehicle_type_code=r.current_vehicle_type_code,
                current_total_cost=float(r.current_total_cost),
                recommended_vehicle_type_code=r.recommended_vehicle_type_code,
                recommended_total_cost=float(r.recommended_total_cost),
                estimated_savings=float(r.estimated_savings),
                confidence=r.confidence,
                contributing_factors=json.loads(r.contributing_factors),
                business_rationale=r.business_rationale,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
