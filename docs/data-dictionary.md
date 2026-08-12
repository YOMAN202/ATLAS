# ATLAS Data Dictionary

**OLTP section: complete (Phase 1). OLAP section: complete (Phase 4).**

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

## OLAP Data Warehouse (Phase 4)

Star schema, Kimball methodology (TDD §4.2). Every dimension has a
surrogate key (`<dim>_key`, `AUTO_INCREMENT`) distinct from the OLTP
`id` (ADR-011, `docs/ATLAS-TDD.md` §14); every fact has a
`source_*_id`/grain-composite `UNIQUE` constraint that is both its
idempotency key for Phase 5's ETL upsert and its grain enforcement.
DDL: `etl/warehouse_ddl/`. Diagram: `docs/diagrams/star-schema.md`.

### dim_date
Type 1 (generated, no OLTP source — see `01_dim_date.sql`). Grain: one row per calendar day. Populated 2021-01-01 through 2022-01-31, covering the validated 365-day Phase 3 dataset plus trailing lead-time/return dates.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| date_key | INT | PK | `YYYYMMDD` |
| full_date | DATE | UNIQUE, NOT NULL | |
| day_of_week | TINYINT | NOT NULL | 1=Sunday..7=Saturday |
| day_name | VARCHAR(10) | NOT NULL | |
| day_of_month | TINYINT | NOT NULL | |
| day_of_year | SMALLINT | NOT NULL | |
| week_of_year | TINYINT | NOT NULL | |
| month_number | TINYINT | NOT NULL | |
| month_name | VARCHAR(10) | NOT NULL | |
| quarter | TINYINT | NOT NULL | |
| year | SMALLINT | NOT NULL | |
| is_weekend | TINYINT(1) | NOT NULL | |

### dim_region
Type 1. Grain: one row per region. Conformed "outrigger" — reached only through `dim_customer`/`dim_warehouse`, not linked to any fact directly. Source: `atlas_oltp.regions`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| region_key | INT | PK | Surrogate key |
| region_id | INT | UNIQUE, NOT NULL | OLTP `regions.id` |
| region_code | VARCHAR(20) | UNIQUE, NOT NULL | |
| region_name | VARCHAR(100) | NOT NULL | |
| source_updated_at | DATETIME | NOT NULL | Type-1 refresh watermark |

### dim_product
Type 1 (TDD §4.2: attribute changes not analytically significant at this scope). Grain: one row per product. Source: `atlas_oltp.products`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| product_key | INT | PK | Surrogate key |
| product_id | INT | UNIQUE, NOT NULL | OLTP `products.id` |
| sku | VARCHAR(30) | UNIQUE, NOT NULL | |
| product_name | VARCHAR(200) | NOT NULL | |
| category | VARCHAR(100) | NULL | |
| unit_of_measure | VARCHAR(10) | NOT NULL | |
| current_unit_cost | DECIMAL(12,2) | NOT NULL | |
| current_unit_price | DECIMAL(12,2) | NOT NULL | |
| is_active | TINYINT(1) | NOT NULL | |
| source_updated_at | DATETIME | NOT NULL | Type-1 refresh watermark |

### dim_supplier
**SCD Type 2** (TDD §4.2/ADR-006: contract terms and lead times change over time). Grain: one row per supplier **per version** — `supplier_id` intentionally repeats across rows. MySQL 8 has no partial/filtered unique index, so "exactly one `is_current=1` row per supplier" is ETL-enforced, not DB-enforced (ADR-012). Source: `atlas_oltp.suppliers`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| supplier_key | INT | PK | Surrogate key |
| supplier_id | INT | NOT NULL | OLTP `suppliers.id`; repeats across versions |
| supplier_code | VARCHAR(30) | NOT NULL | |
| supplier_name | VARCHAR(150) | NOT NULL | |
| contact_email / contact_phone / address fields | VARCHAR | NULL | |
| payment_terms_days | INT | NOT NULL | Tracked (SCD2-triggering) attribute |
| default_lead_time_days | INT | NOT NULL | Tracked (SCD2-triggering) attribute |
| is_active | TINYINT(1) | NOT NULL | |
| effective_from | DATE | NOT NULL, UNIQUE with supplier_id | |
| effective_to | DATE | NULL | |
| is_current | TINYINT(1) | NOT NULL | ETL-enforced uniqueness, see above |
| source_updated_at | DATETIME | NOT NULL | |

