# Star Schema Diagram — OLAP Warehouse (DOC-2)

**Status:** Initial version, committed in Phase 0 from `docs/ATLAS-TDD.md`
§4.2. This is a draft to design against — the **grain/schema review gate
at the end of Phase 4** is where it is validated against the implemented
DDL and finalized.

```mermaid
erDiagram
    dim_date ||--o{ fact_orders : "order_date"
    dim_product ||--o{ fact_orders : "product"
    dim_customer ||--o{ fact_orders : "customer"
    dim_warehouse ||--o{ fact_inventory_snapshot : "warehouse"
    dim_product ||--o{ fact_inventory_snapshot : "product"
    dim_date ||--o{ fact_inventory_snapshot : "snapshot_date"
    dim_supplier ||--o{ fact_procurement : "supplier"
    dim_product ||--o{ fact_procurement : "product"
    dim_carrier ||--o{ fact_shipments : "carrier"
    dim_warehouse ||--o{ fact_shipments : "origin_warehouse"
```

## Fact grains (TDD §4.2, not to be mixed)

| Fact table | Grain |
|---|---|
| `fact_orders` | Order line |
| `fact_shipments` | Shipment |
| `fact_inventory_snapshot` | SKU × warehouse × day |
| `fact_procurement` | PO line |
| `fact_supplier_delivery` | Delivery event |
| `fact_returns` | Return line |

## Conformed dimensions

`dim_date`, `dim_product`, `dim_supplier` (SCD2), `dim_warehouse` (SCD2),
`dim_carrier`, `dim_customer`, `dim_region`. SCD2 applies **only** to
supplier and warehouse (ADR-006) — all others are Type 1.

Built in **Phase 4**, after the OLTP schema (Phase 1) it derives from.
