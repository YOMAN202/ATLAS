"""Stage B orchestration: Transform -> Load -> Reconcile, once per
warehouse object (7 dimensions, 6 facts, 1 summary table), in the
dimension-then-fact order that guarantees any dimension a fact
references is already loaded (ADR-019). Each object gets its own
etl_run_table_metrics row (keyed by warehouse object name, distinct
from Stage A's OLTP-table-keyed rows) and its own transaction (ADR-018).
"""

import time
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.audit.metrics import TableMetrics, record_and_log
from etl.load.dimensions import upsert_scd2_dimension, upsert_type1_dimension
from etl.load.facts import upsert_fact
from etl.reconcile import reconcile_fact
from etl.transform.dimensions import (
    build_dim_carrier_rows,
    build_dim_customer_rows,
    build_dim_product_rows,
    build_dim_region_rows,
    build_scd2_supplier_candidates,
    build_scd2_warehouse_candidates,
)
from etl.transform.facts import (
    build_fact_orders_rows,
    build_fact_procurement_rows,
    build_fact_returns_rows,
    build_fact_shipments_rows,
    build_fact_supplier_delivery_rows,
)
from etl.transform.inventory_snapshot import build_fact_inventory_snapshot_rows
from etl.transform.parsing import parse_date
from etl.transform.staging_reader import (
    read_staged,
    read_staged_by_id,
    read_staged_fields,
    read_staged_subset_by_id,
)
from etl.transform.surrogate_keys import resolve_scd2_as_of, resolve_type1


def _log_object(
    olap_conn: Connection,
    etl_run_id: int,
    name: str,
    extracted_count: int,
    quarantined_count: int,
    transform_seconds: float,
    load_seconds: float,
    reconcile_seconds: float,
    counts,
) -> None:
    record_and_log(
        olap_conn,
        etl_run_id,
        TableMetrics(
            source_table=name,
            extracted_count=extracted_count,
            quarantined_count=quarantined_count,
            rejected_count=0,
            inserted_count=counts.inserted,
            updated_count=counts.updated,
            unchanged_count=counts.unchanged,
            transform_seconds=round(transform_seconds, 3),
            load_seconds=round(load_seconds, 3),
            reconcile_seconds=round(reconcile_seconds, 3),
        ),
    )


def _lookup_vehicle_types(oltp_conn: Connection) -> dict[int, dict]:
    rows = oltp_conn.execute(
        text("SELECT id, code, name, capacity_units, cost_per_mile FROM vehicle_types")
    ).mappings().all()
    return {row["id"]: dict(row) for row in rows}


def _lookup_codes(oltp_conn: Connection, table: str) -> dict[int, str]:
    rows = oltp_conn.execute(text(f"SELECT id, code FROM {table}")).all()
    return {row[0]: row[1] for row in rows}


# --- Dimensions --------------------------------------------------------


def process_dim_region(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "regions")
    rows = build_dim_region_rows(staged)
    t1 = time.perf_counter()
    counts = upsert_type1_dimension(olap_conn, "dim_region", "region_id", rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "dim_region", ("region_id",), len(rows))
    t3 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_region", len(staged), 0, t1 - t0, t2 - t1, t3 - t2, counts)
    assert result.grain_violations == 0, f"dim_region grain violation: {result}"


def process_dim_product(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "products")
    rows = build_dim_product_rows(staged)
    t1 = time.perf_counter()
    counts = upsert_type1_dimension(olap_conn, "dim_product", "product_id", rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "dim_product", ("product_id",), len(rows))
    t3 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_product", len(staged), 0, t1 - t0, t2 - t1, t3 - t2, counts)
    assert result.grain_violations == 0, f"dim_product grain violation: {result}"


def process_dim_carrier(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "carriers")
    vehicle_types = _lookup_vehicle_types(oltp_conn)
    rows = build_dim_carrier_rows(staged, vehicle_types)
    t1 = time.perf_counter()
    counts = upsert_type1_dimension(olap_conn, "dim_carrier", "carrier_id", rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "dim_carrier", ("carrier_id",), len(rows))
    t3 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_carrier", len(staged), 0, t1 - t0, t2 - t1, t3 - t2, counts)
    assert result.grain_violations == 0, f"dim_carrier grain violation: {result}"


