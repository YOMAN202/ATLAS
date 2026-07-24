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
    # products/zone at reorder_quantity_units each (~156k units) before any
    # restocking; sized with headroom above that, not tuned to the exact
    # expected load.
    zone_capacity_units: int = 500_000

    # Demand generator (FR-5.3: seasonal/promotional demand modifiers).
    base_daily_order_rate: float = 800.0
    seasonality_amplitude: float = 0.35
    max_lines_per_order: int = 4

    # Supplier delivery generator: lead-time distribution + occasional
    # lateness (TDD §5).
    lead_time_jitter_days: int = 2
    late_delivery_probability: float = 0.08
    late_delivery_extra_days_max: int = 5
    quality_rejection_rate: float = 0.02

    # PO reorder heuristic (FR-1.2) — deliberately simpler than BR-3
    # (Phase 7's avg-daily-demand x lead-time + safety-stock formula) and
    # must stay that way; see generators/procurement.py.
    reorder_threshold_units: int = 200
    reorder_quantity_units: int = 1000

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
