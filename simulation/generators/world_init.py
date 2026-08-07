"""World-state initialization: creates the master data (warehouses,
zones, products, suppliers, customers, carriers) a simulation run needs
before the day-advancing loop can generate any operational events.

Every write goes through Domain Services (ADR-007) — this module never
touches an OLTP model directly except for read-only lookups of already-
seeded reference data (regions, vehicle types). Faker is used only for
master-data names/addresses (Master Prompt §9), never for business-event
logic — order/PO/shipment/return generation never touches Faker.

The OLTP schema has no product-supplier mapping table (TDD §4.1 names
none), so which supplier(s) can fulfill a product is tracked here, in
memory, as part of WorldState — not persisted, since it isn't part of
the frozen schema.
"""

import math
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
from app.domains import inventory, orders, procurement, transportation, warehousing
from app.models import Product, Region, VehicleType
from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.time_utils import as_datetime

_SUPPLIERS_PER_PRODUCT_MIN = 1
_SUPPLIERS_PER_PRODUCT_MAX = 3
_MIN_SUPPLIER_LEAD_TIME_DAYS = 3
_MAX_SUPPLIER_LEAD_TIME_DAYS = 21


@dataclass
class WorldState:
    warehouse_ids: list[int]
    warehouse_zone_ids: dict[int, list[int]]
    product_ids: list[int]
    supplier_ids: list[int]
    customer_ids: list[int]
    carrier_ids: list[int]
    product_suppliers: dict[int, list[int]]
    initial_positions: dict[int, int]
    product_prices: dict[int, tuple[Decimal, Decimal]]  # product_id -> (unit_cost, unit_price)
    # Demand calibration (round 2): Zipf/Pareto popularity weight per
    # product (shares sum to 1.0 across all products), and the same
    # weights as a plain array aligned with product_ids — precomputed once
    # so the daily demand generator doesn't rebuild it on every order.
    product_demand_weights: dict[int, float]
    product_demand_weights_array: np.ndarray
    # Per-product reorder threshold/quantity computed once at world-init
    # from configured values only (demand weight, assigned suppliers'
    # configured lead times, and WorldStateConfig's calibration constants)
    # — never from observed/historical demand. See WorldStateConfig's
    # reorder_safety_margin_days / reorder_quantity_multiplier /
    # initial_inventory_multiplier docstring for the full rationale.
    reorder_thresholds: dict[int, int]
    reorder_quantities: dict[int, int]
    # carrier_id -> cost_per_mile, precomputed at world-init (see
    # _create_carriers) so transportation dispatch never needs a
    # per-line session.get(Carrier, ...) / session.get(VehicleType, ...).
    carrier_cost_per_mile: dict[int, Decimal]

    # Runtime state threaded across simulated days by the day-advancing
    # generators (not populated here — world_init only creates master
    # data and the initial inventory position).
    products_with_open_po: set[int] = field(default_factory=set)
    pending_po_deliveries: list[dict] = field(default_factory=list)
    pending_shipments: list[dict] = field(default_factory=list)
    pending_returns: list[dict] = field(default_factory=list)
    pending_inspections: list[dict] = field(default_factory=list)


