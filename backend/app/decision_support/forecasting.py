"""Module A orchestration (docs/phase7-architecture.md §5, §7,
docs/phase7-roadmap.md §3 step 1): register the candidate models,
backtest them against representative series, select whichever beats
the seasonal-naive baseline by the widest margin, then generate and
persist real 30-day-ahead forecasts for every qualifying series across
all three grains.

Evaluation strategy, stated plainly: this does not backtest all ~5,972
series individually before choosing a model family — that's neither
necessary (model *selection* doesn't need per-series backtesting, only
model *application* does) nor cheap enough to be worth it for five
closed-form formulas. Instead, every candidate is backtested against
(a) all 5 region-level series (dense, no missing days) and (b) two
40-series SKU/warehouse samples — the top 20 by total order volume and
20 more drawn from the middle of the volume distribution — so the
evaluation honestly reflects both the best-selling and typical products,
not just the easy, data-rich case. The model with the lowest volume-
weighted average MAPE across every backtested point (that still beats
the seasonal-naive baseline) is promoted to is_active=1 and applied to
every qualifying series.
"""

import json
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.decision_support.evaluation import BacktestResult, backtest
from app.decision_support.models import MODEL_SPECS
from app.decision_support.series import (
    Series,
)

FORECAST_HORIZON_DAYS = 30
BACKTEST_TEST_DAYS = 30
MIN_ACTIVE_DAYS = 30


def get_or_create_model(conn: Connection, model_name: str, params: dict) -> int:
    existing = conn.execute(
        text(
            "SELECT id FROM ds_model_registry WHERE module = 'demand_forecasting' "
            "AND model_name = :name AND parameters = CAST(:params AS JSON)"
        ),
        {"name": model_name, "params": json.dumps(params, sort_keys=True)},
    ).scalar()
    if existing is not None:
        return existing
    result = conn.execute(
        text(
            "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, created_at) "
            "VALUES ('demand_forecasting', :name, CAST(:params AS JSON), 0, :now)"
        ),
        {
            "name": model_name,
            "params": json.dumps(params, sort_keys=True),
            "now": datetime.now(UTC),
        },
    )
    return result.lastrowid


def _record_experiment(
    conn: Connection,
    model_id: int,
    result: BacktestResult,
    train_start: date,
    train_end: date,
    series_scope: str,
    baseline_mape: float | None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO ds_experiment_run "
            "(model_id, train_start_date, train_end_date, test_start_date, test_end_date, "
            "series_scope, metric_name, metric_value, baseline_metric_value, n_observations, "
            "run_at, notes) "
            "VALUES (:model_id, :train_start, :train_end, :test_start, :test_end, :scope, 'MAPE', "
            ":metric_value, :baseline, :n_obs, :now, :notes)"
        ),
        {
            "model_id": model_id,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": result.test_start,
            "test_end": result.test_end,
            "scope": series_scope,
            "metric_value": result.mape_result.mape,
            "baseline": baseline_mape,
            "n_obs": result.mape_result.n_scored,
            "now": datetime.now(UTC),
            "notes": f"skipped_zero_actual={result.mape_result.n_skipped_zero_actual}",
        },
    )


def select_backtest_sample(series: list[Series], n: int) -> list[Series]:
    """Top-n by total volume + n more from the middle of the
    distribution — see this module's docstring for why both matter."""
    ranked = sorted(series, key=lambda s: sum(s.values), reverse=True)
    top = ranked[:n]
    mid_start = max(0, len(ranked) // 2 - n // 2)
    middle = ranked[mid_start : mid_start + n]
    return top + middle


def run_backtests(conn: Connection, region_series: list[Series], sku_sample: list[Series]) -> dict:
    """Returns {model_name: {"model_id": int, "mape_points": [(mape, n_scored), ...]}}
    across every backtested series, plus records every run in
    ds_experiment_run for audit (docs/phase7-review-checklist.md §E)."""

    all_series = [("region", s) for s in region_series] + [
        ("sku_warehouse_sample", s) for s in sku_sample
    ]
    baseline_mapes: dict[tuple[str, tuple], float] = {}
    results: dict[str, dict] = {}

    for model_name, params, model_fn in MODEL_SPECS:
        model_id = get_or_create_model(conn, model_name, params)
        mape_points = []
        for scope, s in all_series:
            if len(s.values) <= BACKTEST_TEST_DAYS + 14:  # need real training history left over
                continue
            result = backtest(s.dates, s.values, model_name, model_fn, params, BACKTEST_TEST_DAYS)
            train_start, train_end = s.dates[0], s.dates[-BACKTEST_TEST_DAYS - 1]
            baseline = baseline_mapes.get((scope, s.key))
            _record_experiment(
                conn, model_id, result, train_start, train_end, f"{scope}:{s.key}", baseline
            )
            if model_name == "seasonal_naive":
                baseline_mapes[(scope, s.key)] = result.mape_result.mape
            if result.mape_result.mape is not None:
                mape_points.append((result.mape_result.mape, result.mape_result.n_scored, baseline))
        results[model_name] = {"model_id": model_id, "mape_points": mape_points}

    return results


def select_best_model(backtest_results: dict) -> tuple[str, int, float]:
    """Volume-weighted average MAPE across every scored point, lowest
    wins — but only among models that, on average, beat the seasonal-
    naive baseline; falls back to seasonal_naive itself if nothing
    does (a real, reportable outcome, not hidden)."""

    scored = {}
    for model_name, data in backtest_results.items():
        points = data["mape_points"]
        if not points:
            continue
        total_weight = sum(n for _, n, _ in points)
        weighted_avg = sum(mape * n for mape, n, _ in points) / total_weight
        scored[model_name] = (weighted_avg, data["model_id"])

    baseline_avg = scored["seasonal_naive"][0]

    candidates = {k: v for k, v in scored.items() if v[0] <= baseline_avg} or {
        "seasonal_naive": scored["seasonal_naive"]
    }
    best_name = min(candidates, key=lambda k: candidates[k][0])
    return best_name, candidates[best_name][1], candidates[best_name][0]