def process_dim_customer(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "customers")
    region_key_by_id = resolve_type1(olap_conn, "dim_region", "region_id")
    rows = build_dim_customer_rows(staged, region_key_by_id)
    t1 = time.perf_counter()
    counts = upsert_type1_dimension(olap_conn, "dim_customer", "customer_id", rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "dim_customer", ("customer_id",), len(rows))
    t3 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_customer", len(staged), 0, t1 - t0, t2 - t1, t3 - t2, counts)
    assert result.grain_violations == 0, f"dim_customer grain violation: {result}"


def process_dim_supplier(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "suppliers")
    candidates = build_scd2_supplier_candidates(staged)
    t1 = time.perf_counter()
    counts = upsert_scd2_dimension(
        olap_conn, "dim_supplier", "supplier_id", ("payment_terms_days", "default_lead_time_days"), candidates
    )
    t2 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_supplier", len(staged), 0, t1 - t0, t2 - t1, 0.0, counts)


def process_dim_warehouse(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    staged = read_staged(olap_conn, "warehouses")
    region_key_by_id = resolve_type1(olap_conn, "dim_region", "region_id")
    candidates = build_scd2_warehouse_candidates(staged, region_key_by_id)
    t1 = time.perf_counter()
    counts = upsert_scd2_dimension(
        olap_conn, "dim_warehouse", "warehouse_id", ("total_capacity_units",), candidates
    )
    t2 = time.perf_counter()
    _log_object(olap_conn, etl_run_id, "dim_warehouse", len(staged), 0, t1 - t0, t2 - t1, 0.0, counts)


# --- Facts ---------------------------------------------------------------


_ORDER_LINE_FIELDS = (
    "order_id", "product_id", "fulfillment_warehouse_id", "shipment_id",
    "allocated_quantity", "unit_price", "unit_cost", "line_number",
    "ordered_quantity", "backordered_quantity",
)


def process_fact_orders(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    # Targeted field reads (not full-payload read_staged/read_staged_by_id)
    # for all three source tables here: order_lines is the largest staged
    # table (732k+ rows) and fact_orders only needs 10 of its fields;
    # materializing every field of ~1.7M combined rows was a real
    # memory-footprint problem that crashed the process (and, at this
    # container's memory ceiling, Docker itself) — don't parse what you
    # don't use.
    order_line_fields = read_staged_fields(olap_conn, "order_lines", _ORDER_LINE_FIELDS)
    order_lines = [
        {
            "source_id": source_id,
            "order_id": int(order_id),
            "product_id": int(product_id),
            "fulfillment_warehouse_id": int(fwid) if fwid is not None else None,
            "shipment_id": int(shipment_id) if shipment_id is not None else None,
            "allocated_quantity": int(allocated_quantity),
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "line_number": int(line_number),
            "ordered_quantity": int(ordered_quantity),
            "backordered_quantity": int(backordered_quantity),
        }
        for source_id, (
            order_id, product_id, fwid, shipment_id, allocated_quantity, unit_price,
            unit_cost, line_number, ordered_quantity, backordered_quantity,
        ) in order_line_fields.items()
    ]
    orders_fields = read_staged_fields(olap_conn, "orders", ("customer_id", "order_date", "order_number"))
    orders_by_id = {
        oid: {"customer_id": int(cust_id), "order_date": order_date, "order_number": order_number}
        for oid, (cust_id, order_date, order_number) in orders_fields.items()
    }
    shipment_fields = read_staged_fields(olap_conn, "shipments", ("shipment_number",))
    shipment_number_by_id = {sid: num for sid, (num,) in shipment_fields.items()}

    product_key_by_id = resolve_type1(olap_conn, "dim_product", "product_id")
    customer_key_by_id = resolve_type1(olap_conn, "dim_customer", "customer_id")
    warehouse_key_by_id = resolve_type1(olap_conn, "dim_warehouse", "warehouse_id")  # see note below

    rows, quarantine = build_fact_orders_rows(
        order_lines, orders_by_id, product_key_by_id, customer_key_by_id, warehouse_key_by_id,
        shipment_number_by_id,
    )
    t1 = time.perf_counter()
    counts = upsert_fact(olap_conn, "fact_orders", ("source_order_line_id",), rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "fact_orders", ("source_order_line_id",), len(rows))
    t3 = time.perf_counter()
    _write_quarantine(olap_conn, etl_run_id, "order_lines", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_orders", len(order_lines), len(quarantine), t1 - t0, t2 - t1, t3 - t2, counts
    )
    assert result.grain_violations == 0, f"fact_orders grain violation: {result}"


_SHIPMENT_FIELDS = (
    "carrier_id", "origin_warehouse_id", "destination_warehouse_id", "destination_customer_id",
    "ship_date", "estimated_delivery_date", "actual_delivery_date", "shipment_number", "status_id",
    "distance_miles", "shipping_cost",
)


def process_fact_shipments(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    # Targeted field read (shipments is the second-largest staged table,
    # 696k+ rows) — same rationale as order_lines in process_fact_orders.
    shipment_fields = read_staged_fields(olap_conn, "shipments", _SHIPMENT_FIELDS)
    shipments = [
        {
            "source_id": source_id,
            "carrier_id": int(carrier_id),
            "origin_warehouse_id": int(origin_warehouse_id),
            "destination_warehouse_id": int(dest_warehouse_id) if dest_warehouse_id is not None else None,
            "destination_customer_id": int(dest_customer_id) if dest_customer_id is not None else None,
            "ship_date": ship_date,
            "estimated_delivery_date": est_date,
            "actual_delivery_date": actual_date,
            "shipment_number": shipment_number,
            "status_id": int(status_id),
            "distance_miles": distance_miles,
            "shipping_cost": shipping_cost,
        }
        for source_id, (
            carrier_id, origin_warehouse_id, dest_warehouse_id, dest_customer_id, ship_date, est_date,
            actual_date, shipment_number, status_id, distance_miles, shipping_cost,
        ) in shipment_fields.items()
    ]
    carrier_key_by_id = resolve_type1(olap_conn, "dim_carrier", "carrier_id")
    warehouse_key_by_id = resolve_type1(olap_conn, "dim_warehouse", "warehouse_id")
    customer_key_by_id = resolve_type1(olap_conn, "dim_customer", "customer_id")
    shipment_status_code_by_id = _lookup_codes(oltp_conn, "shipment_statuses")

    rows, quarantine = build_fact_shipments_rows(
        shipments, carrier_key_by_id, warehouse_key_by_id, customer_key_by_id, shipment_status_code_by_id
    )
    t1 = time.perf_counter()
    counts = upsert_fact(olap_conn, "fact_shipments", ("source_shipment_id",), rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "fact_shipments", ("source_shipment_id",), len(rows))
    t3 = time.perf_counter()
    _write_quarantine(olap_conn, etl_run_id, "shipments", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_shipments", len(shipments), len(quarantine), t1 - t0, t2 - t1, t3 - t2, counts
    )
    assert result.grain_violations == 0, f"fact_shipments grain violation: {result}"


def _resolve_supplier_warehouse_for_po_lines(
    olap_conn: Connection,
    po_lines: list[dict],
    purchase_orders_by_id: dict[int, dict],
    business_date_field: str | None,
) -> tuple[dict[int, int | None], dict[int, int | None]]:
    """Builds (row_id=po_line source_id, natural_id, business_date) query
    lists for supplier_key/warehouse_key resolution. `business_date_field`
    is None for fact_procurement (business date = the PO's own order_date)
    or a staged line-column name for fact_supplier_delivery (business
    date = that column, its actual_delivery_date) — the two facts resolve
    the same natural ids as of different dates (ADR-021)."""

    supplier_queries: list[tuple[int, int, date]] = []
    warehouse_queries: list[tuple[int, int, date]] = []
    for line in po_lines:
        po = purchase_orders_by_id.get(line["purchase_order_id"])
        if po is None:
            continue
        raw_date = line[business_date_field] if business_date_field else po["order_date"]
        business_date = parse_date(raw_date)
        if business_date is None:
            continue
        supplier_queries.append((line["source_id"], po["supplier_id"], business_date))
        warehouse_queries.append((line["source_id"], po["warehouse_id"], business_date))

    supplier_key_resolver = resolve_scd2_as_of(olap_conn, "dim_supplier", "supplier_id", supplier_queries)
    warehouse_key_resolver = resolve_scd2_as_of(olap_conn, "dim_warehouse", "warehouse_id", warehouse_queries)
    return supplier_key_resolver, warehouse_key_resolver


def process_fact_procurement(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    po_lines = read_staged(olap_conn, "purchase_order_lines")
    purchase_orders_by_id = read_staged_by_id(olap_conn, "purchase_orders")
    product_key_by_id = resolve_type1(olap_conn, "dim_product", "product_id")
    po_status_code_by_id = _lookup_codes(oltp_conn, "po_statuses")

    supplier_key_resolver, warehouse_key_resolver = _resolve_supplier_warehouse_for_po_lines(
        olap_conn, po_lines, purchase_orders_by_id, business_date_field=None
    )

    rows, quarantine = build_fact_procurement_rows(
        po_lines, purchase_orders_by_id, product_key_by_id, supplier_key_resolver, warehouse_key_resolver,
        po_status_code_by_id,
    )
    t1 = time.perf_counter()
    counts = upsert_fact(olap_conn, "fact_procurement", ("source_po_line_id",), rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "fact_procurement", ("source_po_line_id",), len(rows))
    t3 = time.perf_counter()
    _write_quarantine(olap_conn, etl_run_id, "purchase_order_lines", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_procurement", len(po_lines), len(quarantine), t1 - t0, t2 - t1, t3 - t2, counts
    )
    assert result.grain_violations == 0, f"fact_procurement grain violation: {result}"


def process_fact_supplier_delivery(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    po_lines = read_staged(olap_conn, "purchase_order_lines")
    purchase_orders_by_id = read_staged_by_id(olap_conn, "purchase_orders")
    product_key_by_id = resolve_type1(olap_conn, "dim_product", "product_id")

    delivered_lines = [line for line in po_lines if line.get("actual_delivery_date")]
    supplier_key_resolver, warehouse_key_resolver = _resolve_supplier_warehouse_for_po_lines(
        olap_conn, delivered_lines, purchase_orders_by_id, business_date_field="actual_delivery_date"
    )

    rows, quarantine = build_fact_supplier_delivery_rows(
        po_lines, purchase_orders_by_id, product_key_by_id, supplier_key_resolver, warehouse_key_resolver
    )
    t1 = time.perf_counter()
    counts = upsert_fact(olap_conn, "fact_supplier_delivery", ("source_po_line_id",), rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "fact_supplier_delivery", ("source_po_line_id",), len(rows))
    t3 = time.perf_counter()
    _write_quarantine(olap_conn, etl_run_id, "purchase_order_lines", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_supplier_delivery", len(delivered_lines), len(quarantine),
        t1 - t0, t2 - t1, t3 - t2, counts,
    )
    assert result.grain_violations == 0, f"fact_supplier_delivery grain violation: {result}"


def process_fact_returns(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    return_lines = read_staged(olap_conn, "return_lines")
    returns_by_id = read_staged_by_id(olap_conn, "returns")
    # Targeted subset reads, not full-table reads: order_lines/orders are
    # ~20x/~9x larger than what this fact actually needs (only the specific
    # rows return_lines/returns reference), so a full read_staged_by_id
    # here would parse hundreds of thousands of unused JSON payloads.
    order_line_ids = {line["order_line_id"] for line in return_lines}
    order_lines_by_id = read_staged_subset_by_id(olap_conn, "order_lines", order_line_ids)
    order_ids = {ret["order_id"] for ret in returns_by_id.values()}
    orders_by_id = read_staged_subset_by_id(olap_conn, "orders", order_ids)
    product_key_by_id = resolve_type1(olap_conn, "dim_product", "product_id")
    customer_key_by_id = resolve_type1(olap_conn, "dim_customer", "customer_id")
    reason_code_by_id = _lookup_codes(oltp_conn, "return_reasons")
    disposition_code_by_id = _lookup_codes(oltp_conn, "return_dispositions")

    rows, quarantine = build_fact_returns_rows(
        return_lines, returns_by_id, order_lines_by_id, orders_by_id, product_key_by_id,
        customer_key_by_id, reason_code_by_id, disposition_code_by_id,
    )
    t1 = time.perf_counter()
    counts = upsert_fact(olap_conn, "fact_returns", ("source_return_line_id",), rows)
    t2 = time.perf_counter()
    result = reconcile_fact(olap_conn, "fact_returns", ("source_return_line_id",), len(rows))
    t3 = time.perf_counter()
    _write_quarantine(olap_conn, etl_run_id, "return_lines", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_returns", len(return_lines), len(quarantine), t1 - t0, t2 - t1, t3 - t2, counts
    )
    assert result.grain_violations == 0, f"fact_returns grain violation: {result}"


def process_fact_inventory_snapshot(oltp_conn: Connection, olap_conn: Connection, etl_run_id: int) -> None:
    t0 = time.perf_counter()
    product_key_by_id = resolve_type1(olap_conn, "dim_product", "product_id")
    warehouse_key_by_id = resolve_type1(olap_conn, "dim_warehouse", "warehouse_id")
    product_unit_cost_by_id = oltp_conn.execute(
        text("SELECT id, unit_cost FROM products")
    ).all()
    product_unit_cost_by_id = {r[0]: r[1] for r in product_unit_cost_by_id}

    rows, quarantine = build_fact_inventory_snapshot_rows(
        oltp_conn, product_key_by_id, warehouse_key_by_id, product_unit_cost_by_id
    )
    t1 = time.perf_counter()
    counts = upsert_fact(
        olap_conn, "fact_inventory_snapshot", ("product_key", "warehouse_key", "snapshot_date_key"), rows
    )
    t2 = time.perf_counter()
    result = reconcile_fact(
        olap_conn, "fact_inventory_snapshot", ("product_key", "warehouse_key", "snapshot_date_key"), len(rows)
    )
    t3 = time.perf_counter()
    # A rollup fact has no single OLTP source row id per quarantine entry
    # (dq_quarantine.source_id is nullable for exactly this case).
    _write_quarantine(olap_conn, etl_run_id, "fact_inventory_snapshot", quarantine)
    _log_object(
        olap_conn, etl_run_id, "fact_inventory_snapshot", len(rows), len(quarantine),
        t1 - t0, t2 - t1, t3 - t2, counts,
    )
    assert result.grain_violations == 0, f"fact_inventory_snapshot grain violation: {result}"


def process_summary_daily_revenue_by_region(
    oltp_conn: Connection, olap_conn: Connection, etl_run_id: int
) -> None:
    t0 = time.perf_counter()
    olap_conn.execute(text("DELETE FROM summary_daily_revenue_by_region"))
    olap_conn.execute(
        text(
            "INSERT INTO summary_daily_revenue_by_region "
            "(region_key, date_key, total_orders, total_order_lines, total_revenue, total_gross_margin) "
            "SELECT dc.region_key, fo.order_date_key, "
            "       COUNT(DISTINCT fo.order_number), COUNT(*), "
            "       SUM(fo.extended_revenue), SUM(fo.gross_margin) "
            "FROM fact_orders fo "
            "JOIN dim_customer dc ON dc.customer_key = fo.customer_key "
            "GROUP BY dc.region_key, fo.order_date_key"
        )
    )
    row_count = olap_conn.execute(
        text("SELECT COUNT(*) FROM summary_daily_revenue_by_region")
    ).scalar_one()
    t1 = time.perf_counter()
    _log_object(
        olap_conn, etl_run_id, "summary_daily_revenue_by_region", row_count, 0, 0.0, t1 - t0, 0.0,
        type("Counts", (), {"inserted": row_count, "updated": 0, "unchanged": 0})(),
    )


def _write_quarantine(
    olap_conn: Connection, etl_run_id: int, source_table: str, quarantine: list[tuple[int, str, str]]
) -> None:
    if not quarantine:
        return
    from datetime import UTC, datetime

    from etl.validate.quarantine import quarantine_row

    now = datetime.now(UTC)
    for source_id, rule, detail in quarantine:
        quarantine_row(olap_conn, etl_run_id, source_table, source_id, rule, detail, None, now)
