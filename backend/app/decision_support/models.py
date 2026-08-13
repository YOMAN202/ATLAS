"""Statistical demand forecasting models (Phase 7 Module A). Per ADR-004
(no ML framework) and SRS FR-5.1 ("statistical, not generative-AI
based"), every model here is a named, closed-form formula over a plain
list of numbers — nothing fitted, nothing serialized, nothing a human
can't recompute by hand from the formula in this file. Standard-library
only (`statistics`), no numpy/scipy/scikit-learn dependency added.

Every model takes a complete, gap-filled daily series (no missing
dates — the caller is responsible for 0-filling non-demand days before
calling any of these, since "no row" in fact_orders means zero demand
that day, not an unknown value) and returns a ForecastResult: the
predicted values for the requested horizon, plus the in-sample residual
standard deviation, which the caller uses to build a confidence
interval (predicted ± 1.96 * residual_std for a ~95% interval) — a
number derived from the model's own historical prediction errors, never
fabricated.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev


@dataclass
class ForecastResult:
    dates: list[date]
    predictions: list[float]
    residual_std: float


def _future_dates(last_date: date, horizon: int) -> list[date]:
    return [last_date + timedelta(days=i + 1) for i in range(horizon)]


def seasonal_naive(
    dates: list[date], values: list[float], horizon: int, period: int = 7
) -> ForecastResult:
    """forecast(t) = actual(t - period) — "demand will look like it did
    `period` days ago." The MAPE floor every other model must beat
    (docs/phase7-architecture.md §7); not a strawman, a real, commonly-
    used baseline for demand with weekly seasonality.
    """
    n = len(values)
    predictions = [values[n - period + (i % period)] for i in range(horizon)]
    residuals = [values[i] - values[i - period] for i in range(period, n)]
    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    return ForecastResult(_future_dates(dates[-1], horizon), predictions, residual_std)


def moving_average(
    dates: list[date], values: list[float], horizon: int, window: int = 7
) -> ForecastResult:
    """forecast = the flat mean of the trailing `window` days, repeated
    across the whole horizon — the simplest possible smoother.
    """
    n = len(values)
    level = mean(values[-window:])
    predictions = [level] * horizon
    residuals = [values[i] - mean(values[i - window : i]) for i in range(window, n)]
    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    return ForecastResult(_future_dates(dates[-1], horizon), predictions, residual_std)


def simple_exponential_smoothing(
    dates: list[date], values: list[float], horizon: int, alpha: float = 0.3
) -> ForecastResult:
    """level_t = alpha * actual_t + (1 - alpha) * level_(t-1); forecast
    = the last level, flat across the horizon. Weights recent history
    more than old history (unlike a plain moving average, which weighs
    every day in the window equally), still fully explainable — alpha
    is the one knob and its meaning ("how fast old data is forgotten")
    is standard textbook material, not a hidden coefficient.
    """
    level = values[0]
    residuals = []
    for v in values[1:]:
        residuals.append(v - level)
        level = alpha * v + (1 - alpha) * level
    predictions = [level] * horizon
    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    return ForecastResult(_future_dates(dates[-1], horizon), predictions, residual_std)


def seasonal_exponential_smoothing(
    dates: list[date], values: list[float], horizon: int, alpha: float = 0.3, period: int = 7
) -> ForecastResult:
    """Additive weekly-seasonal SES: compute each weekday's average
    deviation from the overall mean (the "seasonal index"), subtract it
    out (deseasonalize), run plain SES on the deseasonalized level, add
    the seasonal index back in when forecasting. Additive, not
    multiplicative, deliberately — this dataset's per-SKU daily demand
    is intermittent (average 52.7 non-zero days out of 365 per product/
    warehouse pair, confirmed directly against v_daily_demand), and a
    multiplicative index would divide by figures that are frequently
    zero; additive stays well-defined throughout.
    """
    n = len(values)
    overall_mean = mean(values)
    seasonal_index = [0.0] * period
    for p in range(period):
        seasonal_values = values[p::period]
        seasonal_index[p] = (mean(seasonal_values) - overall_mean) if seasonal_values else 0.0

    deseasonalized = [values[i] - seasonal_index[i % period] for i in range(n)]
    level = deseasonalized[0]
    residuals = []
    for i in range(1, n):
        pred = level + seasonal_index[i % period]
        residuals.append(values[i] - pred)
        level = alpha * deseasonalized[i] + (1 - alpha) * level

    predictions = [level + seasonal_index[(n + i) % period] for i in range(horizon)]
    residual_std = pstdev(residuals) if len(residuals) > 1 else 0.0
    return ForecastResult(_future_dates(dates[-1], horizon), predictions, residual_std)


# The fixed set of candidate models this module evaluates (docs/phase7-
# architecture.md §5's ds_model_registry rows) — "multiple benchmark
# models" per your Phase 7 objective, all statistical, all inspectable.
MODEL_SPECS: list[tuple[str, dict, Callable]] = [
    ("seasonal_naive", {"period": 7}, seasonal_naive),
    ("moving_average_7d", {"window": 7}, moving_average),
    ("moving_average_14d", {"window": 14}, moving_average),
    ("simple_exponential_smoothing", {"alpha": 0.3}, simple_exponential_smoothing),
    ("seasonal_exponential_smoothing", {"alpha": 0.3, "period": 7}, seasonal_exponential_smoothing),
]
