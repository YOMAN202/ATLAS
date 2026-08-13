"""Pure row-building for the 5 "standard" facts (order line / shipment /
PO line / return line grain — all 1:1 with a staged source row).
`fact_inventory_snapshot` is a rollup, not 1:1, and lives in its own
module (etl/transform/inventory_snapshot.py) since its transform is
fundamentally a set-based SQL window-function query, not a per-row
Python mapping.

Every builder returns (rows, quarantine_entries) — a row that can't
resolve a required surrogate key is never silently dropped or loaded
with a null/guessed key; it becomes a DQ-3 quarantine entry instead
(ADR-019/ADR-021), with the specific unresolved reference and business
date recorded.
"""

from etl.transform.parsing import parse_date, parse_decimal
from etl.transform.surrogate_keys import date_key_for

QuarantineEntry = tuple[int, str, str]  # (source_id, rule, detail)


def build_fact_orders_rows(
    order_lines: list[dict],
    orders_by_id: dict[int, dict],
    product_key_by_id: dict[int, int],
    customer_key_by_id: dict[int, int],
    warehouse_key_by_id: dict[int, int],
    shipment_number_by_id: dict[int, str],
) -> tuple[list[dict], list[QuarantineEntry]]:
    rows: list[dict] = []
    quarantine: list[QuarantineEntry] = []

    for line in order_lines:
        order = orders_by_id.get(line["order_id"])
        if order is None:
            quarantine.append(
                (line["source_id"], "DQ-3", f"order_id {line['order_id']} not found in staged orders")
            )
            continue

        product_key = product_key_by_id.get(line["product_id"])
        customer_key = customer_key_by_id.get(order["customer_id"])
        if product_key is None or customer_key is None:
            quarantine.append(
                (
                    line["source_id"],
                    "DQ-3",
                    f"product_key or customer_key unresolved (product_id={line['product_id']}, "
                    f"customer_id={order['customer_id']})",
                )
            )
            continue

        fulfillment_warehouse_id = line.get("fulfillment_warehouse_id")
        fulfillment_warehouse_key = (
            warehouse_key_by_id.get(fulfillment_warehouse_id)
            if fulfillment_warehouse_id is not None
            else None
        )
        shipment_id = line.get("shipment_id")

        allocated = line["allocated_quantity"]
        unit_price = parse_decimal(line["unit_price"])
        unit_cost = parse_decimal(line["unit_cost"])
        extended_revenue = unit_price * allocated
        extended_cost = unit_cost * allocated

        rows.append(
            {
                "source_order_line_id": line["source_id"],
                "order_number": order["order_number"],
                "order_line_number": line["line_number"],
                "shipment_number": shipment_number_by_id.get(shipment_id) if shipment_id else None,
                "order_date_key": date_key_for(parse_date(order["order_date"])),
                "product_key": product_key,
                "customer_key": customer_key,
                "fulfillment_warehouse_key": fulfillment_warehouse_key,
                "ordered_quantity": line["ordered_quantity"],
                "allocated_quantity": allocated,
                "backordered_quantity": line["backordered_quantity"],
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "extended_revenue": extended_revenue,
                "extended_cost": extended_cost,
                "gross_margin": extended_revenue - extended_cost,
            }
        )

    return rows, quarantine


