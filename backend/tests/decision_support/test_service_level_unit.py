"""Direct tests of the service-level prediction formulas
(backend/app/decision_support/service_level.py) against hand-
computable expected values — the same discipline
test_models_unit.py/test_supplier_scoring_unit.py use: every formula
must be independently verifiable by hand, not just "runs without
error" (ADR-004, "no black-box outputs").
"""

from app.decision_support.service_level import (
    compute_backorder_probability,
    compute_fulfillment_delay_probability,
    compute_stockout_probability,
)


def test_stockout_probability_is_certain_when_already_out_of_stock():
    # available_quantity <= 0 is a deterministic override -> 1.0
    # regardless of how favorable the historical rate otherwise looks.
    result = compute_stockout_probability(
        available_quantity=0,
        n_historical_days=300,
        n_historical_stockout_days=0,
        population_stockout_rate=0.01,
        historical_min_available_on_safe_days=50,
        forecasted_demand_mean=0,
        forecasted_demand_stddev=0,
        active_days=40,
    )
    assert result.probability == 1.0
    assert result.confidence == "medium"  # active_days < 90


def test_stockout_probability_matches_hand_computed_shrunk_rate():
    # Empirical-Bayes shrinkage toward the population rate:
    # (2 + 0.01 * 60) / (100 + 60) = 2.6 / 160 = 0.01625
    # available_quantity is above the historical safe minimum, so no bump applies.
    result = compute_stockout_probability(
        available_quantity=80,
        n_historical_days=100,
        n_historical_stockout_days=2,
        population_stockout_rate=0.01,
        historical_min_available_on_safe_days=50,
        forecasted_demand_mean=42,
        forecasted_demand_stddev=6,
        active_days=100,
    )
    assert result.probability == 0.01625


def test_stockout_probability_anomaly_bump_when_below_historical_safe_minimum():
    # Same shrunk base rate as above (0.01625), but available_quantity
    # (10) is below historical_min_available_on_safe_days (50) ->
    # 0.01625 + 0.5 (STOCKOUT_ANOMALY_BUMP) = 0.51625
    result = compute_stockout_probability(
        available_quantity=10,
        n_historical_days=100,
        n_historical_stockout_days=2,
        population_stockout_rate=0.01,
        historical_min_available_on_safe_days=50,
        forecasted_demand_mean=42,
        forecasted_demand_stddev=6,
        active_days=100,
    )
    assert result.probability == 0.51625


def test_stockout_probability_bump_is_capped_at_one():
    result = compute_stockout_probability(
        available_quantity=5,
        n_historical_days=100,
        n_historical_stockout_days=100,  # base_rate already 1.0
        population_stockout_rate=1.0,
        historical_min_available_on_safe_days=50,
        forecasted_demand_mean=10,
        forecasted_demand_stddev=2,
        active_days=100,
    )
    assert result.probability == 1.0


def test_stockout_probability_skips_bump_when_no_safe_day_history_exists():
    # historical_min_available_on_safe_days=None (the pair has never
    # avoided a stockout) must not raise or fabricate a comparison.
    result = compute_stockout_probability(
        available_quantity=1,
        n_historical_days=50,
        n_historical_stockout_days=5,
        population_stockout_rate=0.01,
        historical_min_available_on_safe_days=None,
        forecasted_demand_mean=10,
        forecasted_demand_stddev=2,
        active_days=50,
    )
    # (5 + 0.01*60) / (50+60) = 5.6/110 = 0.050909...
    assert result.probability == round(5.6 / 110, 5)


def test_stockout_probability_contributing_factors_are_traceable():
    result = compute_stockout_probability(
        available_quantity=80,
        n_historical_days=100,
        n_historical_stockout_days=2,
        population_stockout_rate=0.01,
        historical_min_available_on_safe_days=50,
        forecasted_demand_mean=42,
        forecasted_demand_stddev=6,
        active_days=100,
    )
    assert result.contributing_factors["available_quantity"] == 80
    assert result.contributing_factors["n_historical_days"] == 100
    assert result.contributing_factors["horizon_days"] == 30


