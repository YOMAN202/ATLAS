"""Inventory dashboard (SRS FR-7.2). Primary source: fact_inventory_snapshot
(grain: 1 row per product/warehouse/day). Turnover and days-of-supply are
standard supply-chain formulas that genuinely need a second source table
(fact_orders, for units/cost sold) — documented per-KPI below rather than
left implicit; not invented math, but not single-table either.

Overstock value (SRS §15) is intentionally NOT implemented — it needs an
explicit "what counts as overstock" policy threshold that hasn't been
defined anywhere in the frozen spec (docs/phase6-dashboard-proposal.md
§5.2, §2). No placeholder threshold is used.

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

router = APIRouter(prefix="/api/v1/dashboards/inventory", tags=["inventory"])


class InventorySummary(BaseModel):
    as_of: AsOf
    latest_snapshot_date: date | None
    total_quantity_on_hand: int
    total_inventory_value: float
    stockout_rate: float | None
    inventory_turnover: float | None
    days_of_supply: float | None
    overstock_value: None = None
    overstock_value_note: str = (
        "Not computed — 'overstock' requires an explicit days-of-supply threshold policy "
        "(docs/phase6-dashboard-proposal.md §5.2), not a placeholder value."
    )


class InventoryRow(BaseModel):
    product_key: int
    warehouse_key: int
    snapshot_date: date
    quantity_on_hand: int
    quantity_available: int
    inventory_value: float
    is_stockout: bool


def _date_key(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _base_params(product_key, warehouse_key, date_from, date_to):
    return {
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "date_from": _date_key(date_from),
        "date_to": _date_key(date_to),
    }


_SNAPSHOT_FILTER = (
    "(:product_key IS NULL OR f.product_key = :product_key) "
    "AND (:warehouse_key IS NULL OR f.warehouse_key = :warehouse_key) "
    "AND (:date_from IS NULL OR f.snapshot_date_key >= :date_from) "
    "AND (:date_to IS NULL OR f.snapshot_date_key <= :date_to)"
)


@router.get("", response_model=InventorySummary)
def get_inventory_summary(
    product_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> InventorySummary:
    etl_run_id = get_current_etl_run_id(conn)
    params = _base_params(product_key, warehouse_key, date_from, date_to)
    key = cache_key("inventory_summary", etl_run_id, **params)
    cached = get_cached(key)
    if cached is not None:
        return cached

    latest_date_row = conn.execute(
        text(
            "SELECT MAX(f.snapshot_date_key) AS latest_key "
            f"FROM fact_inventory_snapshot f WHERE {_SNAPSHOT_FILTER}"
        ),
        params,
    ).one()
    latest_key = latest_date_row.latest_key

    if latest_key is None:
        result = InventorySummary(
            as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
            latest_snapshot_date=None,
            total_quantity_on_hand=0,
            total_inventory_value=0.0,
            stockout_rate=None,
            inventory_turnover=None,
            days_of_supply=None,
        )
        set_cached(key, result)
        return result

    latest = conn.execute(
        text(
            "SELECT dd.full_date, SUM(f.quantity_on_hand) AS on_hand, "
            "SUM(f.inventory_value) AS inventory_total_value, "
            "AVG(CAST(f.is_stockout AS DECIMAL(10,4))) AS stockout_rate "
            "FROM fact_inventory_snapshot f "
            "JOIN dim_date dd ON dd.date_key = f.snapshot_date_key "
            "WHERE f.snapshot_date_key = :latest_key "
            "AND (:product_key IS NULL OR f.product_key = :product_key) "
            "AND (:warehouse_key IS NULL OR f.warehouse_key = :warehouse_key) "
            "GROUP BY dd.full_date"
        ),
        {"latest_key": latest_key, "product_key": product_key, "warehouse_key": warehouse_key},
    ).one()

    # Inventory turnover = COGS over the period (fact_orders.extended_cost)
    # / average daily total inventory_value over the same period.
    cogs = conn.execute(
        text(
            "SELECT COALESCE(SUM(fo.extended_cost), 0) AS cogs FROM fact_orders fo "
            "WHERE (:product_key IS NULL OR fo.product_key = :product_key) "
            "AND (:date_from IS NULL OR fo.order_date_key >= :date_from) "
            "AND (:date_to IS NULL OR fo.order_date_key <= :date_to)"
        ),
        {
            "product_key": product_key,
            "date_from": params["date_from"],
            "date_to": params["date_to"],
        },
    ).scalar_one()

    avg_daily_value = conn.execute(
        text(
            "SELECT AVG(daily_total) FROM ("
            "  SELECT f.snapshot_date_key, SUM(f.inventory_value) AS daily_total "
            f"  FROM fact_inventory_snapshot f WHERE {_SNAPSHOT_FILTER} "
            "  GROUP BY f.snapshot_date_key"
            ") daily"
        ),
        params,
    ).scalar_one()

    turnover = float(cogs) / float(avg_daily_value) if avg_daily_value else None

    # Days of supply = latest total on-hand / average daily units sold
    # (fact_orders.allocated_quantity) over the same period.
    avg_daily_units_sold = conn.execute(
        text(
            "SELECT AVG(daily_units) FROM ("
            "  SELECT fo.order_date_key, SUM(fo.allocated_quantity) AS daily_units "
            "  FROM fact_orders fo "
            "  WHERE (:product_key IS NULL OR fo.product_key = :product_key) "
            "  AND (:date_from IS NULL OR fo.order_date_key >= :date_from) "
            "  AND (:date_to IS NULL OR fo.order_date_key <= :date_to) "
            "  GROUP BY fo.order_date_key"
            ") daily"
        ),
        {
            "product_key": product_key,
            "date_from": params["date_from"],
            "date_to": params["date_to"],
        },
    ).scalar_one()

    days_of_supply = (
        float(latest.on_hand) / float(avg_daily_units_sold) if avg_daily_units_sold else None
    )

    result = InventorySummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        latest_snapshot_date=latest.full_date,
        total_quantity_on_hand=int(latest.on_hand),
        total_inventory_value=float(latest.inventory_total_value),
        stockout_rate=float(latest.stockout_rate) if latest.stockout_rate is not None else None,
        inventory_turnover=turnover,
        days_of_supply=days_of_supply,
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[InventoryRow])
def get_inventory_detail(
    product_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> PageEnvelope[InventoryRow]:
    params = _base_params(product_key, warehouse_key, date_from, date_to)

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM fact_inventory_snapshot f WHERE {_SNAPSHOT_FILTER}"), params
    ).scalar_one()

    # Deliberately no JOIN to dim_date here (unlike the summary query
    # above, which only touches the single latest date): fact_inventory_
    # snapshot is the warehouse's largest table (1.8M rows), and with an
    # unfiltered WHERE, ordering by a joined dim_date.full_date instead of
    # the raw indexed snapshot_date_key int forces MySQL into a full
    # filesort across the whole table before LIMIT can apply — measured
    # as an 8+ second hang against the real dataset, not a hypothetical.
    # snapshot_date_key is YYYYMMDD, trivially convertible to a date in
    # Python — no DB-side join needed to get there.
    rows = conn.execute(
        text(
            "SELECT f.product_key, f.warehouse_key, f.snapshot_date_key, f.quantity_on_hand, "
            "f.quantity_available, f.inventory_value, f.is_stockout "
            "FROM fact_inventory_snapshot f "
            f"WHERE {_SNAPSHOT_FILTER} "
            "ORDER BY f.snapshot_date_key DESC, f.product_key, f.warehouse_key "
            "LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            InventoryRow(
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                snapshot_date=date(
                    r.snapshot_date_key // 10000,
                    (r.snapshot_date_key // 100) % 100,
                    r.snapshot_date_key % 100,
                ),
                quantity_on_hand=r.quantity_on_hand,
                quantity_available=r.quantity_available,
                inventory_value=float(r.inventory_value),
                is_stockout=bool(r.is_stockout),
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
