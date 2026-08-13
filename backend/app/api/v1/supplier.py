"""Supplier dashboard (SRS FR-7.2) — delivery performance only (source:
fact_supplier_delivery, grain: 1 row per delivery event = a received PO
line). Risk score (SRS §15) is intentionally NOT implemented — it's
Phase 7 decision-support territory (FR-8.2), not a warehouse column.

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

router = APIRouter(prefix="/api/v1/dashboards/supplier", tags=["supplier"])


class SupplierSummary(BaseModel):
    as_of: AsOf
    total_deliveries: int
    on_time_delivery_rate: float | None
    average_lead_time_variance_days: float | None
    quality_rejection_rate: float | None
    risk_score: None = None
    risk_score_note: str = (
        "Not computed — supplier risk scoring is Phase 7 decision-support scope (SRS FR-8.2)."
    )


class SupplierDeliveryRow(BaseModel):
    source_po_line_id: int
    po_number: str
    supplier_key: int
    product_key: int
    warehouse_key: int
    received_quantity: int
    quality_rejected_quantity: int
    is_on_time: bool
    lead_time_variance_days: int


def _date_key(d: date | None) -> int | None:
    return int(d.strftime("%Y%m%d")) if d else None


def _params(supplier_key, product_key, date_from, date_to):
    return {
        "supplier_key": supplier_key,
        "product_key": product_key,
        "date_from": _date_key(date_from),
        "date_to": _date_key(date_to),
    }


_FILTER_CLAUSE = (
    "(:supplier_key IS NULL OR fsd.supplier_key = :supplier_key) "
    "AND (:product_key IS NULL OR fsd.product_key = :product_key) "
    "AND (:date_from IS NULL OR fsd.delivery_date_key >= :date_from) "
    "AND (:date_to IS NULL OR fsd.delivery_date_key <= :date_to)"
)


@router.get("", response_model=SupplierSummary)
def get_supplier_summary(
    supplier_key: int | None = Query(None),
    product_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> SupplierSummary:
    etl_run_id = get_current_etl_run_id(conn)
    params = _params(supplier_key, product_key, date_from, date_to)
    key = cache_key("supplier_summary", etl_run_id, **params)
    cached = get_cached(key)
    if cached is not None:
        return cached

    row = conn.execute(
        text(
            "SELECT COUNT(*) AS deliveries, "
            "AVG(CAST(fsd.is_on_time AS DECIMAL(10,4))) AS on_time_rate, "
            "AVG(fsd.lead_time_variance_days) AS avg_variance, "
            "COALESCE(SUM(fsd.quality_rejected_quantity), 0) AS rejected, "
            "COALESCE(SUM(fsd.received_quantity), 0) AS received "
            f"FROM fact_supplier_delivery fsd WHERE {_FILTER_CLAUSE}"
        ),
        params,
    ).one()

    result = SupplierSummary(
        as_of=AsOf(etl_run_id=etl_run_id, date_from=date_from, date_to=date_to),
        total_deliveries=int(row.deliveries),
        on_time_delivery_rate=float(row.on_time_rate) if row.on_time_rate is not None else None,
        average_lead_time_variance_days=(
            float(row.avg_variance) if row.avg_variance is not None else None
        ),
        quality_rejection_rate=(
            (float(row.rejected) / float(row.received)) if row.received else None
        ),
    )
    set_cached(key, result)
    return result


@router.get("/detail", response_model=PageEnvelope[SupplierDeliveryRow])
def get_supplier_detail(
    supplier_key: int | None = Query(None),
    product_key: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(OPERATIONS_ANALYST, EXECUTIVE, ADMINISTRATOR)),
) -> PageEnvelope[SupplierDeliveryRow]:
    params = _params(supplier_key, product_key, date_from, date_to)

    total = conn.execute(
        text(f"SELECT COUNT(*) FROM fact_supplier_delivery fsd WHERE {_FILTER_CLAUSE}"), params
    ).scalar_one()

    rows = conn.execute(
        text(
            "SELECT fsd.source_po_line_id, fsd.po_number, fsd.supplier_key, fsd.product_key, "
            "fsd.warehouse_key, fsd.received_quantity, fsd.quality_rejected_quantity, "
            "fsd.is_on_time, fsd.lead_time_variance_days "
            f"FROM fact_supplier_delivery fsd WHERE {_FILTER_CLAUSE} "
            "ORDER BY fsd.source_po_line_id LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    return PageEnvelope(
        data=[
            SupplierDeliveryRow(
                source_po_line_id=r.source_po_line_id,
                po_number=r.po_number,
                supplier_key=r.supplier_key,
                product_key=r.product_key,
                warehouse_key=r.warehouse_key,
                received_quantity=r.received_quantity,
                quality_rejected_quantity=r.quality_rejected_quantity,
                is_on_time=bool(r.is_on_time),
                lead_time_variance_days=r.lead_time_variance_days,
            )
            for r in rows
        ],
        page=page,
        page_size=page_size,
        total=int(total),
    )
