# ATLAS Data Dictionary

**OLTP section: complete (Phase 1).** OLAP section arrives in Phase 4.

Conventions applied throughout (Master Prompt §5): surrogate integer PK
(`id`) on every table; every FK column indexed (InnoDB auto-indexes FK
columns); money/cost as `DECIMAL(12,2)` (NFR-4); `created_at`/`updated_at`
on every table, `updated_at` indexed — a structural prerequisite for
Phase 5's watermark-based incremental ETL (ADR-008), not shown per-table
below to avoid repetition.

## Reference / lookup tables

### regions
Geographic region — anchors FR-5.1 ("forecasts per SKU/region") and feeds the OLAP `dim_region` conformed dimension.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| code | VARCHAR(20) | UNIQUE, NOT NULL | Business key, e.g. `NE` |
| name | VARCHAR(100) | NOT NULL | e.g. "Northeast" |

### inventory_transaction_types
FR-2.1's five transaction kinds.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| code | VARCHAR(20) | UNIQUE, NOT NULL | RECEIPT / PICK / TRANSFER / ADJUSTMENT / RETURN |
| name | VARCHAR(100) | NOT NULL | Display name |

### po_statuses / order_statuses / shipment_statuses
FR-1.2 / FR-4.2 / FR-3.3 lifecycles respectively.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| code | VARCHAR(20) | UNIQUE, NOT NULL | e.g. `DRAFT`, `ALLOCATED`, `IN_TRANSIT` |
| name | VARCHAR(100) | NOT NULL | Display name |
| sort_order | INT | NOT NULL | Lifecycle ordering, for UI/reporting sequence |

### return_reasons / return_dispositions
FR-4.3 reason codes; BR-5 inspection dispositions.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| code | VARCHAR(20) | UNIQUE, NOT NULL | e.g. `DAMAGED`, `SELLABLE` |
| name | VARCHAR(100) | NOT NULL | Display name |

### vehicle_types
FR-3.1: capacity/cost are attributes of the vehicle type, not the individual carrier.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| code | VARCHAR(20) | UNIQUE, NOT NULL | e.g. `VAN`, `SEMI_TRAILER` |
| name | VARCHAR(100) | NOT NULL | Display name |
| capacity_units | INT | NOT NULL | FR-3.1 capacity |
| cost_per_mile | DECIMAL(12,2) | NOT NULL | FR-3.1/FR-3.4 cost profile |

---

## Procurement & Supplier Management (SRS §6.1)

### suppliers
FR-1.1. Reliability history is *not* a column here — it's derived at ETL time from `purchase_order_lines`' receipt fields, feeding `fact_supplier_delivery`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| supplier_code | VARCHAR(30) | UNIQUE, NOT NULL | Business key (DQ-2 principle) |
| name | VARCHAR(150) | NOT NULL | Supplier name |
| contact_email | VARCHAR(150) | NULL | |
| contact_phone | VARCHAR(30) | NULL | |
| address_line1 | VARCHAR(200) | NULL | |
| city | VARCHAR(100) | NULL | |
| state_province | VARCHAR(100) | NULL | |
| postal_code | VARCHAR(20) | NULL | |
| country | VARCHAR(100) | NULL | |
| payment_terms_days | INT | NOT NULL, default 30 | FR-1.1 contract terms |
| default_lead_time_days | INT | NOT NULL | FR-1.1 lead time baseline |
| is_active | BOOLEAN | NOT NULL, default true | |

### purchase_orders
FR-1.2 lifecycle (draft → submitted → confirmed → fulfilled → closed).

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| po_number | VARCHAR(30) | UNIQUE, NOT NULL | Business key (DQ-2) |
| supplier_id | INT | FK → suppliers.id, NOT NULL | |
| warehouse_id | INT | FK → warehouses.id, NOT NULL | Receiving DC |
| status_id | INT | FK → po_statuses.id, NOT NULL | |
| order_date | DATE | NOT NULL | |
| expected_delivery_date | DATE | NULL | |

### purchase_order_lines
Source of `fact_supplier_delivery`'s "delivery event" grain — there is no separate OLTP delivery table since TDD §4.1 names none; a line's receipt *is* the delivery event.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| purchase_order_id | INT | FK → purchase_orders.id, NOT NULL | |
| product_id | INT | FK → products.id, NOT NULL | |
| line_number | INT | NOT NULL, UNIQUE with purchase_order_id | |
| ordered_quantity | INT | NOT NULL, CHECK > 0 | |
| unit_cost | DECIMAL(12,2) | NOT NULL | Cost snapshotted at order time (not a live join to products) |
| received_quantity | INT | NOT NULL, default 0, CHECK >= 0 | BR-1 |
| quality_rejected_quantity | INT | NOT NULL, default 0, CHECK >= 0 | FR-1.3 |
| expected_delivery_date | DATE | NULL | |
| actual_delivery_date | DATE | NULL | FR-1.3 on-time % — the delivery event date |

