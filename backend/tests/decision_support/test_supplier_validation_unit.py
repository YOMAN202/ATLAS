"""Direct tests of the supplier risk score validation
(backend/app/decision_support/supplier_validation.py) — proving the
correlation-based sanity check actually catches a formula that doesn't
behave the way its own documentation claims (a real bug class: a sign
error or a weight applied to the wrong component), since there's no
forecast/ground-truth to backtest a risk score against the way Module A
backtests a forecast.
"""

from app.decision_support.supplier_scoring import SupplierMetrics, score_suppliers
from app.decision_support.supplier_validation import (
    assert_scores_behave_as_designed,
    validate_scores,
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


def _well_behaved_population():
    good = _metrics(
        "A",
        on_time_rate=1.0,
        quality_rejection_rate=0.0,
        lead_time_stddev_days=0.0,
        prior=1.0,
        recent=1.0,
    )
    mid = _metrics(
        "B",
        on_time_rate=0.8,
        quality_rejection_rate=0.05,
        lead_time_stddev_days=1.0,
        prior=0.9,
        recent=0.8,
    )
    bad = _metrics(
        "C",
        on_time_rate=0.5,
        quality_rejection_rate=0.1,
        lead_time_stddev_days=2.0,
        prior=1.0,
        recent=0.5,
    )
    return [good, mid, bad]


def test_validate_scores_computes_expected_correlation_signs_on_a_well_behaved_population():
    metrics = _well_behaved_population()
    results = score_suppliers(metrics)
    validation = validate_scores(metrics, results)

    assert validation.n_suppliers == 3
    assert validation.correlation_with_on_time_rate < 0  # higher on-time -> lower risk
    assert validation.correlation_with_quality_rejection_rate > 0
    assert validation.correlation_with_lead_time_stddev > 0
    assert validation.correlation_with_trend_delta > 0


def test_assert_scores_behave_as_designed_passes_for_the_real_formula():
    metrics = _well_behaved_population()
    results = score_suppliers(metrics)
    validation = validate_scores(metrics, results)

    assert assert_scores_behave_as_designed(validation) == []


def test_assert_scores_behave_as_designed_flags_a_sign_error():
    # Directly constructs a ValidationResult that mimics a formula bug
    # (a sign flipped) to prove the assertion actually fails loudly
    # rather than only ever passing on real, well-behaved output.
    from app.decision_support.supplier_validation import ValidationResult

    broken = ValidationResult(
        correlation_with_on_time_rate=0.5,  # wrong sign: should be negative
        correlation_with_quality_rejection_rate=0.5,
        correlation_with_lead_time_stddev=0.5,
        correlation_with_trend_delta=0.5,
        n_suppliers=3,
        n_low=1,
        n_medium=1,
        n_high=1,
    )
    problems = assert_scores_behave_as_designed(broken)
    assert len(problems) == 1
    assert "on_time_rate" in problems[0]
