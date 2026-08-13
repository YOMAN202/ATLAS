"""Declarative registry of every OLTP source table Stage A extracts from
and validates — one entry per table, describing its watermark column,
required (non-null) columns for DQ-1, unique/natural-key columns for
DQ-2, foreign-key checks for DQ-3, and range/domain checks for DQ-5.

A declarative registry rather than 13 hand-written near-duplicate
extract/validate modules: every source table follows the same shape
(watermark-based extract, DQ-1/2/3/4/5 checks against real column
constraints already documented in docs/data-dictionary.md), so the
per-table difference is genuinely just *which* columns/rules apply, not
different logic. New source tables (e.g. once Stage B needs additional
extraction) are added here, not by writing new modules.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RangeCheck:
    column: str
    description: str
    is_valid: Callable[[object], bool]


@dataclass(frozen=True)
class ForeignKeyCheck:
    column: str
    referenced_table: str
    referenced_column: str = "id"


@dataclass(frozen=True)
class TableSpec:
    name: str
    pk_column: str = "id"
    watermark_column: str = "updated_at"
    required_columns: tuple[str, ...] = field(default_factory=tuple)
    unique_columns: tuple[str, ...] = field(default_factory=tuple)
    foreign_keys: tuple[ForeignKeyCheck, ...] = field(default_factory=tuple)
    range_checks: tuple[RangeCheck, ...] = field(default_factory=tuple)


def _positive(value: object) -> bool:
    return value is not None and value > 0


def _non_negative(value: object) -> bool:
    return value is not None and value >= 0


REGISTRY: tuple[TableSpec, ...] = (
    TableSpec(
        name="regions",
        required_columns=("code", "name"),
        unique_columns=("code",),
    ),
    TableSpec(
        name="products",
        required_columns=("sku", "name", "unit_of_measure", "unit_cost", "unit_price"),
        unique_columns=("sku",),
        range_checks=(
            RangeCheck("unit_cost", "unit_cost must be >= 0", _non_negative),
            RangeCheck("unit_price", "unit_price must be >= 0", _non_negative),
        ),
    ),
    TableSpec(
        name="suppliers",
        required_columns=("supplier_code", "name", "payment_terms_days", "default_lead_time_days"),
        unique_columns=("supplier_code",),
        range_checks=(
            RangeCheck("payment_terms_days", "payment_terms_days must be >= 0", _non_negative),
            RangeCheck(
                "default_lead_time_days", "default_lead_time_days must be >= 0", _non_negative
            ),
        ),
    ),
    TableSpec(
        name="warehouses",
        required_columns=("warehouse_code", "name", "region_id", "total_capacity_units"),
        unique_columns=("warehouse_code",),
        foreign_keys=(ForeignKeyCheck("region_id", "regions"),),
        range_checks=(
            RangeCheck("total_capacity_units", "total_capacity_units must be >= 0", _non_negative),
        ),
    ),
    TableSpec(
        name="carriers",
        required_columns=("carrier_code", "name", "vehicle_type_id"),
        unique_columns=("carrier_code",),
        foreign_keys=(ForeignKeyCheck("vehicle_type_id", "vehicle_types"),),
    ),
    TableSpec(
        name="customers",
        required_columns=("customer_code", "name", "region_id"),
        unique_columns=("customer_code",),
        foreign_keys=(ForeignKeyCheck("region_id", "regions"),),
    ),
    TableSpec(
        name="orders",
        required_columns=("order_number", "customer_id", "status_id", "order_date"),
        unique_columns=("order_number",),
        foreign_keys=(
            ForeignKeyCheck("customer_id", "customers"),
            ForeignKeyCheck("status_id", "order_statuses"),
        ),
    ),
    TableSpec(
        name="order_lines",
        required_columns=(
            "order_id",
            "product_id",
            "line_number",
            "ordered_quantity",
            "unit_price",
            "unit_cost",
        ),
        foreign_keys=(
            ForeignKeyCheck("order_id", "orders"),
            ForeignKeyCheck("product_id", "products"),
        ),
        range_checks=(RangeCheck("ordered_quantity", "ordered_quantity must be > 0", _positive),),
    ),
    TableSpec(
        name="purchase_orders",
        required_columns=("po_number", "supplier_id", "warehouse_id", "status_id", "order_date"),
        unique_columns=("po_number",),
        foreign_keys=(
            ForeignKeyCheck("supplier_id", "suppliers"),
            ForeignKeyCheck("warehouse_id", "warehouses"),
            ForeignKeyCheck("status_id", "po_statuses"),
        ),
    ),
    TableSpec(
        name="purchase_order_lines",
        required_columns=(
            "purchase_order_id",
            "product_id",
            "line_number",
            "ordered_quantity",
            "unit_cost",
        ),
        foreign_keys=(
            ForeignKeyCheck("purchase_order_id", "purchase_orders"),
            ForeignKeyCheck("product_id", "products"),
        ),
        range_checks=(RangeCheck("ordered_quantity", "ordered_quantity must be > 0", _positive),),
    ),
    TableSpec(
        name="shipments",
        required_columns=("shipment_number", "carrier_id", "origin_warehouse_id", "status_id"),
        unique_columns=("shipment_number",),
        foreign_keys=(
            ForeignKeyCheck("carrier_id", "carriers"),
            ForeignKeyCheck("origin_warehouse_id", "warehouses"),
            ForeignKeyCheck("status_id", "shipment_statuses"),
        ),
    ),
    TableSpec(
        name="returns",
        required_columns=("return_number", "order_id", "return_date"),
        unique_columns=("return_number",),
        foreign_keys=(ForeignKeyCheck("order_id", "orders"),),
    ),
    TableSpec(
        name="return_lines",
        required_columns=(
            "return_id",
            "order_line_id",
            "line_number",
            "returned_quantity",
            "reason_id",
        ),
        foreign_keys=(
            ForeignKeyCheck("return_id", "returns"),
            ForeignKeyCheck("order_line_id", "order_lines"),
            ForeignKeyCheck("reason_id", "return_reasons"),
        ),
        range_checks=(RangeCheck("returned_quantity", "returned_quantity must be > 0", _positive),),
    ),
    # inventory_positions/inventory_transactions: fact_inventory_snapshot's
    # only source (ADR-020) — not anticipated by Stage A's original 13-table
    # scope (built before Stage B's fact-by-fact needs were worked out in
    # detail), added here as a necessary registry extension, not a Stage A
    # optimization. Runs through the identical extract/validate/stage
    # machinery as every other table.
    TableSpec(
        name="inventory_positions",
        required_columns=(
            "product_id",
            "warehouse_id",
            "warehouse_zone_id",
            "quantity_on_hand",
            "quantity_reserved",
        ),
        foreign_keys=(
            ForeignKeyCheck("product_id", "products"),
            ForeignKeyCheck("warehouse_id", "warehouses"),
            ForeignKeyCheck("warehouse_zone_id", "warehouse_zones"),
        ),
        range_checks=(
            RangeCheck("quantity_on_hand", "quantity_on_hand must be >= 0", _non_negative),
            RangeCheck("quantity_reserved", "quantity_reserved must be >= 0", _non_negative),
        ),
    ),
    TableSpec(
        name="inventory_transactions",
        required_columns=("inventory_position_id", "transaction_type_id", "quantity_delta", "occurred_at"),
        foreign_keys=(
            ForeignKeyCheck("inventory_position_id", "inventory_positions"),
            ForeignKeyCheck("transaction_type_id", "inventory_transaction_types"),
        ),
    ),
)

REGISTRY_BY_NAME: dict[str, TableSpec] = {spec.name: spec for spec in REGISTRY}
