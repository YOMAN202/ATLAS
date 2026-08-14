"""Route and cost optimization formulas (Phase 7.2 Module F): vehicle
right-sizing and shipment consolidation — closed-form, deterministic
heuristics over real carrier and shipment data, no external
optimization engine (no scipy.optimize, no OR-tools, no LP/IP solver),
per explicit instruction.

**Why "carrier selection" and "route efficiency" collapse into
right-sizing, not two separate axes.** Real data grounding
(docs/phase7-2-architecture.md §2.1): `dim_carrier.vehicle_cost_per_mile`
is determined ENTIRELY by `vehicle_type_code` — every carrier of the
same type charges the identical rate (VAN=$1.10/mi x 9 carriers,
BOX_TRUCK=$1.75/mi x 8, SEMI_TRAILER=$2.50/mi x 8), and transit time is
statistically indistinguishable both across carriers of the same type
and across vehicle types themselves (VAN 3.3821, BOX_TRUCK 3.3818,
SEMI_TRAILER 3.3829 days on average). "Which of the 9 VAN carriers"
and "which route" are genuinely degenerate optimization axes in this
dataset — the same category of finding as Module C's zero-variance
`fill_rate` and Module D's near-constant `transit_days`. The one real,
actionable lever left in `dim_carrier` is *vehicle type* itself, so
this module is built around that.

**Vehicle right-sizing**: for a single shipment, is the cheapest
vehicle type with sufficient capacity actually being used? Because
transit time doesn't vary by vehicle type (confirmed above), a
right-sizing recommendation has **provable zero service-level
impact** — switching vehicle type changes cost, never delivery timing.

**Shipment consolidation**: shipments sharing the same (origin
warehouse, destination customer, ship date) are real candidates to
combine into one trip. `distance_miles` is NOT a fixed lane property
in this dataset — it varies even for the same (origin, destination)
pair (up to 45 distinct values for one pair, confirmed directly) — so
a consolidation's estimated cost uses the *average* `distance_miles`
across the group, disclosed here as an approximation, not assumed
fixed.
"""

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class VehicleSpec:
    capacity_units: int
    cost_per_mile: float


@dataclass
class RightSizingRecommendation:
    current_total_cost: float
    recommended_vehicle_type_code: str
    recommended_total_cost: float
    estimated_savings: float
    confidence: str
    contributing_factors: dict
    business_rationale: str


@dataclass
class ConsolidationRecommendation:
    total_quantity: int
    avg_distance_miles: float
    current_total_cost: float
    recommended_vehicle_type_code: str
    recommended_total_cost: float
    estimated_savings: float
    confidence: str
    contributing_factors: dict
    business_rationale: str


def cheapest_sufficient_vehicle(quantity: float, vehicle_types: dict[str, VehicleSpec]) -> str:
    """The lowest-cost-per-mile vehicle type whose capacity can hold
    `quantity`. Ties (none exist in the real data — capacities are
    distinct per type) broken by capacity ascending, so the smallest
    sufficient vehicle wins. If no single vehicle type has enough
    capacity, the largest-capacity type is returned (a real shipment
    exceeding even a SEMI_TRAILER's capacity is a data question, not
    this formula's to resolve)."""
    sufficient = [
        (code, spec) for code, spec in vehicle_types.items() if spec.capacity_units >= quantity
    ]
    if sufficient:
        return min(sufficient, key=lambda item: (item[1].cost_per_mile, item[1].capacity_units))[0]
    return max(vehicle_types.items(), key=lambda item: item[1].capacity_units)[0]


def compute_right_sizing_recommendation(
    total_quantity: float,
    distance_miles: float,
    current_vehicle_type_code: str,
    vehicle_types: dict[str, VehicleSpec],
) -> RightSizingRecommendation | None:
    """Returns None when the shipment is already on the cheapest
    sufficient vehicle type -- no recommendation needed, not a zero-
    savings recommendation."""
    current_spec = vehicle_types[current_vehicle_type_code]
    current_total_cost = current_spec.cost_per_mile * distance_miles

    recommended_type = cheapest_sufficient_vehicle(total_quantity, vehicle_types)
    if recommended_type == current_vehicle_type_code:
        return None

    recommended_spec = vehicle_types[recommended_type]
    recommended_total_cost = recommended_spec.cost_per_mile * distance_miles
    savings = current_total_cost - recommended_total_cost
    if savings <= 0:
        return None

    return RightSizingRecommendation(
        current_total_cost=round(current_total_cost, 2),
        recommended_vehicle_type_code=recommended_type,
        recommended_total_cost=round(recommended_total_cost, 2),
        estimated_savings=round(savings, 2),
        confidence="high",
        contributing_factors={
            "total_quantity": total_quantity,
            "distance_miles": distance_miles,
            "current_vehicle_type_code": current_vehicle_type_code,
            "current_vehicle_capacity_units": current_spec.capacity_units,
            "recommended_vehicle_capacity_units": recommended_spec.capacity_units,
            "service_level_impact": "none -- transit time does not vary by vehicle type",
        },
        business_rationale=(
            f"This shipment of {total_quantity:.0f} units used a {current_vehicle_type_code} "
            f"(capacity {current_spec.capacity_units}), but a {recommended_type} "
            f"(capacity {recommended_spec.capacity_units}) has sufficient capacity at a lower "
            f"per-mile rate (${recommended_spec.cost_per_mile:.2f} vs. "
            f"${current_spec.cost_per_mile:.2f}), saving an estimated ${savings:.2f} with no "
            "change to delivery timing."
        ),
    )


def compute_consolidation_recommendation(
    quantities: list[float],
    distances: list[float],
    current_vehicle_type_codes: list[str],
    vehicle_types: dict[str, VehicleSpec],
) -> ConsolidationRecommendation | None:
    """Returns None when consolidating would not actually save money
    (e.g. the group's total quantity forces a vehicle type expensive
    enough to erase the trip-count reduction's benefit)."""
    total_quantity = sum(quantities)
    avg_distance = mean(distances)
    current_total_cost = sum(
        vehicle_types[vt].cost_per_mile * dist
        for vt, dist in zip(current_vehicle_type_codes, distances, strict=True)
    )

    recommended_type = cheapest_sufficient_vehicle(total_quantity, vehicle_types)
    recommended_spec = vehicle_types[recommended_type]
    recommended_total_cost = recommended_spec.cost_per_mile * avg_distance
    savings = current_total_cost - recommended_total_cost
    if savings <= 0:
        return None

    n_shipments = len(quantities)
    confidence = "high" if n_shipments >= 3 else "medium"

    return ConsolidationRecommendation(
        total_quantity=round(total_quantity),
        avg_distance_miles=round(avg_distance, 2),
        current_total_cost=round(current_total_cost, 2),
        recommended_vehicle_type_code=recommended_type,
        recommended_total_cost=round(recommended_total_cost, 2),
        estimated_savings=round(savings, 2),
        confidence=confidence,
        contributing_factors={
            "n_shipments_consolidated": n_shipments,
            "total_quantity": total_quantity,
            "avg_distance_miles": round(avg_distance, 2),
            "distance_miles_is_averaged_not_fixed": True,
            "current_vehicle_type_codes": current_vehicle_type_codes,
        },
        business_rationale=(
            f"{n_shipments} shipments to the same destination on the same day "
            f"(totaling {total_quantity:.0f} units) could combine into one "
            f"{recommended_type} trip instead of {n_shipments} separate trips, saving an "
            f"estimated ${savings:.2f} (avg. distance {avg_distance:.1f} miles)."
        ),
    )
