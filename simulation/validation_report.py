"""Post-run validation analytics: reads a just-populated OLTP dataset and
prints procurement volume, backorder frequency, inventory turnover, ABC
demand distribution, and supplier utilization. Read-only — never mutates
the dataset a validation run produced. Reusable across validation rounds
(and the eventual full 5-year run) so every report is computed the same
way and is directly comparable.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from simulation.config.world_state import DEFAULT_VALIDATION_CONFIG
from simulation.db import make_session_factory


def _print_header(title: str) -> None:
    print(f"\n--- {title} ---", flush=True)


def report_record_counts(session: Session) -> None:
    _print_header("Record Counts")
    tables = [
        "warehouses",
        "warehouse_zones",
        "products",
        "suppliers",
        "customers",
        "carriers",
        "orders",
        "order_lines",
        "purchase_orders",
        "purchase_order_lines",
        "shipments",
        "returns",
        "return_lines",
        "inventory_positions",
        "inventory_transactions",
    ]
    for table in tables:
        count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        print(f"{table}: {count}", flush=True)


def report_procurement_volume(session: Session, num_days: int) -> None:
    _print_header("Procurement Volume")
    po_count, total_ordered_units, distinct_products_reordered = session.execute(
        text(
            """
            SELECT COUNT(DISTINCT po.id), COALESCE(SUM(pol.ordered_quantity), 0),
                   COUNT(DISTINCT pol.product_id)
            FROM purchase_orders po
            JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
            """
        )
    ).one()
    print(f"purchase_orders_created: {po_count}", flush=True)
    print(f"total_units_ordered: {total_ordered_units}", flush=True)
    print(f"distinct_products_reordered: {distinct_products_reordered}", flush=True)
    print(
        f"purchase_orders_per_day (avg): " f"{(po_count / num_days) if num_days else 0:.2f}",
        flush=True,
    )

    fulfilled_count = session.execute(
        text(
            """
            SELECT COUNT(*) FROM purchase_orders po
            JOIN po_statuses s ON s.id = po.status_id
            WHERE s.code = 'FULFILLED'
            """
        )
    ).scalar_one()
    print(f"purchase_orders_fulfilled: {fulfilled_count}", flush=True)


def report_backorder_frequency(session: Session) -> None:
    _print_header("Backorder Frequency")
    total_lines, backordered_lines, total_ordered, total_backordered = session.execute(
        text(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN backordered_quantity > 0 THEN 1 ELSE 0 END),
                   COALESCE(SUM(ordered_quantity), 0),
                   COALESCE(SUM(backordered_quantity), 0)
            FROM order_lines
            """
        )
    ).one()
    line_rate = (backordered_lines / total_lines * 100) if total_lines else 0.0
    unit_rate = (total_backordered / total_ordered * 100) if total_ordered else 0.0
    print(f"order_lines_total: {total_lines}", flush=True)
    print(
        f"order_lines_with_backorder: {backordered_lines} ({line_rate:.3f}% of lines)", flush=True
    )
    print(
        f"units_backordered: {total_backordered} / {total_ordered} ordered "
        f"({unit_rate:.3f}% of units)",
        flush=True,
    )


def report_inventory_turnover(session: Session, num_days: int) -> None:
    _print_header("Inventory Turnover")
    # Units shipped is used as the "units sold" side of the ratio — the
    # units that actually left inventory during the window.
    units_shipped = int(
        session.execute(
            text(
                """
                SELECT COALESCE(SUM(it.quantity_delta), 0) * -1
                FROM inventory_transactions it
                JOIN inventory_transaction_types t ON t.id = it.transaction_type_id
                WHERE t.code = 'PICK'
                """
            )
        ).scalar_one()
    )

    initial_units_raw, current_units_raw = session.execute(
        text(
            """
            SELECT
                (SELECT COALESCE(SUM(it.quantity_delta), 0)
                 FROM inventory_transactions it
                 JOIN inventory_transaction_types t ON t.id = it.transaction_type_id
                 WHERE t.code = 'RECEIPT' AND it.source_reference_type = 'world_init'),
                (SELECT COALESCE(SUM(quantity_on_hand), 0) FROM inventory_positions)
            """
        )
    ).one()
    initial_units = int(initial_units_raw)
    current_units = int(current_units_raw)

    avg_inventory = (initial_units + current_units) / 2 if (initial_units + current_units) else 1
    turnover_ratio = units_shipped / avg_inventory if avg_inventory else 0.0
    annualized_turns = turnover_ratio * (365 / num_days) if num_days else 0.0

    print(f"units_shipped_in_window: {units_shipped}", flush=True)
    print(f"initial_total_inventory_units: {initial_units}", flush=True)
    print(f"final_total_inventory_units: {current_units}", flush=True)
    print(f"avg_inventory_units (2-point approximation): {avg_inventory:.0f}", flush=True)
    print(f"turnover_ratio_over_window: {turnover_ratio:.3f}", flush=True)
    print(f"annualized_turns_per_year: {annualized_turns:.2f}", flush=True)


