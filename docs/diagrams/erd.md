# Entity-Relationship Diagram — OLTP Schema (DOC-1)

**Status:** Draft outline only, committed in Phase 0. This lists the
entities fixed by `docs/ATLAS-TDD.md` §4.1, grouped by domain. Attributes,
keys, and cardinalities are real schema design work and are decided in
**Phase 1**, then finalized at the **schema review gate** ending that
phase — this file is replaced with the true ERD at that point, not
extended piecemeal beforehand.

## Entities by domain (TDD §4.1)

- **Procurement:** `suppliers`, `purchase_orders`, `purchase_order_lines`
- **Product / Warehousing:** `products`, `warehouses`, `warehouse_zones`,
  `inventory_positions`, `inventory_transactions`
- **Transportation:** `carriers`, `shipments`, `shipment_events`
- **Orders / Returns:** `customers`, `orders`, `order_lines`, `returns`,
  `return_lines`
- **Reference / lookups:** status enumeration tables for order, shipment,
  and PO lifecycles (Master Prompt §5 — status fields are constrained
  lookup tables, never free text)

All tables: surrogate integer PKs, DB-level FK enforcement (ADR-002),
3NF unless a documented denormalization is justified (NFR-1), unique
constraints on business keys (`order_number`, `po_number`,
`shipment_number` — DQ-2), `DECIMAL(12,2)` for money (NFR-4).