### dim_warehouse
**SCD Type 2** (TDD §4.2/ADR-006: capacity changes over time). Grain: one row per warehouse **per version**. Same MySQL partial-unique-index limitation as `dim_supplier` (ADR-012). FK to `dim_region` (outrigger). Source: `atlas_oltp.warehouses`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| warehouse_key | INT | PK | Surrogate key |
| warehouse_id | INT | NOT NULL | OLTP `warehouses.id`; repeats across versions |
| warehouse_code | VARCHAR(20) | NOT NULL | |
| warehouse_name | VARCHAR(150) | NOT NULL | |
| address fields | VARCHAR | NULL | |
| region_key | INT | FK → dim_region.region_key, NOT NULL | |
| total_capacity_units | INT | NOT NULL | Tracked (SCD2-triggering) attribute |
| is_active | TINYINT(1) | NOT NULL | |
| effective_from | DATE | NOT NULL, UNIQUE with warehouse_id | |
| effective_to | DATE | NULL | |
| is_current | TINYINT(1) | NOT NULL | ETL-enforced uniqueness |
| source_updated_at | DATETIME | NOT NULL | |

### dim_carrier
Type 1. Grain: one row per carrier. Denormalized with its `vehicle_types` lookup row (not one of the 7 named conformed dimensions, so collapsed rather than snowflaked). Source: `atlas_oltp.carriers`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| carrier_key | INT | PK | Surrogate key |
| carrier_id | INT | UNIQUE, NOT NULL | OLTP `carriers.id` |
| carrier_code | VARCHAR(20) | UNIQUE, NOT NULL | |
| carrier_name | VARCHAR(150) | NOT NULL | |
| vehicle_type_code / vehicle_type_name | VARCHAR | NOT NULL | Denormalized from `vehicle_types` |
| vehicle_capacity_units | INT | NOT NULL | |
| vehicle_cost_per_mile | DECIMAL(12,2) | NOT NULL | |
| is_active | TINYINT(1) | NOT NULL | |
| source_updated_at | DATETIME | NOT NULL | |

### dim_customer
Type 1. Grain: one row per customer. FK to `dim_region` (outrigger). Source: `atlas_oltp.customers`.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| customer_key | INT | PK | Surrogate key |
| customer_id | INT | UNIQUE, NOT NULL | OLTP `customers.id` |
| customer_code | VARCHAR(30) | UNIQUE, NOT NULL | |
| customer_name / email / phone / address fields | VARCHAR | NULL/NOT NULL as source | |
| region_key | INT | FK → dim_region.region_key, NOT NULL | |
| source_updated_at | DATETIME | NOT NULL | |

### fact_orders
**Grain: one row per order line.** FKs per TDD §4.2's ER diagram (`order_date_key`, `product_key`, `customer_key`) plus `fulfillment_warehouse_key` (nullable — an addition beyond the literal diagram, grounded in `order_lines.fulfillment_warehouse_id`, needed for the location-aware "cost-to-serve" KPI). No ratios stored — fulfillment rate is `SUM(allocated_quantity)/SUM(ordered_quantity)` at query time.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| order_line_key | INT | PK | Surrogate key |
| source_order_line_id | INT | UNIQUE, NOT NULL | Grain/idempotency key; `order_lines.id` |
| order_number / order_line_number / shipment_number | VARCHAR/INT | shipment_number NULL | Degenerate dimensions |
| order_date_key | INT | FK → dim_date | |
| product_key | INT | FK → dim_product | |
| customer_key | INT | FK → dim_customer | |
| fulfillment_warehouse_key | INT | FK → dim_warehouse, NULL | Addition beyond TDD's literal ER diagram |
| ordered_quantity / allocated_quantity / backordered_quantity | INT | NOT NULL | |
| unit_price / unit_cost | DECIMAL(12,2) | NOT NULL | |
| extended_revenue / extended_cost / gross_margin | DECIMAL(12,2) | NOT NULL, additive | |

### fact_shipments
**Grain: one row per shipment.** FKs per TDD §4.2 (`carrier_key`, `origin_warehouse_key`) plus `ship_date_key` (unavoidable — every fact needs a date) and `destination_warehouse_key`/`destination_customer_key`, mirroring OLTP's own transfer-xor-delivery invariant via a `CHECK` constraint. Non-additive ratios (cost-per-mile, on-time %) not stored — `is_on_time` flag + `shipping_cost`/`distance_miles` are, and ratios compute at query time.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| shipment_key | INT | PK | Surrogate key |
| source_shipment_id | INT | UNIQUE, NOT NULL | Grain/idempotency key |
| shipment_number / status_code | VARCHAR | NOT NULL | Degenerate; status_code is a load-time snapshot |
| carrier_key | INT | FK → dim_carrier | |
| origin_warehouse_key | INT | FK → dim_warehouse | |
| destination_warehouse_key / destination_customer_key | INT | FK, exactly one NOT NULL (CHECK) | Mirrors OLTP XOR invariant |
| ship_date_key / estimated_delivery_date_key / actual_delivery_date_key | INT | FK → dim_date, latter two NULL | |
| distance_miles | DECIMAL(10,2) | NULL | |
| shipping_cost | DECIMAL(12,2) | NULL | |
| is_on_time | TINYINT(1) | NULL, additive flag | NULL until delivered |
| transit_days | INT | NULL | |