def create_world(
    session: Session, config: WorldStateConfig, rng: np.random.Generator
) -> WorldState:
    """Create every master-data entity a simulation run needs, plus one
    seeded inventory position per product, and return a WorldState the
    day-advancing generators use to avoid re-querying master data daily.
    """

    fake = Faker()
    Faker.seed(config.seed)

    region_ids = _existing_region_ids(session)
    warehouse_ids, warehouse_zone_ids = _create_warehouses(session, config, fake, region_ids)
    product_ids, product_prices = _create_products(session, config, fake, rng)
    supplier_ids, supplier_lead_times = _create_suppliers(session, config, fake, rng)
    customer_ids = _create_customers(session, config, fake, region_ids)
    carrier_ids, carrier_cost_per_mile = _create_carriers(session, config, fake)

    product_suppliers = {
        product_id: _assign_suppliers(rng, supplier_ids) for product_id in product_ids
    }
    demand_weights = _assign_demand_weights(rng, product_ids, config)
    demand_weights_array = np.array([demand_weights[pid] for pid in product_ids])
    reorder_thresholds, reorder_quantities = _compute_reorder_parameters(
        product_ids, demand_weights, product_suppliers, supplier_lead_times, config
    )

    initial_positions = _seed_initial_inventory(
        session, config, rng, product_ids, warehouse_ids, warehouse_zone_ids, reorder_thresholds
    )

    return WorldState(
        warehouse_ids=warehouse_ids,
        warehouse_zone_ids=warehouse_zone_ids,
        product_ids=product_ids,
        supplier_ids=supplier_ids,
        customer_ids=customer_ids,
        carrier_ids=carrier_ids,
        product_suppliers=product_suppliers,
        initial_positions=initial_positions,
        product_prices=product_prices,
        product_demand_weights=demand_weights,
        product_demand_weights_array=demand_weights_array,
        reorder_thresholds=reorder_thresholds,
        reorder_quantities=reorder_quantities,
        carrier_cost_per_mile=carrier_cost_per_mile,
    )


def _create_warehouses(
    session: Session, config: WorldStateConfig, fake: Faker, region_ids: list[int]
) -> tuple[list[int], dict[int, list[int]]]:
    warehouse_ids: list[int] = []
    warehouse_zone_ids: dict[int, list[int]] = {}

    for i in range(config.num_warehouses):
        region_id = region_ids[i % len(region_ids)]
        warehouse = warehousing.create_warehouse(
            session,
            warehouse_code=f"WH-{i + 1:03d}",
            name=f"{fake.city()} Distribution Center",
            region_id=region_id,
            total_capacity_units=config.warehouse_capacity_units,
            address_line1=fake.street_address(),
            city=fake.city(),
            state_province=fake.state(),
            postal_code=fake.postcode(),
            country="USA",
        )
        warehouse_ids.append(warehouse.id)

        zone_ids = []
        for z in range(config.zones_per_warehouse):
            zone_code = chr(ord("A") + z)
            zone = warehousing.create_warehouse_zone(
                session,
                warehouse_id=warehouse.id,
                zone_code=zone_code,
                name=f"Zone {zone_code}",
                zone_capacity_units=config.zone_capacity_units,
            )
            zone_ids.append(zone.id)
        warehouse_zone_ids[warehouse.id] = zone_ids

    return warehouse_ids, warehouse_zone_ids


def _create_products(
    session: Session, config: WorldStateConfig, fake: Faker, rng: np.random.Generator
) -> tuple[list[int], dict[int, tuple[Decimal, Decimal]]]:
    product_ids: list[int] = []
    product_prices: dict[int, tuple[Decimal, Decimal]] = {}
    for i in range(config.num_skus):
        unit_cost = _random_price(rng, low=2.0, high=200.0)
        unit_price = _random_price(rng, low=5.0, high=400.0)
        product: Product = inventory.create_product(
            session,
            sku=f"SKU-{i + 1:06d}",
            name=fake.catch_phrase(),
            unit_cost=unit_cost,
            unit_price=unit_price,
            category=fake.word(),
        )
        product_ids.append(product.id)
        product_prices[product.id] = (Decimal(unit_cost), Decimal(unit_price))
    return product_ids, product_prices


def _create_suppliers(
    session: Session, config: WorldStateConfig, fake: Faker, rng: np.random.Generator
) -> tuple[list[int], dict[int, int]]:
    supplier_ids: list[int] = []
    supplier_lead_times: dict[int, int] = {}
    for i in range(config.num_suppliers):
        lead_time_days = int(
            rng.integers(_MIN_SUPPLIER_LEAD_TIME_DAYS, _MAX_SUPPLIER_LEAD_TIME_DAYS + 1)
        )
        supplier = procurement.create_supplier(
            session,
            supplier_code=f"SUP-{i + 1:04d}",
            name=fake.company(),
            default_lead_time_days=lead_time_days,
            contact_email=fake.company_email(),
            contact_phone=fake.phone_number(),
            address_line1=fake.street_address(),
            city=fake.city(),
            state_province=fake.state(),
            postal_code=fake.postcode(),
            country="USA",
        )
        supplier_ids.append(supplier.id)
        supplier_lead_times[supplier.id] = lead_time_days
    return supplier_ids, supplier_lead_times


