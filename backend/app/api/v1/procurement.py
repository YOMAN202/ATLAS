"""Procurement dashboard — PO-line-level view of what's been ordered
from suppliers (source: fact_procurement, grain: 1 row per PO line).
Distinct from the Supplier dashboard (fact_supplier_delivery), which
covers only lines that have actually been received and their delivery
performance — a PO line exists in fact_procurement as soon as it's
placed, well before any fact_supplier_delivery row exists for it.

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

router = APIRouter(prefix="/api/v1/dashboards/procurement", tags=["procurement"])


class ProcurementSummary(BaseModel):
    as_of: AsOf
    total_po_lines: int
    total_spend: float
    average_unit_cost: float | None
    ordered_quantity: int
    received_quantity: int
    receipt_rate: float | None
    quality_rejected_quantity: int
    quality_rejection_rate: float | None


class ProcurementRow(BaseModel):
    source_po_line_id: int
    po_number: str
    po_status_code: str
    supplier_key: int
    product_key: int
    warehouse_key: int
    ordered_quantity: int
    unit_cost: float
    extended_cost: float
    received_quantity: int
    quality_rejected_quantity: int


def _date_key(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _params(supplier_key, product_key, warehouse_key, date_from, date_to):
    return {
        "supplier_key": supplier_key,
        "product_key": product_key,
        "warehouse_key": warehouse_key,
        "date_from": _date_key(date_from),
        "date_to": _date_key(date_to),
    }


_FILTER_CLAUSE = (
    "(:supplier_key IS NULL OR fp.supplier_key = :supplier_key) "
    "AND (:product_key IS NULL OR fp.product_key = :product_key) "
    "AND (:warehouse_key IS NULL OR fp.warehouse_key = :warehouse_key) "
    "AND (:date_from IS NULL OR fp.order_date_key >= :date_from) "
    "AND (:date_to IS NULL OR fp.order_date_key <= :date_to)"
)


@router.get("", response_model=ProcurementSummary)
def get_procurement_summary(
    supplier_key: int | None = Query(None),
    product_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> ProcurementSummary:
    etl_run_id = get_current_etl_run_id(conn)
    params = _params(supplier_key, product_key, warehouse_key, date_from, date_to)
    key = cache_key("procurement_summary", etl_run_id, **params)
    cached = get_cached(key)
    if cached is not None:
        return cached

    row = conn.execute(
        text(
            "SELECT COUNT(*) AS line_count, COALESCE(SUM(fp.extended_cost), 0) AS spend, "
            "COALESCE(SUM(fp.ordered_quantity), 0) AS ordered, "
            "COALESCE(SUM(fp.received_quantity), 0) AS received, "
            "COALESCE(SUM(fp.quality_rejected_quantity), 0) AS rejected "
            f"FROM fact_procurement fp WHERE {_FILTER_CLAUSE}"
        ),
        params,
    ).one()

    result = ProcurementSummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        total_po_lines=int(row.line_count),
        total_spend=float(row.spend),
        average_unit_cost=(float(row.spend) / float(row.ordered)) if row.ordered else None,
        ordered_quantity=int(row.ordered),
        received_quantity=int(row.received),
        receipt_rate=(float(row.received) / float(row.ordered)) if row.ordered else None,
        quality_rejected_quantity=int(row.rejected),
        quality_rejection_rate=(
            (float(row.rejected) / float(row.received)) if row.received else None
        ),
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[ProcurementRow])
def get_procurement_detail(
    supplier_key: int | None = Query(None),
    product_key: int | None = Query(None),
    warehouse_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> PageEnvelope[ProcurementRow]:
    params = _params(supplier_key, product_key, warehouse_key, date_from, date_to)

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM fact_procurement fp WHERE {_FILTER_CLAUSE}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT fp.source_po_line_id, fp.po_number, fp.po_status_code, fp.supplier_key, "
            "fp.product_key, fp.warehouse_key, fp.ordered_quantity, "
            "fp.unit_cost, fp.extended_cost, "
            "fp.received_quantity, fp.quality_rejected_quantity "
            f"FROM fact_procurement fp WHERE {_FILTER_CLAUSE} "
            "ORDER BY fp.source_po_line_id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            ProcurementRow(
                source_po_line_id=r.source_po_line_id,
                po_number=r.po_number,
                po_status_code=r.po_status_code,
                supplier_key=r.supplier_key,
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                ordered_quantity=r.ordered_quantity,
                unit_cost=float(r.unit_cost),
                extended_cost=float(r.extended_cost),
                received_quantity=r.received_quantity,
                quality_rejected_quantity=r.quality_rejected_quantity,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
