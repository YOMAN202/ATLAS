"""Planning dashboard — demand forecasting (Phase 7 Module A). Read-only,
via the dashboard API's existing atlas_reporting connection (its schema-
wide SELECT on atlas_olap already covers the new ds_* tables — no new
grant needed, docs/phase7-architecture.md §6). Forecasts themselves are
written exclusively by the batch process
(backend/app/decision_support/run_module_a.py, via the separate
atlas_decision_support role) — no endpoint here accepts a write.

Role: supply_planner, administrator — SRS §3's Supply Planner actor is
the one who "views forecasts... and reviews reorder/risk
recommendations"; this is their dashboard, not a general-audience one
like Phase 6's.
"""

import json
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.api.schemas import PageEnvelope
from app.core.security import ADMINISTRATOR, EXECUTIVE, SUPPLY_PLANNER, require_role

router = APIRouter(prefix="/api/v1/dashboards/planning", tags=["planning"])


class ActiveModelInfo(BaseModel):
    model_id: int
    model_name: str
    parameters: dict
    weighted_avg_mape: float | None
    baseline_mape: float | None


class ForecastSummary(BaseModel):
    etl_run_id: int
    active_model: ActiveModelInfo | None
    forecast_horizon_days: int
    total_predicted_demand_next_30d: float
    forecast_generated_at: str | None
    n_sku_warehouse_series: int
    n_category_series: int
    n_region_series: int


class ForecastRow(BaseModel):
    grain_type: str
    product_key: int | None
    warehouse_key: int | None
    category: str | None
    region_key: int | None
    forecast_date: date
    predicted_quantity: float
    confidence_interval_low: float | None
    confidence_interval_high: float | None
    model_name: str


class ExperimentRow(BaseModel):
    model_name: str
    series_scope: str
    metric_value: float | None
    baseline_metric_value: float | None
    n_observations: int
    test_start_date: date
    test_end_date: date


