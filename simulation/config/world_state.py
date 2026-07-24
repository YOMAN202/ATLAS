"""World-state and generator configuration — every tunable simulation
parameter lives here, not scattered through generator code (implementation
requirement: configuration is separate from simulation logic).

Counts default to the TDD §10 target volumes where the frozen documents
specify a number (warehouses, SKUs, suppliers). Everything else (customer/
carrier counts, demand rates, distribution parameters) has no
frozen-document mandate — these are documented, adjustable constants,
tuned from the Phase 3 validation-run realism check, not guessed twice.

This is the "scenario/config file for initial world-state" TDD §5 names
as Phase 2 Scenario Analysis's designated future extension point. Per the
Master Prompt §2 Phase 2 fence, nothing here builds toward scenario
overrides (no supplier-disruption / demand-spike / capacity-reduction
knobs) — only base world-state initialization for this phase.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class WorldStateConfig:
    seed: int
    start_date: date
    num_days: int

    # TDD §10 target volumes.
    num_warehouses: int = 8
    num_skus: int = 5000
    num_suppliers: int = 100

    # Not specified in the frozen documents; reasonable starting points.
    num_customers: int = 2000
    num_carriers: int = 25
    zones_per_warehouse: int = 4
    warehouse_capacity_units: int = 2_000_000
    # ~5,000 SKUs seeded across 8 warehouses x 4 zones averages ~156
    # products/zone; sized with headroom above the per-product initial
    # stock computed by the reorder-calibration constants below, not tuned
    # to the exact expected load.
    zone_capacity_units: int = 500_000

    # Demand generator (FR-5.3: seasonal/promotional demand modifiers).
    base_daily_order_rate: float = 800.0
    seasonality_amplitude: float = 0.35
    max_lines_per_order: int = 4
    min_line_quantity: int = 1
    max_line_quantity: int = 5

    # Demand concentration (calibration, Phase 3 validation round 2):
    # products are assigned a Zipf/Pareto popularity weight at world-init
    # (generators/world_init.py:_assign_demand_weights) instead of being
    # selected with uniform probability. demand_zipf_exponent=1.0 is the
    # classic Zipf's-law exponent — empirically, real retail/e-commerce
    # SKU sales-rank distributions commonly follow close to this exponent,
    # so it is a literature-grounded default, not an arbitrary knob. It is
    # what makes the "top 20% of SKUs account for most demand" long-tail
    # shape the round-1 validation run's ~uniform demand did not have.
    demand_zipf_exponent: float = 1.0

    # PO reorder heuristic (FR-1.2) — deliberately simpler than, and must
    # remain a separate code path from, BR-3 (Phase 7's analytical reorder
    # recommendation). Round 1's fixed global reorder_threshold_units=200
    # / reorder_quantity_units=1000 produced zero purchase orders in 90
    # days: every product's threshold represented ~157 days of runway at
    # its actual (uniform-demand) consumption rate, far above any
    # supplier's lead time, so no product ever came close to triggering a
    # reorder. Round 2 replaces the single global threshold/quantity with
    # per-product values computed once at world-init
    # (generators/world_init.py:_compute_reorder_parameters), each derived
    # ONLY from that product's assigned demand weight, its assigned
    # suppliers' configured lead times, and the constants below — never
    # from observed/historical demand, rolling averages, or any live
    # computation. That keeps this heuristic pure simulation-input
    # configuration, not an analytical forecast, preserving the Phase
    # 3/Phase 7 boundary.
    #
    # reorder_safety_margin_days: extra buffer (in days of expected demand)
    # added on top of a product's own assigned supplier's lead time when
    # sizing its threshold — conceptually similar to conventional safety
    # stock, but expressed as a fixed day-count rather than computed from
    # demand variance, keeping the formula simple by design.
    reorder_safety_margin_days: int = 7
    # reorder_quantity_multiplier: each restock is sized as a multiple of
    # the product's own threshold, so one delivery covers several reorder
    # cycles' worth of buffer rather than restocking to the exact minimum.
    reorder_quantity_multiplier: float = 3.0
    # initial_inventory_multiplier: initial stock is set at this multiple
    # of each product's own calculated threshold — modest headroom so a
    # product isn't reordering from day 0, but low enough that ordinary
    # demand triggers a real first reorder within a 90-day validation
    # window for every demand tier, not just the highest-volume SKUs.
    initial_inventory_multiplier: float = 1.5

    # Supplier delivery generator: lead-time distribution + occasional
    # lateness (TDD §5).
    lead_time_jitter_days: int = 2
    late_delivery_probability: float = 0.08
    late_delivery_extra_days_max: int = 5
    quality_rejection_rate: float = 0.02

    # Transportation cost model.
    shipment_miles_min: float = 25.0
    shipment_miles_max: float = 1200.0
    average_transit_miles_per_day: float = 500.0

    # Returns generator.
    return_rate: float = 0.05
    return_inspection_same_day_probability: float = 0.7
    return_inspection_extra_days_max: int = 3


# Roadmap Phase 3 risk mitigation: "validate realism early on a 3-month
# run before generating the full 5-year run." Full target world size,
# short time window.
DEFAULT_VALIDATION_CONFIG = WorldStateConfig(
    seed=42,
    start_date=date(2021, 1, 1),
    num_days=90,
)

# Small world, short window — for fast automated tests only. Never used
# for the real validation or full-scale run.
TEST_CONFIG = WorldStateConfig(
    seed=1,
    start_date=date(2021, 1, 1),
    num_days=7,
    num_warehouses=2,
    num_skus=20,
    num_suppliers=5,
    num_customers=30,
    num_carriers=3,
    zones_per_warehouse=2,
    warehouse_capacity_units=50_000,
    zone_capacity_units=20_000,
    base_daily_order_rate=15.0,
)