def test_backorder_probability_matches_hand_computed_laplace_rate():
    # Laplace-smoothed historical rate: (2 backordered + 1) / (8 total + 2) = 0.3
    # stockout_probability is accepted and reported but does not drive
    # the number (see compute_backorder_probability's own docstring for
    # the real, disclosed reason).
    result = compute_backorder_probability(
        stockout_probability=0.5, n_historical_lines=8, n_historical_backordered_lines=2
    )
    assert result.probability == 0.3
    assert result.contributing_factors["historical_backorder_rate"] == 0.3
    assert result.contributing_factors["stockout_probability_reported_context_only"] == 0.5
    assert result.confidence == "low"  # n_historical_lines (8) < 20


def test_backorder_probability_confidence_bands():
    high = compute_backorder_probability(
        0.1, n_historical_lines=150, n_historical_backordered_lines=5
    )
    medium = compute_backorder_probability(
        0.1, n_historical_lines=50, n_historical_backordered_lines=5
    )
    low = compute_backorder_probability(0.1, n_historical_lines=5, n_historical_backordered_lines=1)
    assert high.confidence == "high"
    assert medium.confidence == "medium"
    assert low.confidence == "low"


def test_backorder_probability_laplace_smoothing_avoids_brittle_zero_or_one():
    # Zero historical backorders out of a handful of lines should not
    # report a hard 0% rate -- Laplace smoothing pulls it toward 0.5.
    result = compute_backorder_probability(
        stockout_probability=0.0, n_historical_lines=2, n_historical_backordered_lines=0
    )
    assert result.contributing_factors["historical_backorder_rate"] == 0.25  # (0+1)/(2+2)


def test_fulfillment_delay_probability_matches_hand_computed_shrunk_rate():
    # (2 late + 0.05 * 100) / (10 + 100) = 7 / 110 = 0.06364 (rounded)
    result = compute_fulfillment_delay_probability(
        supplier_key=1,
        n_deliveries=10,
        n_late_deliveries=2,
        population_late_rate=0.05,
        mean_lead_time_variance_days=1.0,
        stddev_lead_time_variance_days=1.0,
    )
    assert result is not None
    assert result.probability == round(7 / 110, 5)
    assert result.confidence == "medium"  # n_deliveries (10) < 30


def test_fulfillment_delay_probability_excluded_below_minimum_deliveries():
    result = compute_fulfillment_delay_probability(
        supplier_key=1,
        n_deliveries=4,
        n_late_deliveries=1,
        population_late_rate=0.05,
        mean_lead_time_variance_days=5.0,
        stddev_lead_time_variance_days=1.0,
    )
    assert result is None


def test_fulfillment_delay_probability_shrinkage_pulls_toward_population_rate():
    # zero observed late deliveries still gets pulled up toward the
    # population rate, rather than reporting a brittle 0.0 -- the same
    # shrinkage discipline as stockout's empirical-Bayes base rate.
    # (0 + 0.1 * 100) / (10 + 100) = 10 / 110 = 0.09091
    result = compute_fulfillment_delay_probability(
        supplier_key=1,
        n_deliveries=10,
        n_late_deliveries=0,
        population_late_rate=0.1,
        mean_lead_time_variance_days=0.0,
        stddev_lead_time_variance_days=0.0,
    )
    assert result is not None
    assert result.probability == round(10 / 110, 5)


def test_fulfillment_delay_probability_reports_variability_as_context_only():
    result = compute_fulfillment_delay_probability(
        supplier_key=1,
        n_deliveries=10,
        n_late_deliveries=2,
        population_late_rate=0.05,
        mean_lead_time_variance_days=0.2,
        stddev_lead_time_variance_days=0.9,
    )
    assert result is not None
    assert result.contributing_factors["mean_lead_time_variance_days_reported_context_only"] == 0.2
    assert (
        result.contributing_factors["stddev_lead_time_variance_days_reported_context_only"] == 0.9
    )


def test_fulfillment_delay_probability_high_confidence_band():
    result = compute_fulfillment_delay_probability(
        supplier_key=1,
        n_deliveries=35,
        n_late_deliveries=2,
        population_late_rate=0.05,
        mean_lead_time_variance_days=0.2,
        stddev_lead_time_variance_days=0.9,
    )
    assert result is not None
    assert result.confidence == "high"
