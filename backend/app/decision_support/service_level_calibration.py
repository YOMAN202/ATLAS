"""Calibration analysis for Module D's three predictions. Unlike Module
A (forecast a number, compare to the real number that happened) or
Module C (does the formula correlate the direction its own design
claims), a probability has a different, standard validation question:
**if the model says 70%, does the thing actually happen about 70% of
the time?** That's calibration, not accuracy — a model that always
predicts the population base rate can be "accurate" in aggregate while
being useless per-row; a well-calibrated model's predicted deciles
should track observed outcome rates.

Every (predicted_probability, actual_outcome) pair here comes from a
walk-forward split: predictions computed using only data up to a
cutoff date, actual_outcome observed from what really happened in the
real, already-elapsed window immediately after that cutoff — the same
train/test discipline `evaluation.py::backtest` already uses for
Module A, applied to probabilities instead of point forecasts.
actual_outcome is either a strict 0/1 (did a stockout day occur at
all) or a continuous rate in [0, 1] (fraction of order lines/deliveries
that were backordered/late) depending on what ground truth naturally
supports — both are valid Brier-score/calibration targets.
"""

from dataclasses import dataclass

N_CALIBRATION_BUCKETS = 10


@dataclass
class CalibrationBucket:
    bucket_index: int
    predicted_probability_mean: float
    actual_outcome_rate: float
    n_observations: int


def brier_score(pairs: list[tuple[float, float]]) -> float:
    """Mean squared error between predicted probability and actual
    outcome — the standard scalar calibration/accuracy metric for
    probabilistic predictions (Brier, 1950). 0 is a perfect model; 0.25
    is what "always predict 50%" scores against a 50/50 outcome; lower
    is better, same direction as Module A's MAPE.
    """
    if not pairs:
        raise ValueError("brier_score requires at least one (predicted, actual) pair")
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs)


def naive_baseline_brier_score(pairs: list[tuple[float, float]], population_rate: float) -> float:
    """The Brier score of the simplest possible competing model:
    predict one fixed rate for every row, ignoring every per-entity
    input. A real model earns its complexity only by beating this —
    the same "must beat a naive baseline" discipline Module A applies
    against seasonal_naive.

    **`population_rate` must come from training-period data (the same
    cutoff-bounded query every prediction itself uses), never derived
    from `pairs`' own actual outcomes.** An earlier version computed it
    as `mean(a for _, a in pairs)` — the test window's own realized
    rate. That's an oracle, not a naive baseline: it already knows the
    answer the model is being asked to predict, and by construction
    minimizes squared error against that exact set of outcomes, so
    nothing computed from training data alone can ever beat it on
    principle, not merely in practice. Found and fixed after
    fulfillment-delay predictions (where genuine per-supplier signal
    turned out to be very weak, so the honest choice was close to a
    flat rate) failed to "beat baseline" even at their theoretical
    best — the gate itself, not the model, was unfair. Stockout's and
    backorder's already-validated results are unaffected by this fix:
    both beat even the stricter oracle version, so they beat this
    fairer one too.
    """
    return sum((population_rate - a) ** 2 for _, a in pairs) / len(pairs)


def calibration_buckets(
    pairs: list[tuple[float, float]], n_buckets: int = N_CALIBRATION_BUCKETS
) -> list[CalibrationBucket]:
    """Quantile (equal-count) bucketing, not equal-width probability
    bands: predicted probabilities in this domain cluster heavily at
    the low end (most product/warehouse pairs are not about to stock
    out), so fixed 0-10%/10-20%/... bands would leave several buckets
    nearly empty and statistically meaningless. Sorting and splitting
    into equal-sized groups keeps every bucket's actual_outcome_rate
    backed by a comparable, non-trivial sample size.
    """
    if not pairs:
        return []
    ordered = sorted(pairs, key=lambda pair: pair[0])
    n = len(ordered)
    buckets = []
    for i in range(n_buckets):
        start = (i * n) // n_buckets
        end = ((i + 1) * n) // n_buckets
        chunk = ordered[start:end]
        if not chunk:
            continue
        buckets.append(
            CalibrationBucket(
                bucket_index=i,
                predicted_probability_mean=round(sum(p for p, _ in chunk) / len(chunk), 5),
                actual_outcome_rate=round(sum(a for _, a in chunk) / len(chunk), 5),
                n_observations=len(chunk),
            )
        )
    return buckets