---

## Product / Inventory & Warehousing (SRS §6.2)

### products
| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| sku | VARCHAR(30) | UNIQUE, NOT NULL | Business key |
| name | VARCHAR(200) | NOT NULL | |
| category | VARCHAR(100) | NULL | Descriptive, not a lookup table (not a lifecycle/status field) |
| unit_of_measure | VARCHAR(10) | NOT NULL, default "EA" | |
| unit_cost | DECIMAL(12,2) | NOT NULL | Current standard cost |
| unit_price | DECIMAL(12,2) | NOT NULL | Current standard price |
| is_active | BOOLEAN | NOT NULL, default true | |

### warehouses
FR-2.2 capacity constraints.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| warehouse_code | VARCHAR(20) | UNIQUE, NOT NULL | Business key |
| name | VARCHAR(150) | NOT NULL | |
| address_line1 / city / state_province / postal_code / country | VARCHAR | NULL | |
| region_id | INT | FK → regions.id, NOT NULL | |
| total_capacity_units | INT | NOT NULL | FR-2.2 |
| is_active | BOOLEAN | NOT NULL, default true | |

### warehouse_zones
FR-2.2 zone-level allocation.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| warehouse_id | INT | FK → warehouses.id, NOT NULL | |
| zone_code | VARCHAR(20) | NOT NULL, UNIQUE with warehouse_id | |
| name | VARCHAR(100) | NOT NULL | |
| zone_capacity_units | INT | NOT NULL | FR-2.2 |

### inventory_positions
Current-state table: one row per product × warehouse × zone.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| product_id | INT | FK → products.id, NOT NULL | |
| warehouse_id | INT | FK → warehouses.id, NOT NULL | |
| warehouse_zone_id | INT | FK → warehouse_zones.id, NOT NULL | |
| quantity_on_hand | INT | NOT NULL, default 0, CHECK >= 0 | BR-2 DB-level backstop |
| quantity_reserved | INT | NOT NULL, default 0, CHECK >= 0 | Allocated to open orders, not yet shipped |
| *(unique)* | | UNIQUE(product_id, warehouse_id, warehouse_zone_id) | |

### inventory_transactions
Append-only movement ledger.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| inventory_position_id | INT | FK → inventory_positions.id, NOT NULL | |
| transaction_type_id | INT | FK → inventory_transaction_types.id, NOT NULL | |
| quantity_delta | INT | NOT NULL | + for receipt/return-in, − for pick/adjustment-out |
| occurred_at | DATETIME | NOT NULL, indexed | Business event time |
| source_reference_type | VARCHAR(30) | NULL | Polymorphic soft-reference kind (e.g. `purchase_order_line`) |
| source_reference_id | INT | NULL | Polymorphic soft-reference id — **not** a DB-level FK (documented exception to ADR-002: MySQL cannot FK across multiple target tables) |

---

## Order Management & Returns (SRS §6.4)

### customers
| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| customer_code | VARCHAR(30) | UNIQUE, NOT NULL | Business key |
| name | VARCHAR(150) | NOT NULL | |
| email | VARCHAR(150) | NULL | |
| phone | VARCHAR(30) | NULL | |
| address_line1 / city / state_province / postal_code / country | VARCHAR | NULL | |
| region_id | INT | FK → regions.id, NOT NULL | |

### orders
FR-4.1/FR-4.2.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| order_number | VARCHAR(30) | UNIQUE, NOT NULL | Business key (DQ-2) |
| customer_id | INT | FK → customers.id, NOT NULL | |
| status_id | INT | FK → order_statuses.id, NOT NULL | |
| order_date | DATE | NOT NULL | |

### order_lines
Carries `fulfillment_warehouse_id` at the **line** grain (not a single warehouse on the order) because BR-2 partial fulfillment means different lines can be allocated from, and shipped out of, different warehouses.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| order_id | INT | FK → orders.id, NOT NULL | |
| product_id | INT | FK → products.id, NOT NULL | |
| line_number | INT | NOT NULL, UNIQUE with order_id | |
| ordered_quantity | INT | NOT NULL, CHECK > 0 | |
| allocated_quantity | INT | NOT NULL, default 0, CHECK >= 0 | BR-2 |
| backordered_quantity | INT | NOT NULL, default 0, CHECK >= 0 | BR-2 |
| *(check)* | | CHECK allocated + backordered <= ordered | BR-2 arithmetic invariant |
| unit_price | DECIMAL(12,2) | NOT NULL | Snapshotted at sale time |
| unit_cost | DECIMAL(12,2) | NOT NULL | Snapshotted at sale time (COGS) |
| fulfillment_warehouse_id | INT | FK → warehouses.id, NULL | Set once allocated |
| shipment_id | INT | FK → shipments.id, NULL | Set once shipped |