def report_demand_distribution(session: Session) -> None:
    """ABC classification on REALIZED demand (actual order_lines generated),
    not the theoretical Zipf weight assigned at world-init — this is the
    direct evidence that the calibration change produced concentrated
    demand in the actual dataset, not just in the input assignment.
    """

    _print_header("Demand Distribution (ABC Classification, by realized units ordered)")
    rows = session.execute(
        text(
            """
            SELECT product_id, SUM(ordered_quantity) AS units
            FROM order_lines
            GROUP BY product_id
            ORDER BY units DESC
            """
        )
    ).all()

    units_by_product = [r.units for r in rows]
    total_units = sum(units_by_product)
    n = len(units_by_product)
    top_20_n = max(1, round(n * 0.20))
    mid_30_n = max(1, round(n * 0.30))

    top_20_units = sum(units_by_product[:top_20_n])
    mid_30_units = sum(units_by_product[top_20_n : top_20_n + mid_30_n])
    bottom_50_units = sum(units_by_product[top_20_n + mid_30_n :])

    def pct(x: int) -> float:
        return (x / total_units * 100) if total_units else 0.0

    print(f"products_with_any_demand: {n}", flush=True)
    print(f"total_units_ordered: {total_units}", flush=True)
    print(
        f"Top 20% of SKUs ({top_20_n} products): {top_20_units} units "
        f"({pct(top_20_units):.1f}% of demand)",
        flush=True,
    )
    print(
        f"Middle 30% of SKUs ({mid_30_n} products): {mid_30_units} units "
        f"({pct(mid_30_units):.1f}% of demand)",
        flush=True,
    )
    print(
        f"Remaining 50% of SKUs ({n - top_20_n - mid_30_n} products): "
        f"{bottom_50_units} units ({pct(bottom_50_units):.1f}% of demand)",
        flush=True,
    )


def report_supplier_utilization(session: Session, num_suppliers: int) -> None:
    _print_header("Supplier Utilization")
    rows = session.execute(
        text(
            """
            SELECT po.supplier_id, COUNT(DISTINCT po.id) AS po_count,
                   COALESCE(SUM(pol.ordered_quantity), 0) AS units
            FROM purchase_orders po
            JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
            GROUP BY po.supplier_id
            """
        )
    ).all()

    active_suppliers = len(rows)
    utilization_rate = (active_suppliers / num_suppliers * 100) if num_suppliers else 0.0
    print(f"suppliers_configured: {num_suppliers}", flush=True)
    print(
        f"suppliers_with_at_least_one_po: {active_suppliers} ({utilization_rate:.1f}%)",
        flush=True,
    )

    if rows:
        po_counts = sorted(r.po_count for r in rows)
        print(
            f"POs per active supplier: min={po_counts[0]}, "
            f"max={po_counts[-1]}, avg={sum(po_counts) / len(po_counts):.1f}",
            flush=True,
        )


def main() -> None:
    config = DEFAULT_VALIDATION_CONFIG
    factory = make_session_factory()
    session = factory()
    try:
        report_record_counts(session)
        report_procurement_volume(session, config.num_days)
        report_backorder_frequency(session)
        report_inventory_turnover(session, config.num_days)
        report_demand_distribution(session)
        report_supplier_utilization(session, config.num_suppliers)
    finally:
        session.close()


if __name__ == "__main__":
    main()
