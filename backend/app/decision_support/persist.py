"""Generates and persists real forecasts using the selected model,
across all three grains — the write side of Module A, separate from
forecasting.py's evaluation/selection logic so "how a model is chosen"
and "how a chosen model's output gets written" stay independently
readable.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.decision_support.models import ForecastResult
from app.decision_support.series import Series

CONFIDENCE_Z = 1.96  # ~95% interval from the model's own residual_std — never fabricated


def mark_active_model(conn: Connection, module: str, model_id: int) -> None:
    conn.execute(
        text("UPDATE ds_model_registry SET is_active = 0 WHERE module = :module"),
        {"module": module},
    )
    conn.execute(
        text("UPDATE ds_model_registry SET is_active = 1 WHERE id = :id"), {"id": model_id}
    )


def _clear_prior_forecasts(conn: Connection, grain_type: str, model_id: int) -> None:
    """Idempotent rerun via delete-then-insert — the same pattern
    summary_daily_revenue_by_region already uses (etl/stage_b.py),
    not a fragile upsert on a mixed-nullable-column key (52_ds_demand_
    forecast.sql's own comment explains why a UNIQUE constraint doesn't
    work here)."""
    conn.execute(
        text(
            "DELETE FROM ds_demand_forecast WHERE grain_type = :grain_type AND model_id = :model_id"
        ),
        {"grain_type": grain_type, "model_id": model_id},
    )


def persist_forecasts(
    conn: Connection,
    grain_type: str,
    series_list: list[Series],
    model_fn,
    model_params: dict,
    model_id: int,
    etl_run_id: int,
    horizon: int,
) -> int:
    """Fits the model on each series' FULL available history (not a
    held-out split — this is the real, deployed forecast, not a
    backtest) and writes one row per (series, forecast_date)."""

    _clear_prior_forecasts(conn, grain_type, model_id)
    now = datetime.now(UTC)
    rows: list[dict] = []

    for s in series_list:
        result: ForecastResult = model_fn(s.dates, s.values, horizon, **model_params)
        ci_low_delta = CONFIDENCE_Z * result.residual_std
        for forecast_date, predicted in zip(result.dates, result.predictions, strict=False):
            row = {
                "grain_type": grain_type,
                "forecast_date": forecast_date,
                "predicted_quantity": max(predicted, 0.0),  # demand can't be negative
                "confidence_interval_low": max(predicted - ci_low_delta, 0.0),
                "confidence_interval_high": predicted + ci_low_delta,
                "model_id": model_id,
                "etl_run_id": etl_run_id,
                "generated_at": now,
                "product_key": None,
                "warehouse_key": None,
                "category": None,
                "region_key": None,
            }
            if grain_type == "sku_warehouse":
                row["product_key"], row["warehouse_key"] = s.key
            elif grain_type == "category":
                (row["category"],) = s.key
            elif grain_type == "region":
                (row["region_key"],) = s.key
            rows.append(row)

    if not rows:
        return 0

    _CHUNK = 2000
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i : i + _CHUNK]
        conn.execute(
            text(
                "INSERT INTO ds_demand_forecast "
                "(grain_type, product_key, warehouse_key, category, region_key, forecast_date, "
                "predicted_quantity, confidence_interval_low, confidence_interval_high, "
                "model_id, etl_run_id, generated_at) "
                "VALUES (:grain_type, :product_key, :warehouse_key, :category, :region_key, "
                ":forecast_date, :predicted_quantity, :confidence_interval_low, "
                ":confidence_interval_high, :model_id, :etl_run_id, :generated_at)"
            ),
            chunk,
        )
    return len(rows)
