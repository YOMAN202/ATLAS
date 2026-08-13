"""Planning dashboard — service-level prediction (Phase 7 Module D).
Read-only, via the dashboard API's existing atlas_reporting connection
(its schema-wide SELECT on atlas_olap already covers the new ds_*
tables — no new grant needed). Predictions and calibration results are
written exclusively by the batch process
(backend/app/decision_support/run_module_d.py, via the separate
atlas_decision_support role).

Role: supply_planner, administrator — same actor as Modules A/C's
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

router = APIRouter(prefix="/api/v1/dashboards/planning/service-level", tags=["planning"])


class ServiceLevelSummary(BaseModel):
    etl_run_id: int
    model_id: int | None
    model_name: str | None
    source_forecast_model_id: int | None
    source_supplier_model_id: int | None
    generated_at: str | None
    n_predictions: int
    n_with_delay_prediction: int
    avg_stockout_probability: float | None
    avg_backorder_probability: float | None
    avg_fulfillment_delay_probability: float | None
    n_high_stockout_risk: int


class CalibrationResult(BaseModel):
    prediction_type: str
    brier_score: float
    baseline_brier_score: float
    n_observations: int
    test_start_date: str
    test_end_date: str
    buckets: list["CalibrationBucketRow"]


class CalibrationBucketRow(BaseModel):
    bucket_index: int
    predicted_probability_mean: float
    actual_outcome_rate: float
    n_observations: int


class ServiceLevelRow(BaseModel):
    product_key: int
    warehouse_key: int
    stockout_probability: float
    stockout_confidence: str
    stockout_contributing_factors: dict
    backorder_probability: float
    backorder_confidence: str
    backorder_contributing_factors: dict
    fulfillment_delay_probability: float | None
    fulfillment_delay_confidence: str | None
    fulfillment_delay_contributing_factors: dict | None
    primary_supplier_key: int | None


HIGH_STOCKOUT_RISK_THRESHOLD = 0.5


@router.get("/summary", response_model=ServiceLevelSummary)
def get_service_level_summary(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> ServiceLevelSummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("service_level_summary", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    model_row = conn.execute(
        text(
            "SELECT id, model_name FROM ds_model_registry "
            "WHERE module = 'service_level_prediction' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()

    totals = conn.execute(
        text(
            "SELECT COUNT(*) AS n, "
            "SUM(fulfillment_delay_probability IS NOT NULL) AS n_with_delay, "
            "AVG(stockout_probability) AS avg_stockout, "
            "AVG(backorder_probability) AS avg_backorder, "
            "AVG(fulfillment_delay_probability) AS avg_delay, "
            "MAX(generated_at) AS generated_at, "
            "MAX(source_forecast_model_id) AS source_forecast_model_id, "
            "MAX(source_supplier_model_id) AS source_supplier_model_id, "
            "SUM(stockout_probability > :threshold) AS n_high_risk "
            "FROM ds_service_level_prediction"
        ),
        {"threshold": HIGH_STOCKOUT_RISK_THRESHOLD},
    ).one()

    result = ServiceLevelSummary(
        etl_run_id=etl_run_id,
        model_id=model_row.id if model_row else None,
        model_name=model_row.model_name if model_row else None,
        source_forecast_model_id=totals.source_forecast_model_id,
        source_supplier_model_id=totals.source_supplier_model_id,
        generated_at=str(totals.generated_at) if totals.generated_at else None,
        n_predictions=int(totals.n),
        n_with_delay_prediction=int(totals.n_with_delay or 0),
        avg_stockout_probability=(
            float(totals.avg_stockout) if totals.avg_stockout is not None else None
        ),
        avg_backorder_probability=(
            float(totals.avg_backorder) if totals.avg_backorder is not None else None
        ),
        avg_fulfillment_delay_probability=(
            float(totals.avg_delay) if totals.avg_delay is not None else None
        ),
        n_high_stockout_risk=int(totals.n_high_risk or 0),
    )
    set_cached(key, result)
    return result


@router.get("/calibration", response_model=list[CalibrationResult])
def get_service_level_calibration(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[CalibrationResult]:
    """The module brief's "calibration analysis" deliverable, made
    queryable: per prediction type, the walk-forward Brier score
    against a fair (training-only) naive baseline, plus the decile
    reliability-diagram buckets those scores are computed from."""
    model_row = conn.execute(
        text(
            "SELECT id FROM ds_model_registry "
            "WHERE module = 'service_level_prediction' AND is_active = 1 LIMIT 1"
        )
    ).one_or_none()
    if model_row is None:
        return []

    experiments = conn.execute(
        text(
            "SELECT series_scope, metric_value, baseline_metric_value, n_observations, "
            "test_start_date, test_end_date FROM ds_experiment_run "
            "WHERE model_id = :model_id AND metric_name = 'BRIER_SCORE'"
        ),
        {"model_id": model_row.id},
    ).all()

    buckets_by_type: dict[str, list[CalibrationBucketRow]] = {}
    bucket_rows = conn.execute(
        text(
            "SELECT prediction_type, bucket_index, predicted_probability_mean, "
            "actual_outcome_rate, n_observations FROM ds_calibration_bucket "
            "WHERE model_id = :model_id ORDER BY prediction_type, bucket_index"
        ),
        {"model_id": model_row.id},
    ).all()
    for b in bucket_rows:
        buckets_by_type.setdefault(b.prediction_type, []).append(
            CalibrationBucketRow(
                bucket_index=b.bucket_index,
                predicted_probability_mean=float(b.predicted_probability_mean),
                actual_outcome_rate=float(b.actual_outcome_rate),
                n_observations=b.n_observations,
            )
        )

    return [
        CalibrationResult(
            prediction_type=e.series_scope,
            brier_score=float(e.metric_value),
            baseline_brier_score=float(e.baseline_metric_value),
            n_observations=e.n_observations,
            test_start_date=str(e.test_start_date),
            test_end_date=str(e.test_end_date),
            buckets=buckets_by_type.get(e.series_scope, []),
        )
        for e in experiments
    ]


_DETAIL_FILTER = (
    "(:min_stockout IS NULL OR stockout_probability >= :min_stockout) "
    "AND (:min_backorder IS NULL OR backorder_probability >= :min_backorder) "
    "AND (:min_delay IS NULL OR fulfillment_delay_probability >= :min_delay)"
)


@router.get("/detail", response_model=PageEnvelope[ServiceLevelRow])
def get_service_level_detail(
    min_stockout: float | None = Query(None, ge=0, le=1),
    min_backorder: float | None = Query(None, ge=0, le=1),
    min_delay: float | None = Query(None, ge=0, le=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> PageEnvelope[ServiceLevelRow]:
    params = {
        "min_stockout": min_stockout,
        "min_backorder": min_backorder,
        "min_delay": min_delay,
    }

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM ds_service_level_prediction WHERE {_DETAIL_FILTER}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT product_key, warehouse_key, stockout_probability, stockout_confidence, "
            "stockout_contributing_factors, backorder_probability, backorder_confidence, "
            "backorder_contributing_factors, fulfillment_delay_probability, "
            "fulfillment_delay_confidence, fulfillment_delay_contributing_factors, "
            "primary_supplier_key "
            f"FROM ds_service_level_prediction WHERE {_DETAIL_FILTER} "
            "ORDER BY stockout_probability DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            ServiceLevelRow(
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                stockout_probability=float(r.stockout_probability),
                stockout_confidence=r.stockout_confidence,
                stockout_contributing_factors=json.loads(r.stockout_contributing_factors),
                backorder_probability=float(r.backorder_probability),
                backorder_confidence=r.backorder_confidence,
                backorder_contributing_factors=json.loads(r.backorder_contributing_factors),
                fulfillment_delay_probability=(
                    float(r.fulfillment_delay_probability)
                    if r.fulfillment_delay_probability is not None
                    else None
                ),
                fulfillment_delay_confidence=r.fulfillment_delay_confidence,
                fulfillment_delay_contributing_factors=(
                    json.loads(r.fulfillment_delay_contributing_factors)
                    if r.fulfillment_delay_contributing_factors is not None
                    else None
                ),
                primary_supplier_key=r.primary_supplier_key,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