@router.get("/forecast/summary", response_model=ForecastSummary)
def get_forecast_summary(
    conn: Connection = Depends(get_olap_connection),
    # EXECUTIVE added (v2 redesign) -- the executive command center
    # surfaces forecast accuracy alongside revenue/margin; read-only,
    # same summary data already visible to supply_planner/administrator.
    _role: str = Depends(require_role(EXECUTIVE, SUPPLY_PLANNER, ADMINISTRATOR)),
) -> ForecastSummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("forecast_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    active = conn.execute(
        text(
            "SELECT id, model_name, parameters FROM ds_model_registry "
            "WHERE module = 'demand_forecasting' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()

    active_model = None
    if active is not None:
        eval_row = conn.execute(
            text(
                "SELECT AVG(metric_value) AS avg_mape, AVG(baseline_metric_value) AS avg_baseline "
                "FROM ds_experiment_run WHERE model_id = :model_id"
            ),
            {"model_id": active.id},
        ).one()
        mape = eval_row.avg_mape
        baseline = eval_row.avg_baseline
        active_model = ActiveModelInfo(
            model_id=active.id,
            model_name=active.model_name,
            parameters=json.loads(active.parameters),
            weighted_avg_mape=float(mape) if mape is not None else None,
            baseline_mape=float(baseline) if baseline is not None else None,
        )

    # Region grain only: the dense, non-intermittent series (5 regions,
    # every day non-zero), so "total predicted demand" is a stable
    # headline number rather than summing 5,972 series including many
    # near-zero ones.
    totals = conn.execute(
        text(
            "SELECT COALESCE(SUM(predicted_quantity), 0) AS total, "
            "MAX(generated_at) AS generated_at, COUNT(DISTINCT region_key) AS n_region "
            "FROM ds_demand_forecast WHERE grain_type = 'region'"
        )
    ).one()

    result = ForecastSummary(
        etl_run_id=etl_run_id,
        active_model=active_model,
        forecast_horizon_days=30,
        total_predicted_demand_next_30d=float(totals.total),
        forecast_generated_at=str(totals.generated_at) if totals.generated_at else None,
        n_sku_warehouse_series=_count_series(conn, "sku_warehouse"),
        n_category_series=_count_series(conn, "category"),
        n_region_series=int(totals.n_region),
    )
    set_cached(key, result)
    return result


def _count_series(conn: Connection, grain_type: str) -> int:
    if grain_type == "sku_warehouse":
        expr = "CONCAT(product_key, '-', warehouse_key)"
    elif grain_type == "category":
        expr = "category"
    else:
        expr = "region_key"
    return conn.execute(
        text(
            f"SELECT COUNT(DISTINCT {expr}) FROM ds_demand_forecast WHERE grain_type = :grain_type"
        ),
        {"grain_type": grain_type},
    ).scalar_one()


_DETAIL_FILTER = (
    "f.grain_type = :grain_type "
    "AND (:product_key IS NULL OR f.product_key = :product_key) "
    "AND (:warehouse_key IS NULL OR f.warehouse_key = :warehouse_key) "
    "AND (:category IS NULL OR f.category = :category) "
    "AND (:region_key IS NULL OR f.region_key = :region_key) "
    "AND (:date_from IS NULL OR f.forecast_date >= :date_from) "
    "AND (:date_to IS NULL OR f.forecast_date <= :date_to)"
)


@router.get("/forecast/detail", response_model=PageEnvelope[ForecastRow])
def get_forecast_detail(
    grain_type: str = Query("sku_warehouse", pattern="^(sku_warehouse|category|region)$"),
    product_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    category: str | None = Query(None),
    region_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> PageEnvelope[ForecastRow]:
    params = {
        "grain_type": grain_type,
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "category": category,
        "region_key": region_key,
        "date_from": date_from,
        "date_to": date_to,
    }

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM ds_demand_forecast f WHERE {_DETAIL_FILTER}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT f.grain_type, f.product_key, f.warehouse_key, f.category, f.region_key, "
            "f.forecast_date, f.predicted_quantity, f.confidence_interval_low, "
            "f.confidence_interval_high, mr.model_name "
            "FROM ds_demand_forecast f JOIN ds_model_registry mr ON mr.id = f.model_id "
            f"WHERE {_DETAIL_FILTER} "
            "ORDER BY f.forecast_date LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            ForecastRow(
                grain_type=r.grain_type,
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                category=r.category,
                region_key=r.region_key,
                forecast_date=r.forecast_date,
                predicted_quantity=float(r.predicted_quantity),
                confidence_interval_low=(
                    float(r.confidence_interval_low)
                    if r.confidence_interval_low is not None
                    else None
                ),
                confidence_interval_high=(
                    float(r.confidence_interval_high)
                    if r.confidence_interval_high is not None
                    else None
                ),
                model_name=r.model_name,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )


@router.get("/forecast/experiments", response_model=list[ExperimentRow])
def get_forecast_experiments(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[ExperimentRow]:
    """Every backtested model's per-series results — the concrete
    mechanism behind FR-8.4 ("traceable to the underlying data and
    rule"): a Supply Planner can see exactly why the active model was
    chosen over the other four candidates, not just take it on faith.
    """
    rows = conn.execute(
        text(
            "SELECT mr.model_name, er.series_scope, er.metric_value, er.baseline_metric_value, "
            "er.n_observations, er.test_start_date, er.test_end_date "
            "FROM ds_experiment_run er JOIN ds_model_registry mr ON mr.id = er.model_id "
            "ORDER BY mr.model_name, er.series_scope"
        )
    ).all()
    return [
        ExperimentRow(
            model_name=r.model_name,
            series_scope=r.series_scope,
            metric_value=float(r.metric_value) if r.metric_value is not None else None,
            baseline_metric_value=(
                float(r.baseline_metric_value) if r.baseline_metric_value is not None else None
            ),
            n_observations=r.n_observations,
            test_start_date=r.test_start_date,
            test_end_date=r.test_end_date,
        )
        for r in rows
    ]
