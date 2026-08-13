"""Executive Overview dashboard (SRS FR-7.1). Every KPI here is
documented per docs/phase6-completion.md's KPI registry; summarized
inline in each query's docstring too, so the two can be cross-checked.

Role: executive, administrator (SEC-5) — the high-level summary view;
Operations Analyst/Supply Planner are not given this route, consistent
with SRS §3's actor descriptions (Executive Leadership: "revenue, cost,
service level, risk").
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.api.schemas import AsOf
from app.core.security import ADMINISTRATOR, EXECUTIVE, require_role

router = APIRouter(prefix="/api/v1/dashboards/executive", tags=["executive"])


class DailyRevenuePoint(BaseModel):
    full_date: date
    total_revenue: float
    total_gross_margin: float


class ExecutiveSummary(BaseModel):
    as_of: AsOf
    total_revenue: float
    total_gross_margin: float
    total_orders: int
    total_order_lines: int
    order_fulfillment_rate: float | None
    cost_to_serve: None = None
    cost_to_serve_note: str = (
        "Not computed — cost-to-serve requires an explicit policy definition "
        "(docs/phase6-dashboard-proposal.md §5.1), not a placeholder formula."
    )
    daily_trend: list[DailyRevenuePoint]


def _fetch_summary(
    conn: Connection,
    etl_run_id: int,
    region_key: int | None,
    date_from: date | None,
    date_to: date | None,
) -> ExecutiveSummary:
    """Revenue/margin/order-volume: summary_daily_revenue_by_region
    (grain: 1 row per region per day, pre-aggregated at ETL load time —
    ATLAS-TDD.md §8, "summary tables refreshed at ETL load, not query
    time"). Order fulfillment rate: fact_orders (grain: 1 row per order
    line) — the summary table has no quantity columns, so this one KPI
    genuinely comes from a different, second source table; documented
    here rather than left implicit."""

    date_from_key = int(date_from.strftime("%Y%m%d")) if date_from else None
    date_to_key = int(date_to.strftime("%Y%m%d")) if date_to else None

    totals = conn.execute(
        text(
            "SELECT COALESCE(SUM(total_revenue), 0) AS revenue, "
            "COALESCE(SUM(total_gross_margin), 0) AS margin, "
            "COALESCE(SUM(total_orders), 0) AS orders, "
            "COALESCE(SUM(total_order_lines), 0) AS order_lines "
            "FROM summary_daily_revenue_by_region "
            "WHERE (:region_key IS NULL OR region_key = :region_key) "
            "AND (:date_from IS NULL OR date_key >= :date_from) "
            "AND (:date_to IS NULL OR date_key <= :date_to)"
        ),
        {"region_key": region_key, "date_from": date_from_key, "date_to": date_to_key},
    ).one()

    fulfillment = conn.execute(
        text(
            "SELECT COALESCE(SUM(fo.allocated_quantity), 0) AS allocated, "
            "COALESCE(SUM(fo.ordered_quantity), 0) AS ordered "
            "FROM fact_orders fo "
            "JOIN dim_customer dc ON dc.customer_key = fo.customer_key "
            "WHERE (:region_key IS NULL OR dc.region_key = :region_key) "
            "AND (:date_from IS NULL OR fo.order_date_key >= :date_from) "
            "AND (:date_to IS NULL OR fo.order_date_key <= :date_to)"
        ),
        {"region_key": region_key, "date_from": date_from_key, "date_to": date_to_key},
    ).one()
    fulfillment_rate = (
        float(fulfillment.allocated) / float(fulfillment.ordered) if fulfillment.ordered else None
    )

    trend_rows = conn.execute(
        text(
            "SELECT dd.full_date, SUM(s.total_revenue) AS revenue, "
            "SUM(s.total_gross_margin) AS margin "
            "FROM summary_daily_revenue_by_region s "
            "JOIN dim_date dd ON dd.date_key = s.date_key "
            "WHERE (:region_key IS NULL OR s.region_key = :region_key) "
            "AND (:date_from IS NULL OR s.date_key >= :date_from) "
            "AND (:date_to IS NULL OR s.date_key <= :date_to) "
            "GROUP BY dd.full_date ORDER BY dd.full_date"
        ),
        {"region_key": region_key, "date_from": date_from_key, "date_to": date_to_key},
    ).all()

    return ExecutiveSummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        total_revenue=float(totals.revenue),
        total_gross_margin=float(totals.margin),
        total_orders=int(totals.orders),
        total_order_lines=int(totals.order_lines),
        order_fulfillment_rate=fulfillment_rate,
        daily_trend=[
            DailyRevenuePoint(
                full_date=r.full_date,
                total_revenue=float(r.revenue),
                total_gross_margin=float(r.margin),
            )
            for r in trend_rows
        ],
    )


@router.get("", response_model=ExecutiveSummary)
def get_executive_summary(
    region_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(EXECUTIVE, ADMINISTRATOR)),
) -> ExecutiveSummary:
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key(
        "executive", etl_run_id, region_key=region_key, date_from=date_from, date_to=date_to
    )
    cached = get_cached(key)
    if cached is not None:
        return cached
    result = _fetch_summary(conn, etl_run_id, region_key, date_from, date_to)
    set_cached(key, result)
    return result
