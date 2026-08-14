"""Direct tests of the route/cost optimization formulas
(backend/app/decision_support/route_cost_optimization.py) with hand-
computable exact values, grounded in the real dim_carrier vehicle
economics (VAN $1.10/mi cap 500, BOX_TRUCK $1.75/mi cap 2000,
SEMI_TRAILER $2.50/mi cap 10000 -- confirmed directly against the
warehouse, docs/phase7-2-architecture.md §2.1).
"""

from app.decision_support.route_cost_optimization import (
    VehicleSpec,
    cheapest_sufficient_vehicle,
    compute_consolidation_recommendation,
    compute_right_sizing_recommendation,
)

VEHICLE_TYPES = {
    "VAN": VehicleSpec(capacity_units=500, cost_per_mile=1.10),
    "BOX_TRUCK": VehicleSpec(capacity_units=2000, cost_per_mile=1.75),
    "SEMI_TRAILER": VehicleSpec(capacity_units=10000, cost_per_mile=2.50),
}


def test_cheapest_sufficient_vehicle_picks_the_smallest_adequate_type():
    assert cheapest_sufficient_vehicle(300, VEHICLE_TYPES) == "VAN"
    assert cheapest_sufficient_vehicle(600, VEHICLE_TYPES) == "BOX_TRUCK"
    assert cheapest_sufficient_vehicle(5000, VEHICLE_TYPES) == "SEMI_TRAILER"


def test_cheapest_sufficient_vehicle_falls_back_to_largest_when_none_fit():
    # 15,000 units exceeds even a SEMI_TRAILER's 10,000 capacity.
    assert cheapest_sufficient_vehicle(15000, VEHICLE_TYPES) == "SEMI_TRAILER"


def test_right_sizing_recommends_a_cheaper_vehicle_with_exact_savings():
    rec = compute_right_sizing_recommendation(
        total_quantity=300,
        distance_miles=100,
        current_vehicle_type_code="SEMI_TRAILER",
        vehicle_types=VEHICLE_TYPES,
    )
    assert rec is not None
    assert rec.current_total_cost == 250.0  # 2.50 * 100
    assert rec.recommended_vehicle_type_code == "VAN"
    assert rec.recommended_total_cost == 110.0  # 1.10 * 100
    assert rec.estimated_savings == 140.0
    assert rec.contributing_factors["service_level_impact"] == (
        "none -- transit time does not vary by vehicle type"
    )


def test_right_sizing_returns_none_when_already_on_cheapest_sufficient_vehicle():
    rec = compute_right_sizing_recommendation(
        total_quantity=300,
        distance_miles=100,
        current_vehicle_type_code="VAN",
        vehicle_types=VEHICLE_TYPES,
    )
    assert rec is None


def test_consolidation_combines_shipments_with_exact_savings():
    rec = compute_consolidation_recommendation(
        quantities=[100, 150, 200],
        distances=[50, 60, 70],
        current_vehicle_type_codes=["VAN", "VAN", "VAN"],
        vehicle_types=VEHICLE_TYPES,
    )
    assert rec is not None
    assert rec.total_quantity == 450
    assert rec.avg_distance_miles == 60.0  # (50+60+70)/3
    assert rec.current_total_cost == 198.0  # 1.10 * (50+60+70)
    assert rec.recommended_vehicle_type_code == "VAN"  # 450 <= 500
    assert rec.recommended_total_cost == 66.0  # 1.10 * 60
    assert rec.estimated_savings == 132.0
    assert rec.confidence == "high"  # n_shipments = 3


def test_consolidation_returns_none_when_it_would_not_actually_save_money():
    # Forcing a jump from VAN-scale quantities to a SEMI_TRAILER
    # (2.50/mi, more than double a VAN's 1.10/mi) on equal distances
    # costs more as one big trip than as two small VAN trips --
    # consolidating doesn't always save money, and this formula must
    # not recommend it when it doesn't.
    rec = compute_consolidation_recommendation(
        quantities=[1200, 1200],
        distances=[10, 10],
        current_vehicle_type_codes=["VAN", "VAN"],
        vehicle_types=VEHICLE_TYPES,
    )
    assert rec is None


def test_consolidation_of_two_shipments_has_medium_confidence():
    rec = compute_consolidation_recommendation(
        quantities=[100, 150],
        distances=[50, 50],
        current_vehicle_type_codes=["VAN", "VAN"],
        vehicle_types=VEHICLE_TYPES,
    )
    assert rec is not None
    assert rec.confidence == "medium"  # n_shipments = 2
