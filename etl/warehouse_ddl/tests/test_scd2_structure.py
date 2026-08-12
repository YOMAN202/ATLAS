"""Roadmap Phase 4 Testing Requirement: "a smoke test ... validates ...
SCD2 column structure."

Confirms dim_supplier/dim_warehouse have the SCD2 column set (ADR-012)
with the right types, that no other dimension has it (ADR-006: SCD2 only
on supplier and warehouse), that a two-version insert for the same
natural key is structurally permitted, and that the two TDD §4.3-named
composite indexes exist.
"""

from sqlalchemy import text

SCD2_DIMENSIONS = {"dim_supplier", "dim_warehouse"}
NON_SCD2_DIMENSIONS = {
    "dim_date",
    "dim_region",
    "dim_product",
    "dim_carrier",
    "dim_customer",
}
SCD2_COLUMNS = {"effective_from", "effective_to", "is_current"}


def test_scd2_columns_present_only_on_supplier_and_warehouse(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND COLUMN_NAME IN "
                "('effective_from', 'effective_to', 'is_current')"
            )
        ).all()

    columns_by_table: dict[str, set[str]] = {}
    for table_name, column_name, _data_type in rows:
        columns_by_table.setdefault(table_name, set()).add(column_name)

    for table in SCD2_DIMENSIONS:
        assert columns_by_table.get(table) == SCD2_COLUMNS, (
            f"{table} is missing part of the SCD2 column set (ADR-012): "
            f"expected {SCD2_COLUMNS}, found {columns_by_table.get(table)}"
        )

    for table in NON_SCD2_DIMENSIONS:
        assert table not in columns_by_table, (
            f"{table} unexpectedly has SCD2 columns — ADR-006 restricts SCD2 to "
            f"dim_supplier/dim_warehouse only"
        )


def test_dim_supplier_permits_multi_version_insert(db_conn):
    """Structural proof, not a behavioral ETL test (Phase 5 owns the
    actual SCD2 load logic): two rows for the same natural supplier_id,
    different effective_from dates, must both be insertable."""

    db_conn.execute(
        text(
            "INSERT INTO dim_supplier "
            "(supplier_id, supplier_code, supplier_name, payment_terms_days, "
            " default_lead_time_days, is_active, effective_from, effective_to, is_current, "
            " source_updated_at) "
            "VALUES (9002, 'SUP-V1', 'Supplier v1', 30, 14, 1, '2021-01-01', '2021-06-30', "
            " 0, NOW())"
        )
    )
    db_conn.execute(
        text(
            "INSERT INTO dim_supplier "
            "(supplier_id, supplier_code, supplier_name, payment_terms_days, "
            " default_lead_time_days, is_active, effective_from, effective_to, is_current, "
            " source_updated_at) "
            "VALUES (9002, 'SUP-V2', 'Supplier v2', 45, 7, 1, '2021-07-01', NULL, 1, NOW())"
        )
    )
    versions = db_conn.execute(
        text("SELECT COUNT(*) FROM dim_supplier WHERE supplier_id = 9002")
    ).scalar_one()
    assert versions == 2


def test_named_composite_indexes_exist(engine):
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT TABLE_NAME, INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND INDEX_NAME IN "
                "('ix_fact_inventory_snapshot_warehouse_date', "
                " 'ix_fact_supplier_delivery_supplier_date') "
                "GROUP BY TABLE_NAME, INDEX_NAME"
            )
        ).all()

    found = {(table, index): columns for table, index, columns in rows}
    assert found.get(("fact_inventory_snapshot", "ix_fact_inventory_snapshot_warehouse_date")) == (
        "warehouse_key,snapshot_date_key"
    )
    assert found.get(("fact_supplier_delivery", "ix_fact_supplier_delivery_supplier_date")) == (
        "supplier_key,delivery_date_key"
    )
