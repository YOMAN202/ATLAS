from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import InventoryPosition, Product, Supplier, Warehouse


# DQ-2 / Master Prompt §5: unique constraints on business keys.
def test_unique_business_key_rejects_duplicate(db_session, region):
    db_session.add(Supplier(supplier_code="SUP-1", name="A", default_lead_time_days=7))
    db_session.flush()

    db_session.add(Supplier(supplier_code="SUP-1", name="B", default_lead_time_days=14))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ADR-002: DB-level FK enforcement, not just application-level.
def test_fk_violation_is_rejected(db_session):
    db_session.add(
        Warehouse(
            warehouse_code="WH-BAD",
            name="Bad Warehouse",
            region_id=999999,  # no such region
            total_capacity_units=1000,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# NFR-4: DECIMAL(12,2), precise, no float rounding error.
def test_decimal_precision_is_exact(db_session, product):
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(Product, product.id)
    assert reloaded.unit_price == Decimal("19.99")
    assert reloaded.unit_cost == Decimal("10.00")


# BR-2: inventory cannot go negative — DB-level CHECK backstop.
# MySQL 8 raises OperationalError (error 3819) for a CHECK violation,
# not IntegrityError.
def test_negative_inventory_is_rejected(db_session, product, warehouse, warehouse_zone):
    db_session.add(
        InventoryPosition(
            product_id=product.id,
            warehouse_id=warehouse.id,
            warehouse_zone_id=warehouse_zone.id,
            quantity_on_hand=-1,
        )
    )
    with pytest.raises(OperationalError):
        db_session.flush()


# FR-2.2: one inventory position per product x warehouse x zone.
def test_composite_unique_inventory_position(db_session, product, warehouse, warehouse_zone):
    db_session.add(
        InventoryPosition(
            product_id=product.id,
            warehouse_id=warehouse.id,
            warehouse_zone_id=warehouse_zone.id,
            quantity_on_hand=10,
        )
    )
    db_session.flush()

    db_session.add(
        InventoryPosition(
            product_id=product.id,
            warehouse_id=warehouse.id,
            warehouse_zone_id=warehouse_zone.id,
            quantity_on_hand=5,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
