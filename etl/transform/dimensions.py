"""Pure row-building for the 7 conformed dimensions: OLTP staged payload
-> target dim table column dict. No DB access here — FK lookups
(region_key, vehicle type info) are resolved by the caller and passed
in, so these functions are trivially testable without a database.

dim_date needs no transform — Phase 4 generated and populated it
directly; there is no OLTP source for it.
"""

from etl.transform.parsing import parse_datetime, parse_decimal


def build_dim_region_rows(staged: list[dict]) -> list[dict]:
    return [
        {
            "region_id": row["source_id"],
            "region_code": row["code"],
            "region_name": row["name"],
            "source_updated_at": parse_datetime(row["updated_at"]),
        }
        for row in staged
    ]


def build_dim_product_rows(staged: list[dict]) -> list[dict]:
    return [
        {
            "product_id": row["source_id"],
            "sku": row["sku"],
            "product_name": row["name"],
            "category": row.get("category"),
            "unit_of_measure": row["unit_of_measure"],
            "current_unit_cost": parse_decimal(row["unit_cost"]),
            "current_unit_price": parse_decimal(row["unit_price"]),
            "is_active": bool(row["is_active"]),
            "source_updated_at": parse_datetime(row["updated_at"]),
        }
        for row in staged
    ]


def build_dim_carrier_rows(staged: list[dict], vehicle_types_by_id: dict[int, dict]) -> list[dict]:
    rows = []
    for row in staged:
        vt = vehicle_types_by_id[row["vehicle_type_id"]]
        rows.append(
            {
                "carrier_id": row["source_id"],
                "carrier_code": row["carrier_code"],
                "carrier_name": row["name"],
                "vehicle_type_code": vt["code"],
                "vehicle_type_name": vt["name"],
                "vehicle_capacity_units": vt["capacity_units"],
                "vehicle_cost_per_mile": vt["cost_per_mile"],
                "is_active": bool(row["is_active"]),
                "source_updated_at": parse_datetime(row["updated_at"]),
            }
        )
    return rows


def build_dim_customer_rows(staged: list[dict], region_key_by_id: dict[int, int]) -> list[dict]:
    return [
        {
            "customer_id": row["source_id"],
            "customer_code": row["customer_code"],
            "customer_name": row["name"],
            "email": row.get("email"),
            "phone": row.get("phone"),
            "address_line1": row.get("address_line1"),
            "city": row.get("city"),
            "state_province": row.get("state_province"),
            "postal_code": row.get("postal_code"),
            "country": row.get("country"),
            "region_key": region_key_by_id[row["region_id"]],
            "source_updated_at": parse_datetime(row["updated_at"]),
        }
        for row in staged
    ]


def build_scd2_supplier_candidates(staged: list[dict]) -> list[dict]:
    """One candidate per staged supplier row — the target attribute set
    if a version is needed. etl/load/dimensions.py decides whether that
    means a new version, an in-place update, or nothing (ADR-016)."""

    return [
        {
            "supplier_id": row["source_id"],
            "supplier_code": row["supplier_code"],
            "supplier_name": row["name"],
            "contact_email": row.get("contact_email"),
            "contact_phone": row.get("contact_phone"),
            "address_line1": row.get("address_line1"),
            "city": row.get("city"),
            "state_province": row.get("state_province"),
            "postal_code": row.get("postal_code"),
            "country": row.get("country"),
            "payment_terms_days": row["payment_terms_days"],
            "default_lead_time_days": row["default_lead_time_days"],
            "is_active": bool(row["is_active"]),
            "source_updated_at": parse_datetime(row["updated_at"]),
        }
        for row in staged
    ]


def build_scd2_warehouse_candidates(
    staged: list[dict], region_key_by_id: dict[int, int]
) -> list[dict]:
    return [
        {
            "warehouse_id": row["source_id"],
            "warehouse_code": row["warehouse_code"],
            "warehouse_name": row["name"],
            "address_line1": row.get("address_line1"),
            "city": row.get("city"),
            "state_province": row.get("state_province"),
            "postal_code": row.get("postal_code"),
            "country": row.get("country"),
            "region_key": region_key_by_id[row["region_id"]],
            "total_capacity_units": row["total_capacity_units"],
            "is_active": bool(row["is_active"]),
            "source_updated_at": parse_datetime(row["updated_at"]),
        }
        for row in staged
    ]