def build_fact_shipments_rows(
    shipments: list[dict],
    carrier_key_by_id: dict[int, int],
    warehouse_key_by_id: dict[int, int],
    customer_key_by_id: dict[int, int],
    shipment_status_code_by_id: dict[int, str],
) -> tuple[list[dict], list[QuarantineEntry]]:
    rows: list[dict] = []
    quarantine: list[QuarantineEntry] = []

    for shipment in shipments:
        carrier_key = carrier_key_by_id.get(shipment["carrier_id"])
        origin_key = warehouse_key_by_id.get(shipment["origin_warehouse_id"])
        if carrier_key is None or origin_key is None:
            quarantine.append(
                (shipment["source_id"], "DQ-3", "carrier_key or origin_warehouse_key unresolved")
            )
            continue

        dest_warehouse_id = shipment.get("destination_warehouse_id")
        dest_customer_id = shipment.get("destination_customer_id")
        dest_warehouse_key = warehouse_key_by_id.get(dest_warehouse_id) if dest_warehouse_id else None
        dest_customer_key = customer_key_by_id.get(dest_customer_id) if dest_customer_id else None

        ship_date = parse_date(shipment["ship_date"])
        est_date = parse_date(shipment.get("estimated_delivery_date"))
        actual_date = parse_date(shipment.get("actual_delivery_date"))
        is_on_time = None
        if actual_date is not None and est_date is not None:
            is_on_time = actual_date <= est_date

        rows.append(
            {
                "source_shipment_id": shipment["source_id"],
                "shipment_number": shipment["shipment_number"],
                "status_code": shipment_status_code_by_id[shipment["status_id"]],
                "carrier_key": carrier_key,
                "origin_warehouse_key": origin_key,
                "destination_warehouse_key": dest_warehouse_key,
                "destination_customer_key": dest_customer_key,
                "ship_date_key": date_key_for(ship_date) if ship_date else None,
                "estimated_delivery_date_key": date_key_for(est_date) if est_date else None,
                "actual_delivery_date_key": date_key_for(actual_date) if actual_date else None,
                "distance_miles": parse_decimal(shipment.get("distance_miles")),
                "shipping_cost": parse_decimal(shipment.get("shipping_cost")),
                "is_on_time": is_on_time,
                "transit_days": (
                    (actual_date - ship_date).days if actual_date and ship_date else None
                ),
            }
        )

    return rows, quarantine


def build_fact_procurement_rows(
    po_lines: list[dict],
    purchase_orders_by_id: dict[int, dict],
    product_key_by_id: dict[int, int],
    supplier_key_resolver,
    warehouse_key_resolver,
    po_status_code_by_id: dict[int, str],
) -> tuple[list[dict], list[QuarantineEntry]]:
    """supplier_key_resolver/warehouse_key_resolver: {po_line_source_id: key_or_None},
    pre-resolved by the caller via resolve_scd2_as_of (business date =
    the PO's order_date) since that resolution needs a bulk DB query
    keyed by (natural_id, date) pairs across the whole batch."""

    rows: list[dict] = []
    quarantine: list[QuarantineEntry] = []

    for line in po_lines:
        po = purchase_orders_by_id.get(line["purchase_order_id"])
        if po is None:
            quarantine.append(
                (line["source_id"], "DQ-3", f"purchase_order_id {line['purchase_order_id']} not found")
            )
            continue

        product_key = product_key_by_id.get(line["product_id"])
        supplier_key = supplier_key_resolver.get(line["source_id"])
        warehouse_key = warehouse_key_resolver.get(line["source_id"])
        if product_key is None or supplier_key is None or warehouse_key is None:
            quarantine.append(
                (
                    line["source_id"],
                    "DQ-3",
                    f"product_key/supplier_key/warehouse_key unresolved as of order_date "
                    f"{po['order_date']}",
                )
            )
            continue

        ordered_quantity = line["ordered_quantity"]
        unit_cost = parse_decimal(line["unit_cost"])
        expected_date = parse_date(po.get("expected_delivery_date"))

        rows.append(
            {
                "source_po_line_id": line["source_id"],
                "po_number": po["po_number"],
                "po_line_number": line["line_number"],
                "po_status_code": po_status_code_by_id[po["status_id"]],
                "supplier_key": supplier_key,
                "product_key": product_key,
                "warehouse_key": warehouse_key,
                "order_date_key": date_key_for(parse_date(po["order_date"])),
                "expected_delivery_date_key": date_key_for(expected_date) if expected_date else None,
                "ordered_quantity": ordered_quantity,
                "unit_cost": unit_cost,
                "extended_cost": unit_cost * ordered_quantity,
                "received_quantity": line["received_quantity"],
                "quality_rejected_quantity": line["quality_rejected_quantity"],
            }
        )

    return rows, quarantine


