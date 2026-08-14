"""Inventory policy recommendation formulas (Phase 7 Module B): reorder
point, safety stock, and a service-level inventory target per (product,
warehouse) pair — classic, textbook continuous-review inventory theory
(Silver/Pyke/Peterson), not a fitted model (ADR-004, module brief's "no
machine-learning frameworks").

**EOQ is deliberately out of scope**, per explicit instruction: this
module answers "when to reorder and how much buffer to hold," never
"how much to order" — a genuinely separable question that needs
ordering-cost and holding-cost policy inputs this project has not
defined. Order quantity appears in this module's own validation
simulation only, clearly labeled as a simulation input, never
persisted or reported as a recommendation.

**The formula**: demand during lead time is uncertain for two
independent reasons — daily demand varies, and the lead time itself
varies. Combining both (Silver/Pyke/Peterson's standard formula, not
an invented one):

    sigma_dLT = sqrt(LT * sigma_d^2 + d_bar^2 * sigma_LT^2)
    safety_stock = Z * sigma_dLT
    reorder_point = d_bar * LT + safety_stock

`Z` is the standard-normal inverse CDF at the target service level
(`statistics.NormalDist().inv_cdf`, Python 3.8+ stdlib — no lookup
table, no numpy/scipy).

`d_bar`/`sigma_d` come from Module A's forecast (already-validated,
frozen baseline). `LT`/`sigma_LT` come from the resolved primary
supplier: `LT` is `dim_supplier.default_lead_time_days` adjusted by
Module C's own `avg_lead_time_variance_days` (suppliers average
slightly *later* than their quoted lead time — confirmed directly
against real delivery data, not assumed), `sigma_LT` is Module C's
`lead_time_stddev_days` directly.
"""

from dataclasses import dataclass
from statistics import NormalDist

DEFAULT_TARGET_SERVICE_LEVEL = 0.95
SENSITIVITY_TARGET_SERVICE_LEVELS = [0.90, 0.95, 0.99]

# A pair sitting on more than this many multiples of its own reorder
# point is flagged as excess — a fixed, disclosed classification bar,
# not a statistical prediction requiring calibration. Grounded in the
# pair's own ROP (which is itself demand/lead-time grounded), so it
# scales sensibly per pair rather than using one global unit count.
EXCESS_INVENTORY_MULTIPLIER = 3.0

# Confidence bands: data-sufficiency, not calibration -- how much
# history backs this row's demand/lead-time estimates. Same thresholds
# Modules A/C/D already established for the same underlying signals.
HIGH_CONFIDENCE_ACTIVE_DAYS = 90
HIGH_CONFIDENCE_N_DELIVERIES = 30


@dataclass
class PolicyRecommendation:
    safety_stock: float
    reorder_point: float
    service_level_inventory_target: float
    balancing_recommendation: str
    confidence: str
    contributing_factors: dict
    business_rationale: str


def compute_z_score(target_service_level: float) -> float:
    return NormalDist().inv_cdf(target_service_level)


def compute_policy_recommendation(
    product_key: int,
    warehouse_key: int,
    avg_daily_demand: float,
    demand_stddev: float,
    lead_time_days: float,
    lead_time_stddev_days: float,
    current_available_quantity: float,
    primary_supplier_key: int | None,
    active_days: int,
    n_deliveries: int,
    target_service_level: float = DEFAULT_TARGET_SERVICE_LEVEL,
) -> PolicyRecommendation:
    z = compute_z_score(target_service_level)

    sigma_dLT = (
        lead_time_days * demand_stddev**2 + avg_daily_demand**2 * lead_time_stddev_days**2
    ) ** 0.5
    safety_stock = z * sigma_dLT
    reorder_point = avg_daily_demand * lead_time_days + safety_stock
    service_level_inventory_target = reorder_point

    if current_available_quantity < reorder_point:
        balancing = "reorder_now"
    elif current_available_quantity > reorder_point * EXCESS_INVENTORY_MULTIPLIER:
        balancing = "excess_inventory"
    else:
        balancing = "adequate"

    demand_confidence_ok = active_days >= HIGH_CONFIDENCE_ACTIVE_DAYS
    supplier_confidence_ok = n_deliveries >= HIGH_CONFIDENCE_N_DELIVERIES
    confidence = "high" if (demand_confidence_ok and supplier_confidence_ok) else "medium"

    supplier_phrase = (
        f"supplier #{primary_supplier_key}" if primary_supplier_key else "an unresolved supplier"
    )
    if balancing == "reorder_now":
        status_phrase = "below the reorder point — reorder now."
    elif balancing == "excess_inventory":
        status_phrase = (
            f"more than {EXCESS_INVENTORY_MULTIPLIER:g}x the reorder point — consider reducing."
        )
    else:
        status_phrase = "within the adequate range."

    rationale = (
        f"Average daily demand of {avg_daily_demand:.1f} units and a "
        f"{lead_time_days:.1f}-day lead time from {supplier_phrase} "
        f"(±{lead_time_stddev_days:.2f} days variability) imply a safety stock of "
        f"{safety_stock:.0f} units and a reorder point of {reorder_point:.0f} units to sustain a "
        f"{target_service_level:.0%} service level. Current available inventory "
        f"({current_available_quantity:.0f}) is {status_phrase}"
    )

    return PolicyRecommendation(
        safety_stock=round(safety_stock, 2),
        reorder_point=round(reorder_point, 2),
        service_level_inventory_target=round(service_level_inventory_target, 2),
        balancing_recommendation=balancing,
        confidence=confidence,
        contributing_factors={
            "avg_daily_demand": round(avg_daily_demand, 4),
            "demand_stddev": round(demand_stddev, 4),
            "lead_time_days": round(lead_time_days, 2),
            "lead_time_stddev_days": round(lead_time_stddev_days, 4),
            "target_service_level": target_service_level,
            "z_score": round(z, 4),
            "current_available_quantity": current_available_quantity,
            "primary_supplier_key": primary_supplier_key,
            "active_days": active_days,
            "n_deliveries": n_deliveries,
        },
        business_rationale=rationale,
    )
