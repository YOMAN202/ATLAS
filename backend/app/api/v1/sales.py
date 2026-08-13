"""Sales dashboard — order-line-level detail, distinct from Executive's
high-level daily/regional rollup (SRS FR-7.1 vs. the "operational
dashboards" framing of FR-7.2; split per your approved dashboard
mapping). Source: fact_orders, grain: 1 row per order line.

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

router = APIRouter(prefix="/api/v1/dashboards/sales", tags=["sales"])


class SalesSummary(BaseModel):
    as_of: AsOf
    total_order_lines: int
    distinct_orders: int
    ordered_quantity: int
    allocated_quantity: int
    backordered_quantity: int
    fulfillment_rate: float | None
    average_order_value: float | None


class OrderLineRow(BaseModel):
    source_order_line_id: int
    order_number: str
    order_line_number: int
    product_key: int
    customer_key: int
    ordered_quantity: int
    allocated_quantity: int
    backordered_quantity: int
    unit_price: float
    extended_revenue: float
    gross_margin: float


def _date_key(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _params(product_key, customer_key, date_from, date_to):
    return {
        "product_key": product_key,
        "customer_key": customer_key,
        "date_from": _date_key(date_from),
        "date_to": _date_key(date_to),
    }


_FILTER_CLAUSE = (
    "(:product_key IS NULL OR fo.product_key = :product_key) "
    "AND (:customer_key IS NULL OR fo.customer_key = :customer_key) "
    "AND (:date_from IS NULL OR fo.order_date_key >= :date_from) "
    "AND (:date_to IS NULL OR fo.order_date_key <= :date_to)"
)


@router.get("", response_model=SalesSummary)
def get_sales_summary(
    product_key: int | None = Query(None),
    customer_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> SalesSummary:
    etl_run_id = get_current_etl_run_id(conn)
    params = _params(product_key, customer_key, date_from, date_to)
    key = cache_key("sales_summary", etl_run_id, **params)
    cached = get_cached(key)
    if cached is not None:
        return cached

    row = conn.execute(
        text(
            "SELECT COUNT(*) AS line_count, COUNT(DISTINCT fo.order_number) AS orders, "
            "COALESCE(SUM(fo.ordered_quantity), 0) AS ordered, "
            "COALESCE(SUM(fo.allocated_quantity), 0) AS allocated, "
            "COALESCE(SUM(fo.backordered_quantity), 0) AS backordered, "
            "COALESCE(SUM(fo.extended_revenue), 0) AS revenue "
            f"FROM fact_orders fo WHERE {_FILTER_CLAUSE}"
        ),
        params,
    ).one()

    result = SalesSummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        total_order_lines=int(row.line_count),
        distinct_orders=int(row.orders),
        ordered_quantity=int(row.ordered),
        allocated_quantity=int(row.allocated),
        backordered_quantity=int(row.backordered),
        fulfillment_rate=(float(row.allocated) / float(row.ordered)) if row.ordered else None,
        average_order_value=(float(row.revenue) / int(row.orders)) if row.orders else None,
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[OrderLineRow])
def get_sales_detail(
    product_key: int | None = Query(None),
    customer_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> PageEnvelope[OrderLineRow]:
    params = _params(product_key, customer_key, date_from, date_to)

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM fact_orders fo WHERE {_FILTER_CLAUSE}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT fo.source_order_line_id, fo.order_number, "
            "fo.order_line_number, fo.product_key, "
            "fo.customer_key, fo.ordered_quantity, fo.allocated_quantity, fo.backordered_quantity, "
            "fo.unit_price, fo.extended_revenue, fo.gross_margin "
            f"FROM fact_orders fo WHERE {_FILTER_CLAUSE} "
            "ORDER BY fo.source_order_line_id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            OrderLineRow(
                source_order_line_id=r.source_order_line_id,
                order_number=r.order_number,
                order_line_number=r.order_line_number,
                product_key=r.product_key,
                customer_key=r.customer_key,
                ordered_quantity=r.ordered_quantity,
                allocated_quantity=r.allocated_quantity,
                backordered_quantity=r.backordered_quantity,
                unit_price=float(r.unit_price),
                extended_revenue=float(r.extended_revenue),
                gross_margin=float(r.gross_margin),
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
