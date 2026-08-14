"""fact_inventory_snapshot transform (ADR-020): a single set-based SQL
query against live `atlas_oltp` (not the JSON-staged snapshot — see
ADR-020 for why that's a deliberate, narrow, and safe exception), using
a CTE + window function to compute a continuous daily running balance
for every (product, warehouse) pair that ever had inventory activity.

Known, documented limitation: `quantity_reserved` has no historical
ledger in OLTP (Phase 2's own design: "Reserving does not append to the
transaction ledger, because nothing physically moved yet" —
backend/app/domains/inventory/service.py) — only its *current* value is
ever knowable. Every historical day's `quantity_reserved` is therefore
0 here; only the most recent day uses the real current value from
`inventory_positions`. This is a genuine source-data limitation, not an
implementation shortcut — stated plainly rather than faking a history
that does not exist.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from etl.transform.surrogate_keys import date_key_for

_RUNNING_BALANCE_QUERY = text(
    """
    WITH active_pairs AS (
        SELECT DISTINCT ip.product_id, ip.warehouse_id
        FROM inventory_transactions it
        JOIN inventory_positions ip ON ip.id = it.inventory_position_id
    ),
    bounds AS (
        SELECT MIN(DATE(occurred_at)) AS min_day, MAX(DATE(occurred_at)) AS max_day
        FROM inventory_transactions
    ),
    calendar_grid AS (
        SELECT ap.product_id, ap.warehouse_id, d.day
        FROM active_pairs ap
        CROSS JOIN (
            SELECT DATE_ADD(b.min_day, INTERVAL seq.n DAY) AS day
            FROM bounds b
            JOIN (
                SELECT (t100.n * 100 + t10.n * 10 + t1.n) AS n
                FROM (SELECT 0 AS n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3
                      UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7
                      UNION SELECT 8 UNION SELECT 9) t1
                CROSS JOIN (SELECT 0 AS n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3
                            UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7
                            UNION SELECT 8 UNION SELECT 9) t10
                CROSS JOIN (SELECT 0 AS n UNION SELECT 1 UNION SELECT 2 UNION SELECT 3
                            UNION SELECT 4 UNION SELECT 5 UNION SELECT 6 UNION SELECT 7
                            UNION SELECT 8 UNION SELECT 9) t100
            ) seq
            WHERE DATE_ADD(b.min_day, INTERVAL seq.n DAY) <= b.max_day
        ) d
    ),
    daily_deltas AS (
        SELECT ip.product_id, ip.warehouse_id, DATE(it.occurred_at) AS day,
               SUM(it.quantity_delta) AS day_delta
        FROM inventory_transactions it
        JOIN inventory_positions ip ON ip.id = it.inventory_position_id
        GROUP BY ip.product_id, ip.warehouse_id, DATE(it.occurred_at)
    )
    SELECT
        g.product_id,
        g.warehouse_id,
        g.day,
        SUM(COALESCE(dd.day_delta, 0)) OVER (
            PARTITION BY g.product_id, g.warehouse_id ORDER BY g.day
            ROWS UNBOUNDED PRECEDING
        ) AS quantity_on_hand
    FROM calendar_grid g
    LEFT JOIN daily_deltas dd
        ON dd.product_id = g.product_id AND dd.warehouse_id = g.warehouse_id AND dd.day = g.day
    ORDER BY g.product_id, g.warehouse_id, g.day
    """
)

_CURRENT_RESERVED_QUERY = text(
    "SELECT product_id, warehouse_id, SUM(quantity_reserved) AS reserved "
    "FROM inventory_positions GROUP BY product_id, warehouse_id"
)


def build_fact_inventory_snapshot_rows(
    oltp_conn: Connection,
    product_key_by_id: dict[int, int],
    warehouse_key_by_id: dict[int, int],
    product_unit_cost_by_id: dict[int, object],
) -> tuple[list[dict], list[tuple[int | None, str, str]]]:
    rows = oltp_conn.execute(_RUNNING_BALANCE_QUERY).all()
    if not rows:
        return [], []

    current_reserved = {
        (r.product_id, r.warehouse_id): r.reserved
        for r in oltp_conn.execute(_CURRENT_RESERVED_QUERY).all()
    }

    max_day: date = max(r.day for r in rows)

    result: list[dict] = []
    quarantine: list[tuple[int | None, str, str]] = []

    for r in rows:
        product_key = product_key_by_id.get(r.product_id)
        warehouse_key = warehouse_key_by_id.get(r.warehouse_id)
        if product_key is None or warehouse_key is None:
            # Synthetic composite id for the quarantine record — this
            # fact has no single OLTP source row id (it's a rollup).
            quarantine.append(
                (
                    None,
                    "DQ-3",
                    f"product_key/warehouse_key unresolved for product_id={r.product_id}, "
                    f"warehouse_id={r.warehouse_id}",
                )
            )
            continue

        quantity_on_hand = int(r.quantity_on_hand)
        quantity_reserved = (
            int(current_reserved.get((r.product_id, r.warehouse_id), 0)) if r.day == max_day else 0
        )
        quantity_available = quantity_on_hand - quantity_reserved
        unit_cost = product_unit_cost_by_id[r.product_id]

        result.append(
            {
                "snapshot_date_key": date_key_for(r.day),
                "product_key": product_key,
                "warehouse_key": warehouse_key,
                "quantity_on_hand": quantity_on_hand,
                "quantity_reserved": quantity_reserved,
                "quantity_available": quantity_available,
                "inventory_value": unit_cost * quantity_on_hand,
                "is_stockout": quantity_on_hand == 0,
            }
        )

    return result, quarantine