### fact_inventory_snapshot
**Grain: exactly one row per product, per warehouse, per snapshot date** — not per zone, not per position, not per transaction (ADR-003 periodic snapshot fact; rolls OLTP's zone-level `inventory_positions` up to the warehouse level for the day). Grain key `(product_key, warehouse_key, snapshot_date_key)` UNIQUE. Sparsified — only active (product, warehouse) pairs get a row on a given day (Phase 5 concern). Non-additive/derived measures (days_of_supply, overstock value, capacity_utilization) not stored — no business-rule definition exists in frozen scope for them.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| inventory_snapshot_key | INT | PK | Surrogate key |
| snapshot_date_key | INT | FK → dim_date | |
| product_key | INT | FK → dim_product | |
| warehouse_key | INT | FK → dim_warehouse | |
| *(grain)* | | UNIQUE(product_key, warehouse_key, snapshot_date_key) | Grain/idempotency key |
| quantity_on_hand / quantity_reserved / quantity_available | INT | NOT NULL, additive | |
| inventory_value | DECIMAL(12,2) | NOT NULL, additive | `quantity_on_hand × dim_product.current_unit_cost` at load time |
| is_stockout | TINYINT(1) | NOT NULL, additive flag | `quantity_on_hand = 0` |

### fact_procurement
**Grain: one row per purchase-order line — the purchase-order event** (what was ordered, from whom, at what cost; exists as soon as the line does, regardless of receipt status). See `fact_supplier_delivery` below for the explicit distinction. FKs per TDD §4.2 (`supplier_key`, `product_key`) plus `warehouse_key` (addition, `purchase_orders.warehouse_id`, the receiving DC — needed for warehouse-level procurement spend).

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| po_line_key | INT | PK | Surrogate key |
| source_po_line_id | INT | UNIQUE, NOT NULL | Grain/idempotency key |
| po_number / po_line_number / po_status_code | VARCHAR/INT | NOT NULL | Degenerate; status is a load-time snapshot |
| supplier_key | INT | FK → dim_supplier | SCD2-resolved as of order_date_key |
| product_key | INT | FK → dim_product | |
| warehouse_key | INT | FK → dim_warehouse | Addition beyond TDD's literal ER diagram; receiving DC |
| order_date_key / expected_delivery_date_key | INT | FK → dim_date, latter NULL | |
| ordered_quantity | INT | NOT NULL | |
| unit_cost | DECIMAL(12,2) | NOT NULL | |
| extended_cost | DECIMAL(12,2) | NOT NULL, additive | Procurement spend |
| received_quantity / quality_rejected_quantity | INT | NOT NULL | |

### fact_supplier_delivery
**Grain: one row per delivery event — the receipt/delivery event** (what actually arrived, when, in what condition). Sourced from the same OLTP table as `fact_procurement` (`purchase_order_lines` — there is no separate delivery-event table), but only gets a row once a line has actually been received (`delivery_date_key` is `NOT NULL` — a delivery event without a date isn't an event). See ADR-013. Dimension links are TDD-silent and designed here from real columns.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| delivery_key | INT | PK | Surrogate key |
| source_po_line_id | INT | UNIQUE, NOT NULL | Grain/idempotency key; same source row as fact_procurement |
| po_number / po_line_number | VARCHAR/INT | NOT NULL | Degenerate |
| supplier_key | INT | FK → dim_supplier | SCD2-resolved as of delivery_date_key |
| product_key | INT | FK → dim_product | |
| warehouse_key | INT | FK → dim_warehouse | SCD2-resolved as of delivery_date_key; receiving DC |
| delivery_date_key | INT | FK → dim_date, NOT NULL | |
| expected_delivery_date_key | INT | FK → dim_date, NOT NULL | Needed for lead-time variance |
| ordered_quantity / received_quantity / quality_rejected_quantity | INT | NOT NULL | |
| quality_accepted_quantity | INT | NOT NULL, additive | `received_quantity - quality_rejected_quantity` |
| is_on_time | TINYINT(1) | NOT NULL, additive flag | `actual_delivery_date <= expected_delivery_date` |
| lead_time_variance_days | INT | NOT NULL, additive | `actual - expected`, in days |

Composite index `(supplier_key, delivery_date_key)` per TDD §4.3.

### fact_returns
**Grain: one row per return line.** Dimension links are TDD-silent and designed here: `product_key`/`customer_key` (via `return_lines.order_line_id → order_lines`), `return_date_key`. `reason_code`/`disposition_code` are degenerate text columns, not promoted to new conformed dimensions (the frozen dimension list is exactly 7). `is_quality_related` not stored — classifying "quality-driven" reason codes is an undefined business rule, left to Phase 5/7.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| return_line_key | INT | PK | Surrogate key |
| source_return_line_id | INT | UNIQUE, NOT NULL | Grain/idempotency key |
| return_number / order_number | VARCHAR | NOT NULL | Degenerate |
| reason_code | VARCHAR(20) | NOT NULL | Degenerate, from `return_reasons.code` |
| disposition_code | VARCHAR(20) | NULL | Degenerate, from `return_dispositions.code`; NULL until inspected (BR-5) |
| product_key | INT | FK → dim_product | |
| customer_key | INT | FK → dim_customer | |
| return_date_key | INT | FK → dim_date | |
| returned_quantity | INT | NOT NULL | |
| unit_price / unit_cost | DECIMAL(12,2) | NOT NULL | From the originating order_lines |
| return_value / return_cost_value | DECIMAL(12,2) | NOT NULL, additive | |

### summary_daily_revenue_by_region
The one summary table TDD §10 names by example. Physical table (TDD §15), grain `(region, date)` — no separate surrogate key. Empty shell built in Phase 4; Phase 5's ETL populates it from `fact_orders` joined through `dim_customer → dim_region`. The entire Phase 4 summary-table deliverable — no others are built.

| Column | Type | Constraints | Meaning |
|---|---|---|---|
| region_key | INT | PK (composite), FK → dim_region | |
| date_key | INT | PK (composite), FK → dim_date | |
| total_orders / total_order_lines | INT | NOT NULL | |
| total_revenue / total_gross_margin | DECIMAL(12,2) | NOT NULL | |

---

## Deliberate design notes (for interview defensibility)

- **Price/cost snapshotting:** `purchase_order_lines.unit_cost` and `order_lines.unit_price`/`unit_cost` duplicate values also on `products` — by design, so historical spend/revenue/margin don't shift when a product's current price changes. Documented 3NF exception, not an oversight.
- **Polymorphic soft-reference:** `inventory_transactions.source_reference_type/id` is the one relationship in this schema not enforced as a DB-level FK (ADR-002's one documented exception), because MySQL cannot FK a single column to multiple target tables.
- **Lookup tables beyond TDD §4.1's literal list:** `regions`, `inventory_transaction_types`, `po_statuses`, `order_statuses`, `shipment_statuses`, `return_reasons`, `return_dispositions`, `vehicle_types` implement the TDD's own stated principle ("status fields as constrained enumerations, not free text") and the Roadmap's explicit call for "status codes, regions, vehicle types" reference-data loaders — they are the implementation of that principle, not new scope.
- **`created_at`/`updated_at` on every table:** added structurally now because Phase 5's incremental ETL (ADR-008) requires indexed watermark columns; retrofitting after Phase 1 would be a destructive schema change.

---

## Phase 2 addendum: Domain Service business-rule semantics

The schema above doesn't (and shouldn't) encode the following — they're
business-logic decisions made in `backend/app/domains/` and documented
here since no lookup table's `code`/`name` column can express them.

- **`po_statuses` lifecycle (BR-1):** `DRAFT` -> `SUBMITTED` -> `CONFIRMED`
  -> `FULFILLED` -> `CLOSED`. A PO reaches `FULFILLED` only when every
  line's `received_quantity` is within `PO_RECEIPT_TOLERANCE` (2%
  under-receipt allowed — a value not specified in the SRS/TDD, confirmed
  with the project owner at the Phase 2 review gate; see
  `procurement/service.py`) of `ordered_quantity`. Only *accepted*
  quantity (`received_quantity - quality_rejected_quantity`) is ever
  added to `inventory_positions.quantity_on_hand`.
- **`order_statuses` derivation (BR-2, FR-4.2):** computed from the sum
  of each order's lines' `allocated_quantity`/`backordered_quantity` —
  `PENDING` (nothing attempted yet) -> `ALLOCATED` (fully allocated) /
  `BACKORDERED` (nothing at all could be allocated) / a mixed result is
  `PARTIALLY_FULFILLED`. See `orders/service.py:compute_order_status`,
  a pure function tested independently of the database.
- **`inventory_positions.quantity_reserved` is a soft hold, not a
  physical pick:** allocating an order line increments `quantity_reserved`
  (FR-4.2) without moving `quantity_on_hand` or writing an
  `inventory_transactions` row — nothing has physically moved yet. Phase
  2 does not wire order allocation through to shipment dispatch (not a
  named Phase 2 deliverable), so the physical pick that would decrement
  `quantity_on_hand` is left for whichever phase builds that dispatch flow.
- **Zone choice is a caller decision, not a bin-picking algorithm:**
  every function that touches inventory (receiving, allocating,
  restocking a return) takes an explicit `warehouse_zone_id` /
  `inventory_position_id` from its caller. FR-2.2 explicitly places
  "advanced warehouse slotting and optimization" out of MVP scope, so no
  Domain Service searches across zones for available stock.