def _create_customers(
    session: Session, config: WorldStateConfig, fake: Faker, region_ids: list[int]
) -> list[int]:
    customer_ids: list[int] = []
    for i in range(config.num_customers):
        region_id = region_ids[i % len(region_ids)]
        customer = orders.create_customer(
            session,
            customer_code=f"CUST-{i + 1:06d}",
            name=fake.name(),
            region_id=region_id,
            email=fake.email(),
            phone=fake.phone_number(),
            address_line1=fake.street_address(),
            city=fake.city(),
            state_province=fake.state(),
            postal_code=fake.postcode(),
            country="USA",
        )
        customer_ids.append(customer.id)
    return customer_ids


def _create_carriers(
    session: Session, config: WorldStateConfig, fake: Faker
) -> tuple[list[int], dict[int, Decimal]]:
    vehicle_type_ids = _existing_vehicle_type_ids(session)
    # Vehicle types are a tiny, fixed reference set (config.num_carriers
    # cycles through them) — fetched once here so the transportation
    # generator never needs a per-dispatch session.get(VehicleType, ...).
    cost_per_mile_by_vehicle_type = {
        vt_id: session.get(VehicleType, vt_id).cost_per_mile for vt_id in vehicle_type_ids
    }

    carrier_ids: list[int] = []
    carrier_cost_per_mile: dict[int, Decimal] = {}
    for i in range(config.num_carriers):
        vehicle_type_id = vehicle_type_ids[i % len(vehicle_type_ids)]
        carrier = transportation.create_carrier(
            session,
            carrier_code=f"CARR-{i + 1:03d}",
            name=f"{fake.company()} Logistics",
            vehicle_type_id=vehicle_type_id,
        )
        carrier_ids.append(carrier.id)
        carrier_cost_per_mile[carrier.id] = cost_per_mile_by_vehicle_type[vehicle_type_id]
    return carrier_ids, carrier_cost_per_mile


def _existing_region_ids(session: Session) -> list[int]:
    ids = session.execute(select(Region.id).order_by(Region.id)).scalars().all()
    if not ids:
        raise RuntimeError(
            "No regions found — run backend's seed_reference_data before the simulation"
        )
    return list(ids)


def _existing_vehicle_type_ids(session: Session) -> list[int]:
    ids = session.execute(select(VehicleType.id).order_by(VehicleType.id)).scalars().all()
    if not ids:
        raise RuntimeError(
            "No vehicle types found — run backend's seed_reference_data before the simulation"
        )
    return list(ids)


def _random_price(rng: np.random.Generator, *, low: float, high: float) -> str:
    # Returned as a string so callers pass it straight into a
    # Decimal-typed field without float-precision surprises (NFR-4).
    return f"{rng.uniform(low, high):.2f}"


def _assign_suppliers(rng: np.random.Generator, supplier_ids: list[int]) -> list[int]:
    count = int(rng.integers(_SUPPLIERS_PER_PRODUCT_MIN, _SUPPLIERS_PER_PRODUCT_MAX + 1))
    count = min(count, len(supplier_ids))
    chosen = rng.choice(len(supplier_ids), size=count, replace=False)
    return sorted(supplier_ids[i] for i in chosen)


def _assign_demand_weights(
    rng: np.random.Generator, product_ids: list[int], config: WorldStateConfig
) -> dict[int, float]:
    """Zipf/Pareto popularity weight per product (calibration round 2):
    weight(rank) = 1 / rank^demand_zipf_exponent, normalized to sum to 1
    across all products. Ranks are assigned via a random permutation of
    product_ids (not creation order), so popularity doesn't trivially
    correlate with SKU number — decorrelating the two is what keeps this
    a demand-shape assignment rather than an artifact of naming order.
    """

    n = len(product_ids)
    ranks = rng.permutation(n) + 1  # 1-indexed ranks, one per product_ids position
    raw_weights = 1.0 / np.power(ranks.astype(float), config.demand_zipf_exponent)
    normalized = raw_weights / raw_weights.sum()
    return {product_id: float(normalized[i]) for i, product_id in enumerate(product_ids)}