### returns
| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| return_number | VARCHAR(30) | UNIQUE, NOT NULL | Business key (not in SRS DQ-2's example list, but Master Prompt §5's stated principle applies to any business identifier) |
| order_id | INT | FK → orders.id, NOT NULL | |
| return_date | DATE | NOT NULL | |

### return_lines
| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| return_id | INT | FK → returns.id, NOT NULL | |
| order_line_id | INT | FK → order_lines.id, NOT NULL | Which line is being returned |
| line_number | INT | NOT NULL, UNIQUE with return_id | |
| returned_quantity | INT | NOT NULL, CHECK > 0 | |
| reason_id | INT | FK → return_reasons.id, NOT NULL | FR-4.3 |
| disposition_id | INT | FK → return_dispositions.id, NULL | BR-5: null until inspected |
| inspected_at | DATETIME | NULL | BR-5 inspection timestamp |

---

## Transportation & Fleet Operations (SRS §6.3)

### carriers
| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| carrier_code | VARCHAR(20) | UNIQUE, NOT NULL | Business key |
| name | VARCHAR(150) | NOT NULL | |
| vehicle_type_id | INT | FK → vehicle_types.id, NOT NULL | FR-3.1 |
| is_active | BOOLEAN | NOT NULL, default true | |

### shipments
Models **both** customer-delivery shipments (FR-3.2/UC-2) and inter-warehouse transfers (FR-2.3) in one table, since TDD §4.1 names only one `shipments` table.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| shipment_number | VARCHAR(30) | UNIQUE, NOT NULL | Business key (DQ-2) |
| carrier_id | INT | FK → carriers.id, NOT NULL | |
| origin_warehouse_id | INT | FK → warehouses.id, NOT NULL | |
| destination_warehouse_id | INT | FK → warehouses.id, NULL | FR-2.3 transfer destination |
| destination_customer_id | INT | FK → customers.id, NULL | FR-3.2 delivery destination |
| *(check)* | | CHECK exactly one of destination_warehouse_id / destination_customer_id is set | Enforces the transfer-xor-delivery invariant |
| status_id | INT | FK → shipment_statuses.id, NOT NULL | |
| ship_date | DATE | NULL | |
| estimated_delivery_date | DATE | NULL | |
| actual_delivery_date | DATE | NULL | |
| distance_miles | DECIMAL(10,2) | NULL | FR-3.4 cost-per-mile input |
| shipping_cost | DECIMAL(12,2) | NULL | FR-3.2 |

### shipment_events
FR-3.3 status-history/audit-trail.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| id | INT | PK | Surrogate key |
| shipment_id | INT | FK → shipments.id, NOT NULL | |
| status_id | INT | FK → shipment_statuses.id, NOT NULL | The status this event represents |
| occurred_at | DATETIME | NOT NULL | |
| location | VARCHAR(255) | NULL | Optional checkpoint location |
| notes | VARCHAR(500) | NULL | e.g. exception reason |

---

## Deliberate design notes (for interview defensibility)

- **Price/cost snapshotting:** `purchase_order_lines.unit_cost` and `order_lines.unit_price`/`unit_cost` duplicate values also on `products` — by design, so historical spend/revenue/margin don't shift when a product's current price changes. Documented 3NF exception, not an oversight.
- **Polymorphic soft-reference:** `inventory_transactions.source_reference_type/id` is the one relationship in this schema not enforced as a DB-level FK (ADR-002's one documented exception), because MySQL cannot FK a single column to multiple target tables.
- **Lookup tables beyond TDD §4.1's literal list:** `regions`, `inventory_transaction_types`, `po_statuses`, `order_statuses`, `shipment_statuses`, `return_reasons`, `return_dispositions`, `vehicle_types` implement the TDD's own stated principle ("status fields as constrained enumerations, not free text") and the Roadmap's explicit call for "status codes, regions, vehicle types" reference-data loaders — they are the implementation of that principle, not new scope.
- **`created_at`/`updated_at` on every table:** added structurally now because Phase 5's incremental ETL (ADR-008) requires indexed watermark columns; retrofitting after Phase 1 would be a destructive schema change.
