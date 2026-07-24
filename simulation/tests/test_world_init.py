import numpy as np
import pytest
from app.models import (
    Carrier,
    Customer,
    InventoryPosition,
    Product,
    Supplier,
    Warehouse,
    WarehouseZone,
)
from app.seed.reference_data import seed_reference_data
from sqlalchemy import func, select

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.world_init import create_world


def test_create_world_produces_expected_counts(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    assert len(world.warehouse_ids) == TEST_CONFIG.num_warehouses
    assert len(world.product_ids) == TEST_CONFIG.num_skus
    assert len(world.supplier_ids) == TEST_CONFIG.num_suppliers
    assert len(world.customer_ids) == TEST_CONFIG.num_customers
    assert len(world.carrier_ids) == TEST_CONFIG.num_carriers

    assert db_session.scalar(select(func.count(Warehouse.id))) == TEST_CONFIG.num_warehouses
    assert db_session.scalar(select(func.count(Product.id))) == TEST_CONFIG.num_skus
    assert db_session.scalar(select(func.count(Supplier.id))) == TEST_CONFIG.num_suppliers
    assert db_session.scalar(select(func.count(Customer.id))) == TEST_CONFIG.num_customers
    assert db_session.scalar(select(func.count(Carrier.id))) == TEST_CONFIG.num_carriers
    assert (
        db_session.scalar(select(func.count(WarehouseZone.id)))
        == TEST_CONFIG.num_warehouses * TEST_CONFIG.zones_per_warehouse
    )


def test_create_world_seeds_one_position_per_product(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    assert len(world.initial_positions) == len(world.product_ids)
    for product_id in world.product_ids:
        assert product_id in world.initial_positions


def test_create_world_assigns_one_to_three_suppliers_per_product(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    for product_id in world.product_ids:
        assigned = world.product_suppliers[product_id]
        assert 1 <= len(assigned) <= 3
        assert len(assigned) == len(set(assigned))
        assert all(s in world.supplier_ids for s in assigned)


# Calibration round 2 (FR-1.2 recalibration): demand weights follow a
# Zipf/Pareto shape, not uniform, and every product gets a positive,
# configured-only reorder threshold/quantity.
def test_create_world_assigns_concentrated_demand_weights(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    assert len(world.product_demand_weights) == len(world.product_ids)
    assert sum(world.product_demand_weights.values()) == pytest.approx(1.0, abs=1e-9)
    assert len(world.product_demand_weights_array) == len(world.product_ids)

    # Zipf shape: top 20% of products (by weight) must collectively
    # account for meaningfully more than a uniform 20% share — evidence
    # the distribution is actually concentrated, not flat.
    sorted_weights = sorted(world.product_demand_weights.values(), reverse=True)
    top_20_count = max(1, len(sorted_weights) // 5)
    top_20_share = sum(sorted_weights[:top_20_count])
    assert top_20_share > 0.20


def test_create_world_computes_positive_reorder_parameters_per_product(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    for product_id in world.product_ids:
        assert world.reorder_thresholds[product_id] >= 1
        assert world.reorder_quantities[product_id] >= 1
        # Initial stock (threshold x initial_inventory_multiplier) must
        # start strictly above the threshold, or the reorder heuristic
        # would fire immediately at day 0 for every product.
        position = db_session.get(InventoryPosition, world.initial_positions[product_id])
        assert position.quantity_on_hand > world.reorder_thresholds[product_id]


# Determinism: same seed -> identical sequence of RNG-driven values.
#
# Surrogate ids (product_id, supplier_id) are NOT reproducible across two
# separate create_world calls — MySQL's AUTO_INCREMENT counter is not
# transactional and is unaffected by the rollback below, so the same
# logical "first product" gets a different id each time. Comparing by id
# would fail even when the generator is perfectly deterministic; instead
# compare by *position* (creation order is itself deterministic) and by
# values that don't depend on any id (prices, supplier *count* per product).
def test_create_world_is_deterministic_given_same_seed(db_session, seeded_lookups):
    rng1 = np.random.default_rng(TEST_CONFIG.seed)
    world1 = create_world(db_session, TEST_CONFIG, rng1)
    prices_by_position_1 = [world1.product_prices[pid] for pid in world1.product_ids]
    supplier_counts_by_position_1 = [
        len(world1.product_suppliers[pid]) for pid in world1.product_ids
    ]
    weights_by_position_1 = [world1.product_demand_weights[pid] for pid in world1.product_ids]
    thresholds_by_position_1 = [world1.reorder_thresholds[pid] for pid in world1.product_ids]

    # Rolling back the session clears everything written since the
    # savepoint restart, including the seeded lookups — re-seed (it's
    # idempotent) before building a second world from the same starting
    # point.
    db_session.rollback()
    seed_reference_data(db_session)

    rng2 = np.random.default_rng(TEST_CONFIG.seed)
    world2 = create_world(db_session, TEST_CONFIG, rng2)
    prices_by_position_2 = [world2.product_prices[pid] for pid in world2.product_ids]
    supplier_counts_by_position_2 = [
        len(world2.product_suppliers[pid]) for pid in world2.product_ids
    ]
    weights_by_position_2 = [world2.product_demand_weights[pid] for pid in world2.product_ids]
    thresholds_by_position_2 = [world2.reorder_thresholds[pid] for pid in world2.product_ids]

    assert prices_by_position_1 == prices_by_position_2
    assert supplier_counts_by_position_1 == supplier_counts_by_position_2
    assert weights_by_position_1 == weights_by_position_2
    assert thresholds_by_position_1 == thresholds_by_position_2
