"""Walk-forward backtesting and MAPE evaluation (SRS §15's named
Planning KPI, and the evaluation gate docs/phase7-architecture.md §7
and docs/phase7-review-checklist.md §E require before a model is
promoted to is_active=1).

MAPE is undefined when the actual value is zero (division by zero) —
a real, expected characteristic of this dataset, not an edge case to
paper over: per-SKU daily demand is intermittent (average 52.7 non-zero
days out of 365 per product/warehouse pair, confirmed directly against
v_daily_demand). Zero-actual days are excluded from the MAPE
denominator — a standard, documented convention for intermittent-demand
evaluation — and the count excluded is always reported alongside the
metric, so the coverage is visible rather than silently reduced.
"""

from dataclasses import dataclass
from datetime import date

from app.decision_support.models import ForecastResult


@dataclass
class MapeResult:
    mape: float | None  # None if every actual in the window was zero
    n_scored: int
    n_skipped_zero_actual: int


def mean_absolute_percentage_error(actuals: list[float], predictions: list[float]) -> MapeResult:
    errors = []
    skipped = 0
    for a, p in zip(actuals, predictions, strict=False):
        if a == 0:
            skipped += 1
            continue
        errors.append(abs(a - p) / abs(a))
    if not errors:
        return MapeResult(mape=None, n_scored=0, n_skipped_zero_actual=skipped)
    return MapeResult(
        mape=(sum(errors) / len(errors)) * 100, n_scored=len(errors), n_skipped_zero_actual=skipped
    )


@dataclass
class BacktestResult:
    model_name: str
    mape_result: MapeResult
    test_start: date
    test_end: date


def backtest(
    dates: list[date],
    values: list[float],
    model_name: str,
    model_fn,
    model_params: dict,
    test_days: int,
) -> BacktestResult:
    """Train on everything except the last `test_days` days, forecast
    that held-out window, score against the real values that actually
    happened — walk-forward validation against real historical
    fact_orders data, never synthetic data (docs/phase7-architecture.md
    §7).
    """
    train_dates, train_values = dates[:-test_days], values[:-test_days]
    actual = values[-test_days:]
    result: ForecastResult = model_fn(train_dates, train_values, test_days, **model_params)
    mape_result = mean_absolute_percentage_error(actual, result.predictions)
    return BacktestResult(
        model_name=model_name,
        mape_result=mape_result,
        test_start=dates[-test_days],
        test_end=dates[-1],
    )
