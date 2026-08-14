"""Direct tests of run_module_f.py's own grouping/assembly logic
(_build_right_sizing_recommendations, _build_consolidation_recommendations)
-- the formulas themselves (cheapest_sufficient_vehicle etc.) are
already unit-tested in test_route_cost_optimization_unit.py; this file
only proves the shipment-to-group assembly is correct.
"""

from datetime import date

from app.decision_support.route_cost_optimization import VehicleSpec
from app.decision_support.run_module_f import (
    _build_consolidation_recommendations,
    _build_right_sizing_recommendations,
)

VEHICLE_TYPES = {
    "VAN": VehicleSpec(capacity_units=500, cost_per_mile=1.10),
    "BOX_TRUCK": VehicleSpec(capacity_units=2000, cost_per_mile=1.75),
    "SEMI_TRAILER": VehicleSpec(capacity_units=10000, cost_per_mile=2.50),
}


def _shipment(**overrides) -> dict:
    defaults = dict(
        shipment_number="SHIP-1",
        origin_warehouse_key=1,
        destination_customer_key=100,
        ship_date=date(2021, 12, 5),
        distance_miles=100.0,
        vehicle_type_code="SEMI_TRAILER",
    )
    defaults.update(overrides)
    return defaults


def test_right_sizing_skips_shipments_with_no_order_line_quantity():
    shipments = [_shipment(shipment_number="SHIP-1")]
    recs = _build_right_sizing_recommendations(
        shipments, quantities={}, vehicle_types=VEHICLE_TYPES
    )
    assert recs == []


def test_right_sizing_produces_one_recommendation_per_oversized_shipment():
    shipments = [_shipment(shipment_number="SHIP-1", vehicle_type_code="SEMI_TRAILER")]
    quantities = {"SHIP-1": 100}
    recs = _build_right_sizing_recommendations(shipments, quantities, VEHICLE_TYPES)
    assert len(recs) == 1
    assert recs[0]["shipment_numbers"] == ["SHIP-1"]
    assert recs[0]["rec"].recommended_vehicle_type_code == "VAN"


def test_consolidation_groups_by_origin_destination_and_date():
    shipments = [
        _shipment(shipment_number="SHIP-1", ship_date=date(2021, 12, 5)),
        _shipment(shipment_number="SHIP-2", ship_date=date(2021, 12, 5)),
        # Different day -- must NOT be grouped with the above two.
        _shipment(shipment_number="SHIP-3", ship_date=date(2021, 12, 6)),
    ]
    quantities = {"SHIP-1": 100, "SHIP-2": 100, "SHIP-3": 100}
    recs = _build_consolidation_recommendations(shipments, quantities, VEHICLE_TYPES)
    assert len(recs) == 1  # only SHIP-1 + SHIP-2 form a group of >= 2
    assert set(recs[0]["shipment_numbers"]) == {"SHIP-1", "SHIP-2"}


def test_consolidation_skips_shipments_with_no_destination_customer():
    # A warehouse-to-warehouse transfer (destination_customer_key is
    # NULL) is not a consolidation candidate under this module's
    # (origin_warehouse, destination_customer, ship_date) grouping.
    shipments = [
        _shipment(shipment_number="SHIP-1", destination_customer_key=None),
        _shipment(shipment_number="SHIP-2", destination_customer_key=None),
    ]
    quantities = {"SHIP-1": 100, "SHIP-2": 100}
    recs = _build_consolidation_recommendations(shipments, quantities, VEHICLE_TYPES)
    assert recs == []


def test_consolidation_skips_singleton_groups():
    shipments = [_shipment(shipment_number="SHIP-1")]
    quantities = {"SHIP-1": 100}
    recs = _build_consolidation_recommendations(shipments, quantities, VEHICLE_TYPES)
    assert recs == []
