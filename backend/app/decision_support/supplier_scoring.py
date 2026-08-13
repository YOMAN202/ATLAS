"""Supplier risk scoring (Phase 7 Module C). A composite 0-100 score
built from four named, weighted components — never a fitted classifier,
per ADR-004/SRS §17's "no black-box outputs, all outputs must be
rule/statistics-based and explainable."

**Why every component is min-max normalized before weighting**: the raw
metrics have very different natural scales in this dataset — on-time
rate spans ~87-96% (a ~9-point range), quality rejection spans ~1.6-2.3%
(a ~0.65-point range), while lead-time stddev spans 0.59-1.11 days. If
the stated weights (0.35/0.30/0.20/0.15) were applied directly to these
raw ranges, quality's contribution to the score would be swamped by
variability's, regardless of the stated weight, purely because of unit
scale — an easy, real mistake to make and a subtle way for a
"documented, explainable" formula to secretly not do what its own
documentation claims. Normalizing every component to its own
observed 0-100 range first means the stated weights are what actually
control the score.

**Why fill_rate is not a scoring input**: `received_quantity /
ordered_quantity` is exactly 1.0000 for every one of the 100 suppliers
(zero variance, confirmed directly against v_supplier_delivery_stats) —
a genuine characteristic of this dataset (fact_supplier_delivery only
contains lines that were actually delivered, and this simulation
doesn't model partial shipments). A constant contributes nothing to a
weighted score; including it anyway would be decorative, not
explainable. It's still reported on every output row (the "fulfillment
performance" the module objective names), just not scored.
"""

import json
from dataclasses import dataclass

WEIGHT_ON_TIME = 0.35
WEIGHT_QUALITY = 0.30
WEIGHT_VARIABILITY = 0.20
WEIGHT_TREND = 0.15

ON_TIME_RATE_ALERT_THRESHOLD = 0.85
QUALITY_REJECTION_ALERT_THRESHOLD = 0.02
TREND_DECLINE_ALERT_THRESHOLD = 0.05  # a 5-point on-time-rate drop, prior vs. recent 90 days

RISK_LOW_MAX = 33.0
RISK_MEDIUM_MAX = 66.0

SCORING_PARAMETERS = {
    "weights": {
        "on_time": WEIGHT_ON_TIME,
        "quality": WEIGHT_QUALITY,
        "variability": WEIGHT_VARIABILITY,
        "trend": WEIGHT_TREND,
    },
    "alert_thresholds": {
        "on_time_rate_below": ON_TIME_RATE_ALERT_THRESHOLD,
        "quality_rejection_rate_above": QUALITY_REJECTION_ALERT_THRESHOLD,
        "on_time_rate_decline_above": TREND_DECLINE_ALERT_THRESHOLD,
    },
    "classification_bands": {"low_max": RISK_LOW_MAX, "medium_max": RISK_MEDIUM_MAX},
}


@dataclass
class SupplierMetrics:
    supplier_key: int
    n_deliveries: int
    on_time_rate: float
    quality_rejection_rate: float
    fill_rate: float
    avg_lead_time_variance_days: float
    lead_time_stddev_days: float
    recent_on_time_rate: float | None
    prior_on_time_rate: float | None
    total_spend: float
    share_of_total_spend: float
    distinct_products_supplied: int
    distinct_warehouses_served: int


@dataclass
class SupplierRiskResult:
    supplier_key: int
    risk_score: float
    risk_classification: str
    on_time_rate_trend_delta: float
    trend_direction: str
    triggering_metrics: list[str]


def _minmax_normalize(value: float, low: float, high: float) -> float:
    if high == low:
        return 0.0  # a population-wide constant contributes nothing, not a divide-by-zero
    return max(0.0, min(1.0, (value - low) / (high - low))) * 100


def score_suppliers(metrics: list[SupplierMetrics]) -> list[SupplierRiskResult]:
    """Scores the whole supplier population together (not one at a
    time) because normalization is population-relative by design — a
    supplier's variability risk is "how variable relative to every
    other supplier this run saw," not an absolute constant."""

    on_time_risks = [1 - m.on_time_rate for m in metrics]
    quality_risks = [m.quality_rejection_rate for m in metrics]
    variability_risks = [m.lead_time_stddev_days for m in metrics]
    # Signed: positive = declined, negative = improved — the real,
    # explainable number reported on every output row. The *scoring*
    # input is a separate, floored copy (below): only a decline should
    # ever raise risk, but the reported delta must show real
    # improvement as negative, not silently clamp it to 0.
    signed_trend_deltas = [
        (m.prior_on_time_rate or 0.0) - (m.recent_on_time_rate or 0.0) for m in metrics
    ]
    trend_deltas = [max(0.0, d) for d in signed_trend_deltas]

    ot_low, ot_high = min(on_time_risks), max(on_time_risks)
    q_low, q_high = min(quality_risks), max(quality_risks)
    v_low, v_high = min(variability_risks), max(variability_risks)
    t_low, t_high = min(trend_deltas), max(trend_deltas)

    results = []
    for m, ot_raw, q_raw, v_raw, t_raw, t_signed in zip(
        metrics,
        on_time_risks,
        quality_risks,
        variability_risks,
        trend_deltas,
        signed_trend_deltas,
        strict=True,
    ):
        on_time_component = _minmax_normalize(ot_raw, ot_low, ot_high)
        quality_component = _minmax_normalize(q_raw, q_low, q_high)
        variability_component = _minmax_normalize(v_raw, v_low, v_high)
        trend_component = _minmax_normalize(t_raw, t_low, t_high)

        risk_score = (
            WEIGHT_ON_TIME * on_time_component
            + WEIGHT_QUALITY * quality_component
            + WEIGHT_VARIABILITY * variability_component
            + WEIGHT_TREND * trend_component
        )

        if risk_score <= RISK_LOW_MAX:
            classification = "Low"
        elif risk_score <= RISK_MEDIUM_MAX:
            classification = "Medium"
        else:
            classification = "High"

        if t_signed > TREND_DECLINE_ALERT_THRESHOLD:
            trend_direction = "degrading"
        elif t_signed < -TREND_DECLINE_ALERT_THRESHOLD:
            trend_direction = "improving"
        else:
            trend_direction = "stable"

        triggering: list[str] = []
        if m.on_time_rate < ON_TIME_RATE_ALERT_THRESHOLD:
            triggering.append(
                f"on_time_rate {m.on_time_rate:.1%} below "
                f"{ON_TIME_RATE_ALERT_THRESHOLD:.0%} threshold"
            )
        if m.quality_rejection_rate > QUALITY_REJECTION_ALERT_THRESHOLD:
            triggering.append(
                f"quality_rejection_rate {m.quality_rejection_rate:.2%} above "
                f"{QUALITY_REJECTION_ALERT_THRESHOLD:.0%} threshold"
            )
        if t_raw > TREND_DECLINE_ALERT_THRESHOLD:
            triggering.append(f"on-time rate declined {t_raw:.1%} (prior 90d vs. most recent 90d)")
        if variability_component >= 66.0:
            triggering.append("lead-time variability in the top third of all suppliers")

        results.append(
            SupplierRiskResult(
                supplier_key=m.supplier_key,
                risk_score=round(risk_score, 2),
                risk_classification=classification,
                on_time_rate_trend_delta=round(t_signed, 4),
                trend_direction=trend_direction,
                triggering_metrics=triggering,
            )
        )
    return results


def triggering_metrics_json(result: SupplierRiskResult) -> str:
    return json.dumps(result.triggering_metrics)
