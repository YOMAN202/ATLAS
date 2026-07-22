# Entity-Relationship Diagram — OLTP Schema (DOC-1)

**Status:** Finalized to match the schema implemented in Phase 1
(`backend/app/models/`, migrations `3518b4c8151c` → `cd15da4c273a`).
Column-level detail (types, constraints, business meaning) lives in
[`docs/data-dictionary.md`](../data-dictionary.md); this diagram shows
structure and relationships.

```mermaid
erDiagram
    %% Reference / lookup tables
    regions ||--o{ warehouses : region
    regions ||--o{ customers : region

    %% Product / warehousing
    warehouses ||--o{ warehouse_zones : zone
    warehouses ||--o{ inventory_positions : position
    warehouse_zones ||--o{ inventory_positions : position
    products ||--o{ inventory_positions : position
    inventory_positions ||--o{ inventory_transactions : transaction
    inventory_transaction_types ||--o{ inventory_transactions : type

    %% Procurement
    suppliers ||--o{ purchase_orders : po
    warehouses ||--o{ purchase_orders : "destination"
    po_statuses ||--o{ purchase_orders : status
    purchase_orders ||--o{ purchase_order_lines : line
    products ||--o{ purchase_order_lines : product

    %% Orders / returns
    customers ||--o{ orders : order
    order_statuses ||--o{ orders : status
    orders ||--o{ order_lines : line
    products ||--o{ order_lines : product
    warehouses ||--o{ order_lines : fulfillment
    shipments ||--o{ order_lines : shipment
    orders ||--o{ returns : return
    returns ||--o{ return_lines : line
    order_lines ||--o{ return_lines : "original line"
    return_reasons ||--o{ return_lines : reason
    return_dispositions ||--o{ return_lines : disposition

    %% Transportation
    vehicle_types ||--o{ carriers : type
    carriers ||--o{ shipments : carrier
    warehouses ||--o{ shipments : origin
    warehouses ||--o{ shipments : "destination (transfer)"
    customers ||--o{ shipments : "destination (delivery)"
    shipment_statuses ||--o{ shipments : status
    shipments ||--o{ shipment_events : event
    shipment_statuses ||--o{ shipment_events : status
```

## Notes on relationships not expressible as a plain FK

- `inventory_transactions.source_reference_type` / `source_reference_id`
  is a polymorphic soft-reference (to a PO line, order line, return line,
  or transfer) — not shown above, since MySQL cannot express a single FK
  across multiple target tables. Documented exception to full DB-level FK
  enforcement (ADR-002); see `docs/data-dictionary.md`.
- `shipments` carries **either** `destination_warehouse_id` **or**
  `destination_customer_id` (never both, never neither), enforced by a
  CHECK constraint — modeling both inter-warehouse transfers (FR-2.3) and
  customer deliveries (FR-3.2) in the one `shipments` table TDD §4.1 names.

## 3NF justification

Every table is in 3NF (NFR-1): all non-key attributes depend on the whole
key, and on nothing but the key. The one deliberate denormalization is
price/cost snapshotting — `purchase_order_lines.unit_cost` and
`order_lines.unit_price`/`unit_cost` duplicate a value also present on
`products`, by design: a transaction line records the price *at the time
of the transaction*, not a live join to the product's current price, so
historical revenue/margin/spend figures don't shift retroactively when a
product's price changes. This is a standard, documented OLTP pattern, not
an oversight.
