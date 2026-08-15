"""Planning dashboard — inventory policy recommendation (Phase 7
Module B). Read-only, via the dashboard API's existing atlas_reporting
connection (its schema-wide SELECT on atlas_olap already covers the
new ds_* tables — no new grant needed). Recommendations and sensitivity
results are written exclusively by the batch process
(backend/app/decision_support/run_module_b.py, via the separate
atlas_decision_support role).

Role: supply_planner, administrator — same actor as Modules A/C/D's
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
from app.core.security import ADMINISTRATOR, EXECUTIVE, SUPPLY_PLANNER, require_role

router = APIRouter(prefix="/api/v1/dashboards/planning/inventory-policy", tags=["planning"])


class BalancingBreakdown(BaseModel):
    reorder_now: int
    adequate: int
    excess_inventory: int


class InventoryPolicySummary(BaseModel):
    etl_run_id: int
    model_id: int | None
    model_name: str | None
    source_forecast_model_id: int | None
    source_supplier_model_id: int | None
    source_service_level_model_id: int | None
    generated_at: str | None
    n_recommendations: int
    avg_safety_stock: float | None
    avg_reorder_point: float | None
    balancing_breakdown: BalancingBreakdown


class SensitivityScenario(BaseModel):
    target_service_level: float
    avg_safety_stock: float
    avg_reorder_point: float
    total_inventory_investment: float
    achieved_service_level: float
    n_pairs: int


class InventoryPolicyRow(BaseModel):
    product_key: int
    warehouse_key: int
    safety_stock: float
    reorder_point: float
    service_level_inventory_target: float
    current_available_quantity: float
    balancing_recommendation: str
    confidence: str
    contributing_factors: dict
    business_rationale: str
    primary_supplier_key: int | None


@router.get("/summary", response_model=InventoryPolicySummary)
def get_inventory_policy_summary(
    conn: Connection = Depends(get_olap_connection),
    # EXECUTIVE added (v2 redesign) -- see forecast.py's identical note.
    _role: str = Depends(require_role(EXECUTIVE, SUPPLY_PLANNER, ADMINISTRATOR)),
) -> InventoryPolicySummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("inventory_policy_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    model_row = conn.execute(
        text(
            "SELECT id, model_name FROM ds_model_registry "
            "WHERE module = 'inventory_policy' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()

    totals = conn.execute(
        text(
            "SELECT COUNT(*) AS n, AVG(safety_stock) AS avg_ss, AVG(reorder_point) AS avg_rop, "
            "MAX(generated_at) AS generated_at, "
            "MAX(source_forecast_model_id) AS source_forecast_model_id, "
            "MAX(source_supplier_model_id) AS source_supplier_model_id, "
            "MAX(source_service_level_model_id) AS source_service_level_model_id, "
            "SUM(balancing_recommendation = 'reorder_now') AS n_reorder_now, "
            "SUM(balancing_recommendation = 'adequate') AS n_adequate, "
            "SUM(balancing_recommendation = 'excess_inventory') AS n_excess "
            "FROM ds_inventory_policy"
        )
    ).one()

    result = InventoryPolicySummary(
        etl_run_id=etl_run_id,
        model_id=model_row.id if model_row else None,
        model_name=model_row.model_name if model_row else None,
        source_forecast_model_id=totals.source_forecast_model_id,
        source_supplier_model_id=totals.source_supplier_model_id,
        source_service_level_model_id=totals.source_service_level_model_id,
        generated_at=str(totals.generated_at) if totals.generated_at else None,
        n_recommendations=int(totals.n),
        avg_safety_stock=float(totals.avg_ss) if totals.avg_ss is not None else None,
        avg_reorder_point=float(totals.avg_rop) if totals.avg_rop is not None else None,
        balancing_breakdown=BalancingBreakdown(
            reorder_now=int(totals.n_reorder_now or 0),
            adequate=int(totals.n_adequate or 0),
            excess_inventory=int(totals.n_excess or 0),
        ),
    )
    set_cached(key, result)
    return result


@router.get("/sensitivity", response_model=list[SensitivityScenario])
def get_inventory_policy_sensitivity(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[SensitivityScenario]:
    """The "policy sensitivity analysis" deliverable: how safety stock,
    reorder point, inventory investment, and achieved service level
    move as the target service level varies — from a real walk-forward
    simulation at each level, not an interpolation."""
    model_row = conn.execute(
        text(
            "SELECT id FROM ds_model_registry "
            "WHERE module = 'inventory_policy' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()
    if model_row is None:
        return []

    rows = conn.execute(
        text(
            "SELECT target_service_level, avg_safety_stock, avg_reorder_point, "
            "total_inventory_investment, achieved_service_level, n_pairs "
            "FROM ds_policy_sensitivity WHERE model_id = :model_id ORDER BY target_service_level"
        ),
        {"model_id": model_row.id},
    ).all()
    return [
        SensitivityScenario(
            target_service_level=float(r.target_service_level),
            avg_safety_stock=float(r.avg_safety_stock),
            avg_reorder_point=float(r.avg_reorder_point),
            total_inventory_investment=float(r.total_inventory_investment),
            achieved_service_level=float(r.achieved_service_level),
            n_pairs=r.n_pairs,
        )
        for r in rows
    ]


_DETAIL_FILTER = (
    "(:balancing IS NULL OR balancing_recommendation = :balancing) "
    "AND (:product_key IS NULL OR product_key = :product_key) "
    "AND (:warehouse_key IS NULL OR warehouse_key = :warehouse_key)"
)


@router.get("/detail", response_model=PageEnvelope[InventoryPolicyRow])
def get_inventory_policy_detail(
    balancing_recommendation: str | None = Query(
        None, pattern="^(reorder_now|adequate|excess_inventory)$"
    ),
    product_key: int | None = Query(
        None, description="Look up a single (product, warehouse) pair directly."
    ),
    warehouse_key: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> PageEnvelope[InventoryPolicyRow]:
    params = {
        "balancing": balancing_recommendation,
        "product_key": product_key,
        "warehouse_key": warehouse_key,
    }

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM ds_inventory_policy WHERE {_DETAIL_FILTER}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT product_key, warehouse_key, safety_stock, reorder_point, "
            "service_level_inventory_target, current_available_quantity, "
            "balancing_recommendation, confidence, contributing_factors, business_rationale, "
            "primary_supplier_key "
            f"FROM ds_inventory_policy WHERE {_DETAIL_FILTER} "
            "ORDER BY reorder_point DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            InventoryPolicyRow(
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                safety_stock=float(r.safety_stock),
                reorder_point=float(r.reorder_point),
                service_level_inventory_target=float(r.service_level_inventory_target),
                current_available_quantity=float(r.current_available_quantity),
                balancing_recommendation=r.balancing_recommendation,
                confidence=r.confidence,
                contributing_factors=json.loads(r.contributing_factors),
                business_rationale=r.business_rationale,
                primary_supplier_key=r.primary_supplier_key,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