def _compute_reorder_parameters(
    product_ids: list[int],
    demand_weights: dict[int, float],
    product_suppliers: dict[int, list[int]],
    supplier_lead_times: dict[int, int],
    config: WorldStateConfig,
) -> tuple[dict[int, int], dict[int, int]]:
    """Per-product reorder threshold + restock quantity (calibration round
    2), derived ONLY from configured/assigned values — a product's own
    demand weight, its assigned suppliers' configured lead times, and
    WorldStateConfig's calibration constants. No observed/historical
    demand, rolling averages, or live computation of any kind, per the
    Phase 3 / Phase 7 architectural boundary (see WorldStateConfig).

    threshold = expected_daily_demand_units x (max assigned lead time +
    reorder_safety_margin_days). Using the max (not average) lead time
    among a product's assigned suppliers is a deliberately conservative
    choice: run_reorder_heuristic picks a random assigned supplier each
    time it reorders, so sizing the buffer for the slowest one avoids an
    optimistic threshold that a slow-supplier draw could undercut.
    """

    avg_lines_per_order = (1 + config.max_lines_per_order) / 2
    avg_quantity_per_line = (config.min_line_quantity + config.max_line_quantity) / 2
    expected_total_daily_units = (
        config.base_daily_order_rate * avg_lines_per_order * avg_quantity_per_line
    )

    thresholds: dict[int, int] = {}
    quantities: dict[int, int] = {}
    for product_id in product_ids:
        expected_daily_units = demand_weights[product_id] * expected_total_daily_units
        max_lead_time = max(
            supplier_lead_times[supplier_id] for supplier_id in product_suppliers[product_id]
        )
        threshold = max(
            1,
            math.ceil(expected_daily_units * (max_lead_time + config.reorder_safety_margin_days)),
        )
        thresholds[product_id] = threshold
        quantities[product_id] = max(1, math.ceil(threshold * config.reorder_quantity_multiplier))

    return thresholds, quantities


def _seed_initial_inventory(
    session: Session,
    config: WorldStateConfig,
    rng: np.random.Generator,
    product_ids: list[int],
    warehouse_ids: list[int],
    warehouse_zone_ids: dict[int, list[int]],
    reorder_thresholds: dict[int, int],
) -> dict[int, int]:
    """One seeded position per product, in one randomly chosen warehouse
    zone, at initial_inventory_multiplier x that product's own reorder
    threshold — sparsified (TDD §10: "a SKU not yet stocked at a
    warehouse generates no snapshot rows"), not every product in every
    warehouse. Sizing initial stock relative to each product's own
    (demand-derived) threshold, rather than one global quantity, is what
    lets every demand tier — not just the highest-volume SKUs — reach its
    first real reorder within the validation window.
    """

    initial_positions: dict[int, int] = {}
    occurred_at = as_datetime(config.start_date)

    for product_id in product_ids:
        warehouse_id = warehouse_ids[int(rng.integers(0, len(warehouse_ids)))]
        zone_ids = warehouse_zone_ids[warehouse_id]
        zone_id = zone_ids[int(rng.integers(0, len(zone_ids)))]

        initial_quantity = math.ceil(
            reorder_thresholds[product_id] * config.initial_inventory_multiplier
        )

        position = inventory.get_or_create_position(
            session, product_id=product_id, warehouse_id=warehouse_id, warehouse_zone_id=zone_id
        )
        inventory.record_transaction(
            session,
            inventory_position_id=position.id,
            transaction_type_code="RECEIPT",
            quantity_delta=initial_quantity,
            occurred_at=occurred_at,
            source_reference_type="world_init",
            source_reference_id=product_id,
        )
        initial_positions[product_id] = position.id

    return initial_positions
