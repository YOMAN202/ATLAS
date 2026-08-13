"""Operational dashboard — merges what the proposal separately called
Transportation (fact_shipments, grain: 1 row per shipment) and the
buildable part of Warehouse (capacity utilization) per your approved
dashboard mapping. Pick accuracy and zone-level throughput (SRS §15)
are NOT implemented — no fact table exists at that grain anywhere in
the warehouse (docs/phase6-dashboard-proposal.md §2); building them
would mean inventing data, not querying it.

Real finding while building this dashboard (not a bug here): every one
of the 696,747 shipments in fact_shipments has estimated_delivery_date_key
= NULL, because atlas_oltp.shipments.estimated_delivery_date is NULL for
100% of rows at the source — the simulation engine never populates it.
is_on_time is therefore always NULL too (etl/transform/facts.py can only
compute it when both the actual and estimated dates are known), so
on_time_delivery_rate is structurally unavailable from this dataset, not
a query mistake. transit_days doesn't depend on the estimate and is
unaffected (only 7,905 NULLs — genuinely still-in-transit shipments at
the end of the simulated year).

Role: operations_analyst, executive, administrator.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.api.schemas import AsOf, PageEnvelope
from app.core.security import ADMINISTRATOR, EXECUTIVE, OPERATIONS_ANALYST, require_role

router = APIRouter(prefix="/api/v1/dashboards/operational", tags=["operational"])


class WarehouseCapacityRow(BaseModel):
    warehouse_key: int
    warehouse_name: str
    total_capacity_units: int
    quantity_on_hand: int
    capacity_utilization: float | None


class OperationalSummary(BaseModel):
    as_of: AsOf
    total_shipments: int
    on_time_delivery_rate: float | None
    on_time_delivery_rate_note: str | None = None
    average_cost_per_mile: float | None
    average_cost_per_shipment: float | None
    average_transit_days: float | None
    pick_accuracy: None = None
    pick_accuracy_note: str = "Not computed — no picking-event fact table exists in the warehouse."
    zone_throughput: None = None
    zone_throughput_note: str = "Not computed — no fact table is at warehouse-zone grain."
    warehouse_capacity: list[WarehouseCapacityRow]


class ShipmentRow(BaseModel):
    source_shipment_id: int
    shipment_number: str
    status_code: str
    carrier_key: int
    origin_warehouse_key: int
    distance_miles: float | None
    shipping_cost: float | None
    is_on_time: bool | None
    transit_days: int | None


def _date_key(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _params(carrier_key, warehouse_key, date_from, date_to):
    return {
        "carrier_key": carrier_key,
        "warehouse_key": warehouse_key,
        "date_from": _date_key(date_from),
        "date_to": _date_key(date_to),
    }


_FILTER_CLAUSE = (
    "(:carrier_key IS NULL OR fs.carrier_key = :carrier_key) "
    "AND (:warehouse_key IS NULL OR fs.origin_warehouse_key = :warehouse_key) "
    "AND (:date_from IS NULL OR fs.ship_date_key >= :date_from) "
    "AND (:date_to IS NULL OR fs.ship_date_key <= :date_to)"
)


@router.get("", response_model=OperationalSummary)
def get_operational_summary(
    carrier_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> OperationalSummary:
    etl_run_id = get_current_etl_run_id(conn)
    params = _params(carrier_key, warehouse_key, date_from, date_to)
    key = cache_key("operational_summary", etl_run_id, **params)
    cached = get_cached(key)
    if cached is not None:
        return cached

    row = conn.execute(
        text(
            "SELECT COUNT(*) AS shipments, "
            "AVG(CAST(fs.is_on_time AS DECIMAL(10,4))) AS on_time_rate, "
            "SUM(fs.shipping_cost) AS total_cost, SUM(fs.distance_miles) AS total_miles, "
            "AVG(fs.shipping_cost) AS avg_cost, AVG(fs.transit_days) AS avg_transit "
            f"FROM fact_shipments fs WHERE {_FILTER_CLAUSE}"
        ),
        params,
    ).one()

    # Capacity utilization: fact_inventory_snapshot's latest total
    # quantity_on_hand per warehouse / dim_warehouse.total_capacity_units
    # — a second source table, documented rather than folded silently
    # into the shipments query above.
    latest_key = conn.execute(
        text("SELECT MAX(snapshot_date_key) FROM fact_inventory_snapshot")
    ).scalar_one()
    capacity_rows = conn.execute(
        text(
            "SELECT w.warehouse_key, w.warehouse_name, w.total_capacity_units, "
            "COALESCE(SUM(f.quantity_on_hand), 0) AS on_hand "
            "FROM dim_warehouse w "
            "LEFT JOIN fact_inventory_snapshot f "
            "  ON f.warehouse_key = w.warehouse_key AND f.snapshot_date_key = :latest_key "
            "WHERE w.is_current = 1 "
            "AND (:warehouse_key IS NULL OR w.warehouse_key = :warehouse_key) "
            "GROUP BY w.warehouse_key, w.warehouse_name, w.total_capacity_units "
            "ORDER BY w.warehouse_key"
        ),
        {"latest_key": latest_key, "warehouse_key": warehouse_key},
    ).all()

    result = OperationalSummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        total_shipments=int(row.shipments),
        on_time_delivery_rate=float(row.on_time_rate) if row.on_time_rate is not None else None,
        on_time_delivery_rate_note=(
            None
            if row.on_time_rate is not None
            else "Unavailable: estimated_delivery_date is NULL for every shipment "
            "at the OLTP source "
            "(a real source-data limitation, not a query issue) — is_on_time can never be computed."
        ),
        average_cost_per_mile=(
            (float(row.total_cost) / float(row.total_miles)) if row.total_miles else None
        ),
        average_cost_per_shipment=float(row.avg_cost) if row.avg_cost is not None else None,
        average_transit_days=float(row.avg_transit) if row.avg_transit is not None else None,
        warehouse_capacity=[
            WarehouseCapacityRow(
                warehouse_key=r.warehouse_key,
                warehouse_name=r.warehouse_name,
                total_capacity_units=r.total_capacity_units,
                quantity_on_hand=int(r.on_hand),
                capacity_utilization=(
                    float(r.on_hand) / float(r.total_capacity_units)
                    if r.total_capacity_units
                    else None
                ),
            )
            for r in capacity_rows
        ],
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[ShipmentRow])
def get_operational_detail(
    carrier_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> PageEnvelope[ShipmentRow]:
    params = _params(carrier_key, warehouse_key, date_from, date_to)

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM fact_shipments fs WHERE {_FILTER_CLAUSE}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT fs.source_shipment_id, fs.shipment_number, fs.status_code, fs.carrier_key, "
            "fs.origin_warehouse_key, fs.distance_miles, fs.shipping_cost, "
            "fs.is_on_time, fs.transit_days "
            f"FROM fact_shipments fs WHERE {_FILTER_CLAUSE} "
            "ORDER BY fs.source_shipment_id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            ShipmentRow(
                source_shipment_id=r.source_shipment_id,
                shipment_number=r.shipment_number,
                status_code=r.status_code,
                carrier_key=r.carrier_key,
                origin_warehouse_key=r.origin_warehouse_key,
                distance_miles=float(r.distance_miles) if r.distance_miles is not None else None,
                shipping_cost=float(r.shipping_cost) if r.shipping_cost is not None else None,
                is_on_time=bool(r.is_on_time) if r.is_on_time is not None else None,
                transit_days=r.transit_days,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
