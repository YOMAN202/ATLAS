"""Transportation generator: dispatches fully-allocated order lines as
shipments with a cost model (TDD §5), then advances each shipment through
its lifecycle over the following days (FR-3.3).

Dispatch is the integration point Phase 2 deferred: converting a
reservation into a physical pick (inventory.pick) and linking the line to
its shipment (orders.mark_line_shipped), both confirmed with the project
owner before implementing (see the dispatch-wiring commit). Every write
goes through Domain Services (ADR-007).

Known simplification: a line that was partially backordered at order
time is never retried here — only lines allocated in full, in one shot,
ever ship. Backorder-retry (re-attempting allocation once new stock
arrives) is not built in Phase 3; flagged in the validation-run report.
"""

from datetime import date, timedelta

import numpy as np
from app.domains import inventory, orders, transportation
from app.models import Order, OrderLine
from sqlalchemy import select
from sqlalchemy.orm import Session

from simulation.config.world_state import WorldStateConfig
from simulation.generators.world_init import WorldState
from simulation.stats import SimulationStats
from simulation.time_utils import as_datetime

_STATUS_DAYS_AFTER_CREATION = {
    "PICKED": 1,
    "IN_TRANSIT": 2,
}


def generate_shipments_for_allocated_lines(
    session: Session,
    world: WorldState,
    current_date: date,
    config: WorldStateConfig,
    rng: np.random.Generator,
    stats: SimulationStats,
) -> None:
    """Dispatch every fully-allocated, not-yet-shipped line for the day in
    three bulk calls (pick_bulk, create_shipments_bulk,
    mark_lines_shipped_bulk) instead of one pick/create_shipment/
    mark_line_shipped sequence per line — this was ~49% of a simulated
    day's total cost in profiling (~2,700 lines/day at full scale).

    RNG draws (carrier choice, distance) still happen in a per-line loop,
    in the same order the lines were queried, before any bulk call — same
    draw sequence as the old per-line version, so determinism is
    unaffected by batching the DB work.
    """

    # Joins in the customer_id here (one query for the whole day's batch)
    # instead of a per-line session.get(Order, ...) — was one of the
    # largest single contributors to per-day DB round-trips.
    rows = session.execute(
        select(OrderLine, Order.customer_id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(
            OrderLine.allocated_quantity == OrderLine.ordered_quantity,
            OrderLine.shipment_id.is_(None),
        )
    ).all()
    if not rows:
        return

    occurred_at = as_datetime(current_date)
    picks = []
    shipment_requests = []
    transit_days_by_line: dict[int, int] = {}

    for line, customer_id in rows:
        # Carrier -> cost_per_mile is a small, fixed lookup (config.num_carriers,
        # e.g. 25) computed once at world-init instead of two session.get()
        # round-trips (Carrier, then VehicleType) per dispatched line.
        carrier_id = world.carrier_ids[int(rng.integers(0, len(world.carrier_ids)))]
        cost_per_mile = world.carrier_cost_per_mile[carrier_id]
        distance_miles = round(rng.uniform(config.shipment_miles_min, config.shipment_miles_max), 2)
        shipping_cost = round(distance_miles * float(cost_per_mile), 2)

        picks.append(
            {
                "inventory_position_id": world.initial_positions[line.product_id],
                "quantity": line.allocated_quantity,
                "occurred_at": occurred_at,
                "source_reference_type": "order_line",
                "source_reference_id": line.id,
            }
        )
        shipment_requests.append(
            {
                "line": line,
                "shipment_number": f"SHIP-{current_date.isoformat()}-{stats.next_seq():08d}",
                "carrier_id": carrier_id,
                "origin_warehouse_id": line.fulfillment_warehouse_id,
                "destination_customer_id": customer_id,
                "occurred_at": occurred_at,
                "ship_date": current_date,
                "distance_miles": distance_miles,
                "shipping_cost": shipping_cost,
            }
        )
        transit_days_by_line[line.id] = max(
            1, round(distance_miles / config.average_transit_miles_per_day)
        )

    inventory.pick_bulk(session, picks=picks)
    created_shipments = transportation.create_shipments_bulk(
        session,
        shipments=[
            {k: v for k, v in request.items() if k != "line"} for request in shipment_requests
        ],
    )
    orders.mark_lines_shipped_bulk(
        session,
        links=[
            {"order_line_id": request["line"].id, "shipment_id": shipment.id}
            for request, shipment in zip(shipment_requests, created_shipments, strict=True)
        ],
    )
    stats.shipments_created += len(created_shipments)

    for request, shipment in zip(shipment_requests, created_shipments, strict=True):
        line_id = request["line"].id
        transit_days = transit_days_by_line[line_id]
        schedule = [
            (current_date + timedelta(days=_STATUS_DAYS_AFTER_CREATION["PICKED"]), "PICKED"),
            (
                current_date + timedelta(days=_STATUS_DAYS_AFTER_CREATION["IN_TRANSIT"]),
                "IN_TRANSIT",
            ),
            (
                current_date
                + timedelta(days=_STATUS_DAYS_AFTER_CREATION["IN_TRANSIT"] + transit_days),
                "DELIVERED",
            ),
        ]
        world.pending_shipments.append(
            {"shipment_id": shipment.id, "order_line_id": line_id, "schedule": schedule}
        )


def advance_pending_shipments(
    session: Session,
    world: WorldState,
    current_date: date,
    stats: SimulationStats,
) -> list[tuple[int, date]]:
    """Advance every in-flight shipment whose next scheduled status is
    due. Returns (order_line_id, delivered_date) for shipments that
    reached DELIVERED today, so the caller (the engine) can decide
    whether to queue a return — this module doesn't know about returns.
    """

    still_pending = []
    newly_delivered: list[tuple[int, date]] = []

    for entry in world.pending_shipments:
        schedule = entry["schedule"]
        while schedule and schedule[0][0] <= current_date:
            due_date, status_code = schedule.pop(0)
            transportation.advance_shipment_status(
                session,
                shipment_id=entry["shipment_id"],
                new_status_code=status_code,
                occurred_at=as_datetime(due_date),
            )
            if status_code == "DELIVERED":
                stats.shipments_delivered += 1
                newly_delivered.append((entry["order_line_id"], due_date))

        if schedule:
            still_pending.append(entry)

    world.pending_shipments = still_pending
    return newly_delivered
