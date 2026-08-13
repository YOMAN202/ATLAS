"""Direct tests of the supplier risk formula
(backend/app/decision_support/supplier_scoring.py) against hand-
computable expected values — proving the composite score is an
inspectable weighted formula, not a fitted black box (ADR-004,
mirrors test_models_unit.py's discipline for Module A).
"""

from app.decision_support.supplier_scoring import (
    SupplierMetrics,
    _minmax_normalize,
    score_suppliers,
)


def _metrics(
    supplier_key, on_time_rate, quality_rejection_rate, lead_time_stddev_days, prior, recent
):
    return SupplierMetrics(
        supplier_key=supplier_key,
        n_deliveries=100,
        on_time_rate=on_time_rate,
        quality_rejection_rate=quality_rejection_rate,
        fill_rate=1.0,
        avg_lead_time_variance_days=0.0,
        lead_time_stddev_days=lead_time_stddev_days,
        recent_on_time_rate=recent,
        prior_on_time_rate=prior,
        total_spend=1000.0,
        share_of_total_spend=0.5,
        distinct_products_supplied=10,
        distinct_warehouses_served=2,
    )


def test_minmax_normalize_maps_the_observed_range_onto_0_to_100():
    assert _minmax_normalize(5, 0, 10) == 50.0
    assert _minmax_normalize(0, 0, 10) == 0.0
    assert _minmax_normalize(10, 0, 10) == 100.0


def test_minmax_normalize_returns_zero_for_a_population_wide_constant():
    # a metric with zero variance (e.g. fill_rate in the real dataset)
    # must contribute nothing to the score, not divide by zero.
    assert _minmax_normalize(1.0, 1.0, 1.0) == 0.0


def test_a_uniformly_better_supplier_scores_exactly_zero_and_the_other_exactly_one_hundred():
    # Two suppliers, one strictly better on every dimension: with only
    # two data points, min-max normalization sends the better supplier
    # to 0 and the worse one to 100 on every component, so the weighted
    # sum (which sums to 1.0) is hand-computable exactly.
    good = _metrics(
        "A",
        on_time_rate=1.0,
        quality_rejection_rate=0.0,
        lead_time_stddev_days=0.0,
        prior=1.0,
        recent=1.0,
    )
    bad = _metrics(
        "B",
        on_time_rate=0.5,
        quality_rejection_rate=0.1,
        lead_time_stddev_days=2.0,
        prior=1.0,
        recent=0.5,
    )

    results = score_suppliers([good, bad])
    by_key = {r.supplier_key: r for r in results}

    assert by_key["A"].risk_score == 0.0
    assert by_key["A"].risk_classification == "Low"
    assert by_key["A"].trend_direction == "stable"
    assert by_key["A"].triggering_metrics == []

    assert by_key["B"].risk_score == 100.0
    assert by_key["B"].risk_classification == "High"
    assert by_key["B"].trend_direction == "degrading"
    assert len(by_key["B"].triggering_metrics) == 4


def test_trend_delta_only_penalizes_decline_never_improvement():
    # prior < recent means on-time rate improved; the *scoring* input is
    # floored at 0 so improvement never earns a negative risk
    # contribution, but the *reported* on_time_rate_trend_delta stays
    # the real signed value so the output isn't misleadingly zeroed.
    improving = _metrics(
        "A",
        on_time_rate=0.9,
        quality_rejection_rate=0.01,
        lead_time_stddev_days=0.5,
        prior=0.7,
        recent=0.9,
    )
    flat = _metrics(
        "B",
        on_time_rate=0.9,
        quality_rejection_rate=0.01,
        lead_time_stddev_days=0.5,
        prior=0.9,
        recent=0.9,
    )

    results = score_suppliers([improving, flat])
    # the reported delta is the real, signed value (negative = improved) —
    # only the *scoring* input is floored at zero, never the output.
    assert results[0].on_time_rate_trend_delta == -0.2
    assert results[1].on_time_rate_trend_delta == 0.0
    assert results[0].trend_direction == "improving"
    assert results[1].trend_direction == "stable"
    # both floored to zero trend risk for scoring purposes -> identical
    # scores despite the different reported deltas
    assert results[0].risk_score == results[1].risk_score
