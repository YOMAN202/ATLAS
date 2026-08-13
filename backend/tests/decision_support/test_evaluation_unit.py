"""Direct tests of MAPE computation and walk-forward backtesting
(backend/app/decision_support/evaluation.py) — especially the zero-
actual-demand handling, since roughly 85% of per-SKU daily observations
in the real dataset are zero (docs/phase7-module-a-completion.md §4)
and MAPE is undefined there by definition, not by accident.
"""

from datetime import date, timedelta

from app.decision_support.evaluation import backtest, mean_absolute_percentage_error
from app.decision_support.models import seasonal_naive


def _dates(n: int) -> list[date]:
    start = date(2021, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_mape_is_zero_for_a_perfect_prediction():
    result = mean_absolute_percentage_error([10, 20, 30], [10, 20, 30])
    assert result.mape == 0.0
    assert result.n_scored == 3
    assert result.n_skipped_zero_actual == 0


def test_mape_matches_hand_computed_percentage():
    result = mean_absolute_percentage_error([100], [110])
    assert result.mape == 10.0  # |100 - 110| / 100 * 100


def test_mape_excludes_zero_actual_days_from_the_denominator():
    # Only indices 1 and 3 (actual != 0) are scored; both are perfect
    # predictions, so MAPE is 0 despite two mismatched zero-actual points.
    result = mean_absolute_percentage_error([0, 10, 0, 20], [5, 10, 5, 20])
    assert result.mape == 0.0
    assert result.n_scored == 2
    assert result.n_skipped_zero_actual == 2


def test_mape_is_none_when_every_actual_in_the_window_is_zero():
    result = mean_absolute_percentage_error([0, 0, 0], [1, 2, 3])
    assert result.mape is None
    assert result.n_scored == 0
    assert result.n_skipped_zero_actual == 3


def test_backtest_trains_on_everything_except_the_held_out_window():
    # A clean two-week seasonal-naive setup: week 2 == week 1 exactly,
    # so a 7-day-ahead backtest of the last 7 (held-out) days against a
    # seasonal_naive model trained on the first 7 should be a perfect
    # forecast (0% MAPE) — this exercises the actual train/test split,
    # not just the model formula in isolation.
    week = [10, 20, 30, 40, 50, 60, 70]
    values = week + week
    result = backtest(
        _dates(14), values, "seasonal_naive", seasonal_naive, {"period": 7}, test_days=7
    )
    assert result.mape_result.mape == 0.0
    assert result.test_start == date(2021, 1, 8)
    assert result.test_end == date(2021, 1, 14)
