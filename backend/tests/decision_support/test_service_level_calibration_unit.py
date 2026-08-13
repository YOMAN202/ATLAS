"""Direct tests of the calibration harness
(backend/app/decision_support/service_level_calibration.py) against
hand-computable expected values.
"""

import pytest

from app.decision_support.service_level_calibration import (
    brier_score,
    calibration_buckets,
    naive_baseline_brier_score,
)


def test_brier_score_is_zero_for_perfect_predictions():
    assert brier_score([(1.0, 1.0), (0.0, 0.0)]) == 0.0


def test_brier_score_matches_hand_computed_value():
    # ((0.5-1)^2 + (0.5-0)^2) / 2 = (0.25 + 0.25) / 2 = 0.25
    assert brier_score([(0.5, 1.0), (0.5, 0.0)]) == 0.25


def test_brier_score_requires_at_least_one_pair():
    with pytest.raises(ValueError):
        brier_score([])


def test_naive_baseline_brier_score_matches_hand_computed_value():
    # population_rate is supplied externally (from training data), not
    # derived from the pairs' own actual outcomes -- an oracle baseline
    # would trivially minimize itself and could never honestly be beaten.
    # score = ((2/3-1)^2 + (2/3-0)^2 + (2/3-1)^2) / 3
    #       = ((1/9) + (4/9) + (1/9)) / 3 = (6/9) / 3 = 2/9
    pairs = [(0.9, 1.0), (0.1, 0.0), (0.5, 1.0)]
    assert round(naive_baseline_brier_score(pairs, population_rate=2 / 3), 6) == round(2 / 9, 6)


def test_naive_baseline_brier_score_is_not_automatically_minimized():
    # A population_rate that does NOT match the pairs' own mean outcome
    # must score worse than one that does -- proving this isn't secretly
    # still computing an in-sample oracle under a different name.
    pairs = [(0.5, 1.0), (0.5, 0.0), (0.5, 1.0)]
    fair = naive_baseline_brier_score(pairs, population_rate=0.1)
    oracle_equivalent = naive_baseline_brier_score(pairs, population_rate=2 / 3)
    assert fair > oracle_equivalent


def test_calibration_buckets_splits_into_equal_count_groups_sorted_by_predicted_probability():
    pairs = [(i / 10, 1.0 if i >= 5 else 0.0) for i in range(10)]  # 0.0..0.9
    buckets = calibration_buckets(pairs, n_buckets=10)
    assert len(buckets) == 10
    assert [b.n_observations for b in buckets] == [1] * 10
    # bucket 0 holds the lowest predicted probability (0.0), bucket 9 the highest (0.9)
    assert buckets[0].predicted_probability_mean == 0.0
    assert buckets[9].predicted_probability_mean == 0.9
    # a perfectly-ordered predicted-vs-actual relationship: every bucket's
    # actual_outcome_rate matches what was hand-assigned above
    assert buckets[0].actual_outcome_rate == 0.0
    assert buckets[9].actual_outcome_rate == 1.0


def test_calibration_buckets_handles_fewer_pairs_than_buckets():
    pairs = [(0.1, 0.0), (0.9, 1.0)]
    buckets = calibration_buckets(pairs, n_buckets=10)
    # only 2 pairs -> at most 2 non-empty buckets, never a crash or
    # fabricated empty-bucket rows
    assert len(buckets) <= 2
    assert sum(b.n_observations for b in buckets) == 2


def test_calibration_buckets_empty_input_returns_empty_list():
    assert calibration_buckets([], n_buckets=10) == []
