"""Direct tests of every forecasting formula (backend/app/decision_support/
models.py) against hand-computable expected values — the actual
mechanism proving these are inspectable statistical formulas, not a
fitted black box (SRS FR-8.4, ADR-004).
"""

from datetime import date, timedelta

from app.decision_support.models import (
    moving_average,
    seasonal_exponential_smoothing,
    seasonal_naive,
    simple_exponential_smoothing,
)


def _dates(n: int) -> list[date]:
    start = date(2021, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_seasonal_naive_repeats_the_last_full_period():
    values = [1, 2, 3, 4, 5, 6, 7, 10, 20, 30, 40, 50, 60, 70]  # 2 full weeks
    result = seasonal_naive(_dates(14), values, horizon=7, period=7)
    assert result.predictions == [10, 20, 30, 40, 50, 60, 70]  # exactly week 2 again
    assert result.dates[0] == date(2021, 1, 15)


def test_moving_average_is_the_flat_trailing_mean():
    values = [1, 2, 3, 4, 5, 6, 7]
    result = moving_average(_dates(7), values, horizon=3, window=7)
    assert result.predictions == [4.0, 4.0, 4.0]  # mean(1..7) == 4.0, repeated flat


def test_moving_average_uses_only_the_trailing_window():
    values = [100, 100, 100, 2, 4, 6]  # window=3 should ignore the leading 100s
    result = moving_average(_dates(6), values, horizon=1, window=3)
    assert result.predictions == [4.0]  # mean(2, 4, 6)


def test_simple_exponential_smoothing_reproduces_a_constant_series_exactly():
    values = [10.0] * 10
    result = simple_exponential_smoothing(_dates(10), values, horizon=5, alpha=0.5)
    assert result.predictions == [10.0] * 5
    assert result.residual_std == 0.0  # zero prediction error on a truly constant series


def test_seasonal_exponential_smoothing_reproduces_a_perfectly_periodic_series():
    pattern = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    values = pattern * 4  # 4 identical weeks, zero noise
    result = seasonal_exponential_smoothing(_dates(28), values, horizon=7, alpha=0.5, period=7)
    # a perfectly periodic, noise-free series should forecast as exactly itself
    assert [round(p, 6) for p in result.predictions] == pattern
    assert round(result.residual_std, 6) == 0.0


def test_seasonal_exponential_smoothing_seasonal_index_matches_hand_computed_deviation():
    # Two identical weeks -> the day-3 seasonal index is exactly
    # pattern[2] - mean(pattern), computable by hand.
    pattern = [5.0, 5.0, 20.0, 5.0, 5.0, 5.0, 5.0]
    values = pattern * 3
    overall_mean = sum(pattern) / len(pattern)
    result = seasonal_exponential_smoothing(_dates(21), values, horizon=7, alpha=0.3, period=7)
    expected_day3 = overall_mean + (pattern[2] - overall_mean)
    assert round(result.predictions[2], 6) == round(expected_day3, 6) == 20.0
