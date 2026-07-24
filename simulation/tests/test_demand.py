from datetime import date

import numpy as np
import pytest
from app.models import Order, OrderLine
from sqlalchemy import select

from simulation.config.world_state import TEST_CONFIG
from simulation.generators.demand import generate_daily_orders, seasonal_multiplier
from simulation.generators.world_init import create_world
from simulation.stats import SimulationStats


# FR-5.3: seasonality curve peaks in late November, troughs half a year away.
def test_seasonal_multiplier_peaks_in_late_november():
    peak = seasonal_multiplier(date(2021, 12, 1), TEST_CONFIG)
    trough = seasonal_multiplier(date(2021, 6, 1), TEST_CONFIG)
    average = seasonal_multiplier(date(2021, 3, 2), TEST_CONFIG)

    assert peak > average > trough
    assert peak == pytest.approx(1.0 + TEST_CONFIG.seasonality_amplitude, abs=0.02)
    assert trough == pytest.approx(1.0 - TEST_CONFIG.seasonality_amplitude, abs=0.02)


def test_generate_daily_orders_creates_orders_and_allocates(db_session, seeded_lookups):
    rng = np.random.default_rng(TEST_CONFIG.seed)
    world = create_world(db_session, TEST_CONFIG, rng)

    generate_daily_orders(
        db_session, world, TEST_CONFIG.start_date, TEST_CONFIG, rng, SimulationStats()
    )

    assert db_session.scalar(select(Order).limit(1)) is not None

    lines = db_session.execute(select(OrderLine)).scalars().all()
    assert len(lines) > 0
    for line in lines:
        # BR-2: every line is either allocated, backordered, or both, and
        # never more than what was ordered.
        assert line.allocated_quantity + line.backordered_quantity <= line.ordered_quantity
        assert line.allocated_quantity >= 0
        assert line.backordered_quantity >= 0
