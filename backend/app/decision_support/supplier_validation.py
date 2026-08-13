"""Validation for the supplier risk score (Phase 7 Module C). A risk
score has no future ground truth to backtest against the way a demand
forecast does (Module A) — there's no "actual risk that happened" to
compare a prediction to. The meaningful validation question instead is:
**does the formula actually behave the way its own documentation
claims?** If `risk_score` doesn't correlate negatively with
`on_time_rate` and positively with `quality_rejection_rate`, the
formula has a real bug (a sign error, a weight applied to the wrong
component) regardless of how principled the design looks on paper —
this is the check that would catch that.

Uses `statistics.correlation` (Python 3.10+ standard library, no numpy
needed — the score itself is deliberately not a numpy-computed formula
per Module A's/Module C's shared "no new dependency" discipline).
"""

from dataclasses import dataclass
from statistics import correlation

from app.decision_support.supplier_scoring import SupplierMetrics, SupplierRiskResult


@dataclass
class ValidationResult:
    correlation_with_on_time_rate: float
    correlation_with_quality_rejection_rate: float
    correlation_with_lead_time_stddev: float
    correlation_with_trend_delta: float
    n_suppliers: int
    n_low: int
    n_medium: int
    n_high: int


def validate_scores(
    metrics: list[SupplierMetrics], results: list[SupplierRiskResult]
) -> ValidationResult:
    scores = [r.risk_score for r in results]

    corr_on_time = correlation(scores, [m.on_time_rate for m in metrics])
    corr_quality = correlation(scores, [m.quality_rejection_rate for m in metrics])
    corr_variability = correlation(scores, [m.lead_time_stddev_days for m in metrics])
    corr_trend = correlation(scores, [r.on_time_rate_trend_delta for r in results])

    return ValidationResult(
        correlation_with_on_time_rate=round(corr_on_time, 4),
        correlation_with_quality_rejection_rate=round(corr_quality, 4),
        correlation_with_lead_time_stddev=round(corr_variability, 4),
        correlation_with_trend_delta=round(corr_trend, 4),
        n_suppliers=len(results),
        n_low=sum(1 for r in results if r.risk_classification == "Low"),
        n_medium=sum(1 for r in results if r.risk_classification == "Medium"),
        n_high=sum(1 for r in results if r.risk_classification == "High"),
    )


def assert_scores_behave_as_designed(validation: ValidationResult) -> list[str]:
    """Returns a list of problems found (empty = all sanity checks
    passed). Called by run_module_c.py, which refuses to persist scores
    that fail this — a formula that doesn't correlate the way its own
    documented intent says is a bug, not a result to publish."""

    problems = []
    if validation.correlation_with_on_time_rate >= 0:
        problems.append(
            f"risk_score should correlate NEGATIVELY with on_time_rate "
            f"(higher on-time = lower risk), got {validation.correlation_with_on_time_rate}"
        )
    if validation.correlation_with_quality_rejection_rate <= 0:
        problems.append(
            f"risk_score should correlate POSITIVELY with quality_rejection_rate, "
            f"got {validation.correlation_with_quality_rejection_rate}"
        )
    if validation.correlation_with_lead_time_stddev <= 0:
        problems.append(
            f"risk_score should correlate POSITIVELY with lead_time_stddev_days, "
            f"got {validation.correlation_with_lead_time_stddev}"
        )
    if validation.correlation_with_trend_delta <= 0:
        problems.append(
            f"risk_score should correlate POSITIVELY with on_time_rate_trend_delta "
            f"(a decline should raise risk), got {validation.correlation_with_trend_delta}"
        )
    return problems
