from collections import Counter
from datetime import date

import numpy as np
import pytest
from app.models import Order, OrderLine
from sqlalchemy import select

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.demand import (
    _weighted_indices_without_replacement,
    generate_daily_orders,
    seasonal_multiplier,
)
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats


# FR-5.3: seasonality curve peaks in late November, troughs half a year away.
def test_seasonal_multiplier_peaks_in_late_november():
    peak = seasonal_multiplier(date(2021, 12, 1), TEST_CONFIG)
    trough = seasonal_multiplier(date(2021, 6, 1), TEST_CONFIG)
    average = seasonal_multiplier(date(2021, 3, 2), TEST_CONFIG)

    assert peak > average > trough
    assert peak == pytest.approx(1.0 + TEST_CONFIG.seasonality_amplitude, abs=0.02)
    assert trough == pytest.approx(1.0 - TEST_CONFIG.seasonality_amplitude, abs=0.02)


def test_generate_daily_orders_creates_orders_and_allocates(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    generate_daily_orders(
        db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, SimulationStats()
    )

    assert db_session.scalar(select(Order).limit(1)) is not None

    lines = db_session.execute(select(OrderLine)).scalars().all()
    assert len(lines) > 0
    for line in lines:
        # BR-2: every line is either allocated, backordered, or both, and
        # never more than what was ordered.
        assert line.allocated_quantity + line.backordered_quantity <= line.ordered_quantity
        assert line.allocated_quantity >= 0
        assert line.backordered_quantity >= 0


# Calibration round 2 performance fix: _weighted_indices_without_replacement
# replaces numpy's native rng.choice(replace=False, p=...), which does real
# work across the whole population every call. Must remain a drop-in
# statistical + determinism equivalent.
def test_weighted_indices_without_replacement_never_duplicates():
    rng = np.random.default_rng(7)
    weights = np.array([0.5, 0.3, 0.1, 0.05, 0.05])

    for _ in range(200):
        indices = _weighted_indices_without_replacement(rng, weights, size=3)
        assert len(indices) == 3
        assert len(set(indices)) == 3
        assert all(0 <= i < len(weights) for i in indices)


def test_weighted_indices_without_replacement_is_deterministic_given_same_seed():
    weights = np.array([0.4, 0.3, 0.15, 0.1, 0.05])

    rng1 = np.random.default_rng(99)
    draws1 = [_weighted_indices_without_replacement(rng1, weights, size=2) for _ in range(50)]

    rng2 = np.random.default_rng(99)
    draws2 = [_weighted_indices_without_replacement(rng2, weights, size=2) for _ in range(50)]

    assert draws1 == draws2


def test_weighted_indices_without_replacement_matches_native_numpy_distribution():
    """Statistical equivalence check against numpy's native
    rng.choice(replace=False, p=weights) — NOT against the raw weight
    vector directly. For size>1 without replacement, an item's per-slot
    marginal inclusion frequency is mathematically not the same as its
    raw weight (only true for size=1): a dominant item's inclusion
    probability compresses toward 1.0 rather than scaling linearly, which
    is a real property of without-replacement sampling, not drift. So the
    correct equivalence target is numpy's own without-replacement output,
    which the redraw-based approach is meant to reproduce cheaply.
    """

    weights = np.array([0.50, 0.25, 0.15, 0.06, 0.04])
    num_trials = 20_000

    rng_native = np.random.default_rng(123)
    native_counts = Counter()
    for _ in range(num_trials):
        for idx in rng_native.choice(len(weights), size=2, replace=False, p=weights):
            native_counts[int(idx)] += 1

    rng_optimized = np.random.default_rng(123)
    optimized_counts = Counter()
    for _ in range(num_trials):
        for idx in _weighted_indices_without_replacement(rng_optimized, weights, size=2):
            optimized_counts[idx] += 1

    total_picks = num_trials * 2
    native_empirical = np.array([native_counts[i] / total_picks for i in range(len(weights))])
    optimized_empirical = np.array([optimized_counts[i] / total_picks for i in range(len(weights))])

    assert list(np.argsort(-optimized_empirical)) == list(np.argsort(-native_empirical))
    assert np.max(np.abs(optimized_empirical - native_empirical)) < 0.02