def build_fact_supplier_delivery_rows(
    po_lines: list[dict],
    purchase_orders_by_id: dict[int, dict],
    product_key_by_id: dict[int, int],
    supplier_key_resolver,
    warehouse_key_resolver,
) -> tuple[list[dict], list[QuarantineEntry]]:
    """Only PO lines that have actually been received (actual_delivery_date
    set) produce a row here — fact_procurement exists as soon as the line
    does, fact_supplier_delivery only once it's been received (ADR-013/
    the fact_procurement vs fact_supplier_delivery distinction, Phase 4).
    supplier_key_resolver/warehouse_key_resolver are keyed by the
    *delivery* date here, not order_date (a different resolution than
    fact_procurement's, per ADR-021)."""

    rows: list[dict] = []
    quarantine: list[QuarantineEntry] = []

    for line in po_lines:
        if not line.get("actual_delivery_date"):
            continue  # not yet delivered — no fact_supplier_delivery row yet

        po = purchase_orders_by_id.get(line["purchase_order_id"])
        if po is None:
            quarantine.append(
                (line["source_id"], "DQ-3", f"purchase_order_id {line['purchase_order_id']} not found")
            )
            continue

        product_key = product_key_by_id.get(line["product_id"])
        supplier_key = supplier_key_resolver.get(line["source_id"])
        warehouse_key = warehouse_key_resolver.get(line["source_id"])
        if product_key is None or supplier_key is None or warehouse_key is None:
            quarantine.append(
                (
                    line["source_id"],
                    "DQ-3",
                    f"product_key/supplier_key/warehouse_key unresolved as of delivery_date "
                    f"{line['actual_delivery_date']}",
                )
            )
            continue

        delivery_date = parse_date(line["actual_delivery_date"])
        expected_date = parse_date(po.get("expected_delivery_date"))
        received = line["received_quantity"]
        rejected = line["quality_rejected_quantity"]
        is_on_time = expected_date is not None and delivery_date <= expected_date
        variance_days = (delivery_date - expected_date).days if expected_date else None

        rows.append(
            {
                "source_po_line_id": line["source_id"],
                "po_number": po["po_number"],
                "po_line_number": line["line_number"],
                "supplier_key": supplier_key,
                "product_key": product_key,
                "warehouse_key": warehouse_key,
                "delivery_date_key": date_key_for(delivery_date),
                "expected_delivery_date_key": date_key_for(expected_date) if expected_date else None,
                "ordered_quantity": line["ordered_quantity"],
                "received_quantity": received,
                "quality_rejected_quantity": rejected,
                "quality_accepted_quantity": received - rejected,
                "is_on_time": is_on_time,
                "lead_time_variance_days": variance_days,
            }
        )

    return rows, quarantine


def build_fact_returns_rows(
    return_lines: list[dict],
    returns_by_id: dict[int, dict],
    order_lines_by_id: dict[int, dict],
    orders_by_id: dict[int, dict],
    product_key_by_id: dict[int, int],
    customer_key_by_id: dict[int, int],
    reason_code_by_id: dict[int, str],
    disposition_code_by_id: dict[int, str],
) -> tuple[list[dict], list[QuarantineEntry]]:
    rows: list[dict] = []
    quarantine: list[QuarantineEntry] = []

    for line in return_lines:
        ret = returns_by_id.get(line["return_id"])
        order_line = order_lines_by_id.get(line["order_line_id"])
        if ret is None or order_line is None:
            quarantine.append(
                (line["source_id"], "DQ-3", "return_id or order_line_id not found in staged data")
            )
            continue

        order = orders_by_id.get(ret["order_id"])
        if order is None:
            quarantine.append((line["source_id"], "DQ-3", f"order_id {ret['order_id']} not found"))
            continue

        product_key = product_key_by_id.get(order_line["product_id"])
        customer_key = customer_key_by_id.get(order["customer_id"])
        if product_key is None or customer_key is None:
            quarantine.append(
                (line["source_id"], "DQ-3", "product_key or customer_key unresolved")
            )
            continue

        returned_quantity = line["returned_quantity"]
        unit_price = parse_decimal(order_line["unit_price"])
        unit_cost = parse_decimal(order_line["unit_cost"])
        disposition_id = line.get("disposition_id")

        rows.append(
            {
                "source_return_line_id": line["source_id"],
                "return_number": ret["return_number"],
                "order_number": order["order_number"],
                "reason_code": reason_code_by_id[line["reason_id"]],
                "disposition_code": (
                    disposition_code_by_id.get(disposition_id) if disposition_id else None
                ),
                "product_key": product_key,
                "customer_key": customer_key,
                "return_date_key": date_key_for(parse_date(ret["return_date"])),
                "returned_quantity": returned_quantity,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "return_value": unit_price * returned_quantity,
                "return_cost_value": unit_cost * returned_quantity,
            }
        )

    return rows, quarantine
