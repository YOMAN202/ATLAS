# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Development Roadmap — Execution Blueprint
**Version 1.1**
*Sources of truth: ATLAS-SRS.md v1.3 (FROZEN), ATLAS-TDD.md v1.1 (FROZEN)*

---

## 0. Ordering Reconciliation (READ FIRST)

The requested phase list was reviewed against the frozen TDD. **Two ordering conflicts were found and corrected here.** Per the governance rule ("flag conflicts rather than silently change the design"), both are documented explicitly. No scope, features, or technologies were added — only the *sequence* was corrected to respect dependencies already fixed in the TDD.

### Conflict 1 — Simulation cannot precede the Domain Service layer
- **Requested:** Phase 2 = Simulation Engine, then Phase 3 = Backend (which contains domain services).
- **Conflict:** TDD **ADR-007** and TDD §5 state the simulation engine writes *through* the OLTP domain service layer, never directly to the database. The domain services must therefore **exist before** the simulation can run.
- **Correction:** The domain-service portion of "Backend" is pulled forward into its own phase **before** the simulation engine. The REST API portion of "Backend" stays later (it reads the warehouse, which doesn't exist until after ETL).

### Conflict 2 — ETL cannot precede the OLAP Warehouse schema
- **Requested:** Phase 4 = ETL Pipeline, then Phase 5 = OLAP Warehouse.
- **Conflict:** ETL's Load stage writes into the warehouse fact/dimension tables. The warehouse schema must **exist before** the ETL that populates it. Building ETL against a non-existent target is impossible and would force rework.
- **Correction:** OLAP Warehouse schema is built **before** the ETL pipeline. (This also matches the TDD §9 critical-path graph, where S4 Warehouse precedes S5–S6 ETL.)

### Corrected phase sequence and mapping to your request

| Blueprint Phase | Content | Maps to your requested |
|---|---|---|
| Phase 0 | Initialization / Repo / Docker / CI / Tooling | Phase 0 ✓ |
| Phase 1 | OLTP Database (schema, constraints, indexes, migrations, reference data) | Phase 1 ✓ |
| Phase 2 | **Domain Services & Business Rules** | *(pulled from your Phase 3 "Backend")* |
| Phase 3 | Simulation Engine | your Phase 2 |
| Phase 4 | **OLAP Warehouse** (dimensions, facts, summary tables, indexes) | your Phase 5 *(moved ahead of ETL)* |
| Phase 5 | ETL Pipeline (extract, DQ, transform, SCD2, load, audit, watermark) | your Phase 4 *(moved after warehouse)* |
| Phase 6 | Backend API (REST, validation, security, role-based access) | *(REST-API remainder of your Phase 3 "Backend")* |
| Phase 7 | Business Intelligence & Decision Support (Power BI, recommendations, forecasting) | your Phase 6 |
| Phase 8 | Frontend (Next.js dashboards, admin UI, role views, charts, tables) | your Phase 7 |
| Phase 9 | Testing & Optimization | your Phase 8 |
| Phase 10 | Documentation & Release | your Phase 9 |

The result is 11 phases (0–10) rather than 10, because "Backend" legitimately splits across the timeline: domain services are a *write-path foundation* needed early; the REST API is a *read-path surface* needed late. Everything you listed is present; nothing was added.

### A note on "continuous testing" and "docs at every milestone"
Per your optimization goals, **testing and documentation are per-phase deliverables throughout**, not deferred. Phase 9 (Testing & Optimization) and Phase 10 (Documentation & Release) are *consolidation/hardening* phases — system-level performance work and final polish — **not** the first place tests or docs appear. Every phase below ships with its own tests and updates the data dictionary / ADRs.

---

## 1. Roadmap Principles

1. **Working software at every phase boundary.** Each phase ends demonstrable, even if narrow.
2. **Data model first, then vertical slices.** Schemas (Phases 1, 4) are stabilized and reviewed before dependent code is written — this is the single biggest rework-avoidance lever.
3. **The two schema phases get explicit review gates** before downstream work starts (TDD risk mitigation for "schema mistakes discovered late").
4. **Tests and docs travel with the code**, per phase.
5. **The MVP is a complete, coherent product**, not a pile of half-features. The cut line is defended, not aspirational.

---

## 2. Phase Details

Each phase below specifies: Objective · Deliverables · Dependencies · Estimated Effort · Risks · Definition of Done · Testing Requirements · Expected Commits · Expected Project Structure (populated) · Expected Artifacts · Expected Screenshots · Expected Documentation.

---

### PHASE 0 — Initialization & Scaffolding

**Objective:** Stand up a running skeleton so every later phase has a home; establish tooling and standards once.

**Deliverables:**
- Git repo initialized; branch strategy documented (trunk-based with short-lived feature branches).
- Full folder structure created (see §3).
- `docker-compose.yml` booting MySQL 8 + backend + frontend (empty apps that run).
- `.env.example` with placeholders; real `.env` git-ignored; env-var config loading (SEC-4).
- Alembic initialized against the OLTP schema.
- GitHub Actions CI: lint (ruff/black for Python, eslint/prettier for TS) + empty pytest run, all green.
- Coding standards doc (naming, formatting, commit-message convention: Conventional Commits).
- Initial versions of the four TDD diagrams committed under `docs/diagrams/`.

**Dependencies:** None.

**Estimated Effort:** ~0.5 week. Difficulty 3/10.

**Risks:** Low. Main risk is over-investing in tooling gold-plating — timebox it.

**Definition of Done:** `docker compose up` boots all services; CI green on empty test; standards doc and diagram stubs committed.

**Testing Requirements:** CI pipeline itself proven working (a trivial passing test); linting enforced.

**Expected Commits:** `chore: initialize repo and folder structure` · `chore: docker-compose with mysql8, backend, frontend` · `chore: env-var config + .env.example` · `chore: alembic init` · `ci: lint + test pipeline` · `docs: coding standards + initial diagrams`.

**Expected Project Structure (populated):** root files, `docs/`, empty `backend/app`, `frontend/app`, `etl/`, `simulation/` skeletons.

**Expected Artifacts:** running compose stack; green CI badge.

**Expected Screenshots:** CI passing; `docker compose ps` showing services up.

**Expected Documentation:** README (overview + setup), coding standards, diagram stubs.

---

### PHASE 1 — OLTP Database

**Objective:** Design and implement the full normalized operational schema — the foundation for everything downstream.

**Deliverables:**
- All OLTP tables as SQLAlchemy models + Alembic migrations: suppliers, products, warehouses, warehouse_zones, inventory_positions, inventory_transactions, purchase_orders, purchase_order_lines, carriers, shipments, shipment_events, customers, orders, order_lines, returns, return_lines, and status lookup tables.
- Database-level FK constraints (ADR-002); `DECIMAL(12,2)` money types (NFR-4); unique constraints on business keys — order_number, po_number, shipment_number (DQ-2); 3NF (NFR-1).
- Index plan implemented per TDD §4.3 (FK indexes explicit; documented).
- Seed/reference data loaders for static lookups (status codes, regions, vehicle types).
- ER diagram finalized to match the implemented schema.
- Data dictionary: OLTP section complete.

**Dependencies:** Phase 0.

**Estimated Effort:** ~1 week. Difficulty 7/10.

**Risks:** **High-leverage.** Schema errors here propagate everywhere. Mitigated by the review gate below.

**Definition of Done:** Migrations apply cleanly to empty MySQL and roll back cleanly; ER diagram + data dictionary match reality; constraint tests pass. **→ SCHEMA REVIEW GATE before Phase 2.**

**Testing Requirements:** Unit tests for constraints (unique business keys enforced; FK violations rejected; DECIMAL precision correct); migration up/down tested in CI against a containerized MySQL.

**Expected Commits:** `feat(db): supplier + product + warehouse tables` · `feat(db): inventory positions + transactions` · `feat(db): procurement (PO + lines)` · `feat(db): orders + order lines + returns` · `feat(db): transportation (carriers, shipments, events)` · `feat(db): status lookup tables + seed data` · `test(db): constraint + migration tests` · `docs: finalize ERD + OLTP data dictionary`.

**Expected Project Structure (populated):** `backend/app/models/` (OLTP models), `backend/alembic/versions/`, seed loaders.

**Expected Artifacts:** applied migration set; populated reference/lookup tables.

**Expected Screenshots:** ER diagram; a `SHOW CREATE TABLE` for a representative table showing constraints.

**Expected Documentation:** finalized ERD; OLTP data dictionary.

---

### PHASE 2 — Domain Services & Business Rules  *(pulled ahead of Simulation — Conflict 1)*

**Objective:** Implement the business-rule-enforcing OLTP service layer that both the simulation engine (Phase 3) and the REST API (Phase 6) will call. This is the write-path foundation (ADR-007).

**Deliverables:**
- Domain service functions per module: order create/advance with partial fulfillment + backorder (BR-2); PO lifecycle draft→…→closed with receipt-tolerance rule (BR-1); inventory transactions (receipt/pick/transfer/adjustment) with non-negative guarantee (BR-2); shipment lifecycle; returns with inspection/disposition step (BR-5).
- Zone-level allocation (FR-2.2, MVP scope): inventory positions associated with warehouse zones, zone capacity modeled, and inventory movements respecting zone assignments. (Advanced slotting/optimization is a future enhancement, out of scope.)
- Business rules BR-1–BR-5 enforced in code with tests.
- Data dictionary updated where service logic implies derived fields.

**Dependencies:** Phase 1 (+ its review gate).

**Estimated Effort:** ~1 week. Difficulty 8/10.

**Risks:** Medium-high. Business-rule edge cases (partial fulfillment, backorders, inspection routing) are where subtle bugs hide. Mitigated by rule-level unit tests.

**Definition of Done:** Every MVP-relevant business rule (SRS §14) has a passing unit test; services enforce integrity with no UI present.

**Testing Requirements:** Unit tests per business rule, including negative/edge cases (allocate more than stock → partial + backorder; PO receipt outside tolerance → not fulfilled; return failing inspection → separate disposition, sellable stock unchanged).

**Expected Commits:** `feat(domain): order allocation with partial fulfillment + backorder` · `feat(domain): PO lifecycle + receipt tolerance` · `feat(domain): inventory transactions (non-negative)` · `feat(domain): zone-aware inventory positions + zone capacity` · `feat(domain): shipment lifecycle` · `feat(domain): returns + inspection disposition` · `test(domain): business-rule suite BR-1..BR-5`.

**Expected Project Structure (populated):** `backend/app/domains/{procurement,inventory,warehousing,transportation,orders,returns}/`.

**Expected Artifacts:** callable, tested domain service layer.

**Expected Screenshots:** test report showing business-rule suite passing.

**Expected Documentation:** data dictionary updates; brief service-layer notes in module READMEs.

---

### PHASE 3 — Simulation Engine  *(your Phase 2)*

**Objective:** Bring the company alive — generate a realistic 5-year operational history through the domain services.

**Deliverables:**
- Day-advancing simulation loop calling domain services only (never direct DB writes).
- Generators: seasonality-aware demand/orders (FR-5.3); supplier deliveries with lead-time distributions + occasional lateness; warehouse operations; shipment/transport generation with cost model; returns at realistic rates with reason codes.
- **Purchase Order Generator** (FR-1.2): the Simulation Engine's internal reorder heuristic that triggers purchase-order creation during data generation (through Domain Services), populating procurement history. This is the operational PO-generation logic — intentionally distinct from the Phase 7 Decision Support reorder recommendation, which is analytical and warehouse-derived. The two are separate systems and are not to be conflated.
- World-state config: 8 warehouses, ~5,000 SKUs, ~100 suppliers (TDD §10).
- Full-run capability generating the 5-year target dataset (1–2M order lines, ~500k shipments).
- Faker used only for master/reference data (names, addresses), not business-event logic.

**Dependencies:** Phase 2.

**Estimated Effort:** ~1 week. Difficulty 8/10.

**Risks:** Medium-high. Two failure modes: (a) data that looks random/unrealistic (undermines the whole premise), (b) generation too slow to produce 5 years in reasonable time. Mitigate by validating realism early on a 3-month run before the full 5-year run, and profiling generation.

**Definition of Done:** A full run produces a rule-consistent 5-year OLTP dataset at target volume; spot-checks show visible seasonality, varied supplier performance, present returns; generation completes in a practical wall-clock time.

**Testing Requirements:** Tests that generated data obeys business rules (no negative inventory, valid lifecycles); statistical sanity checks (demand seasonality present; supplier on-time distribution within expected bounds).

**Expected Commits:** `feat(sim): day-advancing loop over domain services` · `feat(sim): seasonal demand + order generator` · `feat(sim): purchase-order generator (internal reorder heuristic)` · `feat(sim): supplier delivery generator (lead-time + lateness)` · `feat(sim): transport + shipment cost model` · `feat(sim): returns generator` · `feat(sim): world-state config (8 wh, 5k SKU, 100 suppliers)` · `test(sim): rule-consistency + realism checks`.

**Expected Project Structure (populated):** `simulation/engine.py`, `simulation/generators/`, `simulation/config/`.

**Expected Artifacts:** a fully populated 5-year OLTP database; a config file defining world state.

**Expected Screenshots:** a chart of simulated monthly order volume showing seasonality; row-count summary of the generated dataset.

**Expected Documentation:** simulation design notes (rules + distributions used); data-realism validation summary.

---

### PHASE 4 — OLAP Warehouse  *(your Phase 5 — moved ahead of ETL, Conflict 2)*

**Objective:** Design and implement the dimensional warehouse the ETL will populate.

**Deliverables:**
- Dimension tables: dim_date, dim_product, dim_supplier (SCD2), dim_warehouse (SCD2), dim_carrier, dim_customer, dim_region (ADR-006).
- Fact tables at defined grains: fact_orders (order line), fact_shipments (shipment), fact_inventory_snapshot (SKU×warehouse×day), fact_procurement (PO line), fact_supplier_delivery (delivery event), fact_returns (return line) — per TDD §4.2.1.
- Physical pre-aggregated summary table definitions (structure only; populated by ETL in Phase 5).
- Indexing strategy implemented (composite indexes per TDD §4.3); date-partition hook noted for fact_inventory_snapshot if warranted.
- Star schema diagram finalized; data dictionary extended to OLAP.

**Dependencies:** Phase 1 (source shape), and ideally Phase 3 done (real data to validate design against). Design work may overlap Phase 3.

**Estimated Effort:** ~1 week. Difficulty 7/10.

**Risks:** **High-leverage** (second schema). Grain mistakes are expensive downstream. Mitigated by the review gate below.

**Definition of Done:** Warehouse DDL creates cleanly; star schema diagram + OLAP data dictionary complete; summary-table shells exist. **→ GRAIN/SCHEMA REVIEW GATE before Phase 5.**

**Testing Requirements:** DDL apply/teardown tested in CI; a smoke test inserting a handful of synthetic rows validates FK resolution fact→dim and SCD2 column structure.

**Expected Commits:** `feat(dw): conformed dimensions` · `feat(dw): SCD2 structure on supplier + warehouse` · `feat(dw): fact tables at defined grains` · `feat(dw): summary table shells` · `feat(dw): warehouse indexing strategy` · `docs: finalize star schema + OLAP data dictionary`.

**Expected Project Structure (populated):** `etl/warehouse_ddl/`.

**Expected Artifacts:** created OLAP schema (empty facts/dims + summary shells).

**Expected Screenshots:** star schema diagram; dimension table showing SCD2 columns (effective_from / effective_to / is_current / surrogate key).

**Expected Documentation:** finalized star schema diagram; OLAP data dictionary.

---

### PHASE 5 — ETL Pipeline  *(your Phase 4 — moved after warehouse)*

**Objective:** Move data from OLTP into the warehouse correctly, cleanly, and repeatably — the technical high-water mark of the project.

**Deliverables (Stage A — Extract, Validate, DQ):**
- Incremental, watermark-based extraction (ADR-008).
- Data quality checks DQ-1–DQ-6 (completeness, uniqueness, referential integrity, duplicate detection, invalid values) with failing records routed to `dq_quarantine` and the violated rule recorded.
- `etl_run_log` audit table + per-run metrics (DQ-6).

**Deliverables (Stage B — Transform, Load, SCD2, Score):**
- Transform layer mapping OLTP → facts/dims; derived measures computed.
- SCD2 logic for supplier + warehouse (versioned rows on tracked-attribute change), tested.
- Transactional, idempotent batch load (NFR-3).
- Pre-aggregated summary tables populated during load (TDD §10 decision).
- Per-run + per-table data quality score (DQ-7).
- Full pipeline runnable end-to-end; meets the NFR-8 batch-window target on the full dataset.

**Dependencies:** Phase 3 (source data) + Phase 4 (target schema + its review gate).

**Estimated Effort:** ~1.5–2 weeks (largest phase). Difficulty 9/10.

**Risks:** **Highest single-phase risk.** SCD2 correctness, idempotency, and hitting the batch-window at full volume are all non-trivial. Most likely place to slip. Mitigate by building Stage A fully (with its DQ test suite) before Stage B, and testing SCD2 on a deliberately constructed mid-history change.

**Definition of Done:** A full ETL run populates the entire warehouse from the 5-year OLTP dataset; re-running is idempotent (no duplicate/corrupt rows); SCD2 verified via a constructed supplier-term change producing correct versioned rows; DQ score computed and stored; batch window met.

**Testing Requirements:** Dedicated DQ suite proving each DQ-1–DQ-7 rule catches its bad-data case (SRS risk: DQ framework must not give false confidence); integration test of full extract→…→audit; idempotency test (run twice → identical warehouse state); SCD2 correctness test.

**Expected Commits:** `feat(etl): watermark-based incremental extract` · `feat(etl): DQ checks + quarantine routing` · `feat(etl): etl_run_log audit` · `test(etl): data-quality rule suite` · `feat(etl): transform to facts/dims` · `feat(etl): SCD2 for supplier + warehouse` · `feat(etl): transactional idempotent load` · `feat(etl): populate summary tables` · `feat(etl): DQ scoring` · `test(etl): idempotency + SCD2 + full-pipeline integration`.

**Expected Project Structure (populated):** `etl/extract/`, `etl/validate/`, `etl/transform/`, `etl/load/`, `etl/pipeline.py`, `etl/tests/`.

**Expected Artifacts:** fully populated warehouse; populated summary tables; audit log with metrics + DQ scores; quarantine table demonstrating caught bad data.

**Expected Screenshots:** ETL run log output (row counts per stage, duration); DQ score summary; a quarantine record showing the violated rule; SCD2 dimension rows for one supplier across a term change.

**Expected Documentation:** finalized ETL flow diagram; ETL + DQ notes in `docs/`; ADR updates if any implementation nuance arose.

---

### PHASE 6 — Backend API  *(REST-API remainder of your Phase 3 "Backend")*

**Objective:** Expose the warehouse (reads) and necessary OLTP admin operations (writes) via a secured REST API.

**Deliverables:**
- Dashboard read endpoints over OLAP (executive, inventory, warehouse, transportation, supplier, data-quality), hitting summary tables where defined.
- Admin/reference-data write endpoints through Phase 2 domain services.
- Pydantic validation on all input (SEC-2); parameterized queries throughout (SEC-1).
- Three MySQL roles wired — atlas_app, atlas_etl, atlas_reporting (SEC-3); role-based access middleware for the four actors (SEC-5).
- Response caching keyed to ETL run version (TDD §7) for expensive aggregates.

**Dependencies:** Phase 5 (warehouse populated).

**Estimated Effort:** ~1 week. Difficulty 6/10.

**Risks:** Medium. Main risk is endpoints that don't meet NFR-10 latency because they hit raw facts instead of summary tables — caught by latency tests.

**Definition of Done:** All MVP dashboard endpoints return correct data within NFR-10 latency; role restrictions enforced and tested; caching invalidates on ETL completion.

**Testing Requirements:** API tests (FastAPI test client) for each endpoint; role-access tests (each actor sees only permitted resources); latency assertions against target volume; input-validation tests (malformed input rejected).

**Expected Commits:** `feat(api): executive + inventory dashboard endpoints` · `feat(api): warehouse + transportation + supplier endpoints` · `feat(api): data-quality endpoint` · `feat(api): admin reference-data endpoints via domain services` · `feat(security): 3 DB roles + role-based middleware` · `feat(api): ETL-versioned response cache` · `test(api): endpoint + role-access + latency`.

**Expected Project Structure (populated):** `backend/app/api/` (v1 routes), `backend/app/core/security.py`.

**Expected Artifacts:** running, documented REST API (FastAPI auto-docs at `/docs`).

**Expected Screenshots:** FastAPI Swagger UI; a role-access test showing a forbidden resource blocked; a latency test result.

**Expected Documentation:** API overview; auth/role model notes; security section (SEC-1–SEC-5) marked implemented.

---

### PHASE 7 — Business Intelligence & Decision Support  *(your Phase 6)*

**Objective:** Deliver the explainable analytics that differentiate ATLAS from a plain dashboard project, plus the Power BI deliverable.

**Deliverables:**
- **Decision support (rule-based, explainable):** reorder recommendations — reorder point = avg daily demand × lead time + safety stock (BR-3) — with contributing factors surfaced (FR-8.1, UC-1); supplier risk alerts referencing the triggering metric + threshold (FR-8.2); route/cost optimization suggestions from historical route efficiency (FR-8.3); every recommendation traceable to inputs (FR-8.4).
- **Forecasting:** statistical demand forecasting (moving average / exponential smoothing, ADR-004); forecast-vs-actual + MAPE for the Planning view (FR-7.4).
- **Power BI (parallel track — can start any time after Phase 5):** report set connected read-only via atlas_reporting, reproducing 2–3 executive/operational views (ADR-005).

**Dependencies:** Phase 5 (warehouse data). Power BI can run in parallel with Phase 6.

**Estimated Effort:** ~1.5 weeks. Difficulty 8/10.

**Risks:** Medium. Recommendation logic must be *correct and explainable*, not just plausible — the explainability is the point. Mitigate with logic tests asserting the "why" matches the inputs.

**Definition of Done:** Recommendations generate correctly, each with visible reasoning traceable to data; forecast accuracy (MAPE) computed; Power BI report set connects and renders.

**Testing Requirements:** Unit tests for reorder-point math (BR-3), risk-alert thresholds, forecast calculations; a traceability test asserting each recommendation's stated factors equal its actual inputs.

**Expected Commits:** `feat(ds): reorder recommendations + reasoning` · `feat(ds): supplier risk alerts` · `feat(ds): route/cost optimization suggestions` · `feat(ds): statistical demand forecasting + MAPE` · `test(ds): recommendation logic + traceability` · `feat(bi): Power BI report set on atlas_reporting`.

**Expected Project Structure (populated):** `backend/app/decision_support/`.

**Expected Artifacts:** generated recommendations with reasoning; forecast series with accuracy metrics; a `.pbix` Power BI file.

**Expected Screenshots:** a reorder recommendation with its "why" panel; a supplier risk alert with the triggering metric; forecast-vs-actual chart; Power BI dashboard.

**Expected Documentation:** decision-support rules documented (each rule + inputs + formula); forecasting method notes; Power BI setup/connection guide.

---

### PHASE 8 — Frontend  *(your Phase 7)*

**Objective:** The user-facing product surface — all dashboards, admin UI, role-based views, presented to a commercial-product standard.

**Deliverables:**
- Next.js App Router shell; role-based route groups (Executive / Operations / Planner / Admin); typed API client aligned to the backend schema.
- **Executive Overview** dashboard (FR-7.1): revenue, margin, service level, order-volume trends.
- **Operational** dashboards (FR-7.2): Inventory, Warehouse, Transportation, Supplier.
- **Risk & Exceptions** view (FR-7.3).
- **Forecasting & Planning** dashboard (FR-7.4) showing forecasts + reorder recommendations from Phase 7, including the "why" behind each recommendation.
- **Data Quality** dashboard (FR-7.5): DQ scores over time, quarantine rates, per-check breakdown.
- **Admin UI** for reference-data management.
- ECharts for charts, TanStack Table for tabular drill-downs, shadcn/ui + Tailwind design system, Framer Motion used sparingly (per TDD §8 — commercial, not flashy).

**Dependencies:** Phase 6 (endpoints) + Phase 7 (recommendations/forecasts to display).

**Estimated Effort:** ~1.5 weeks. Difficulty 6/10.

**Risks:** Medium. Risk of dashboards that miss NFR-9 latency (mitigated: they hit summary-table-backed endpoints) or a visually inconsistent UI (mitigated by committing to the shadcn/Tailwind system up front).

**Definition of Done:** All MVP dashboards + admin UI render real data, are interactive (filter/drill), enforce role-based views, and meet NFR-9 latency at target volume.

**Testing Requirements:** Component tests for key dashboards; an end-to-end smoke test (load each dashboard, apply a filter, drill down); visual consistency check against the design system.

**Expected Commits:** `feat(fe): app shell + role-based routing + API client` · `feat(fe): executive overview dashboard` · `feat(fe): inventory + warehouse dashboards` · `feat(fe): transportation + supplier dashboards` · `feat(fe): risk & exceptions view` · `feat(fe): forecasting & planning + recommendation reasoning` · `feat(fe): data quality dashboard` · `feat(fe): admin reference-data UI` · `test(fe): component + e2e smoke`.

**Expected Project Structure (populated):** `frontend/app/` (route groups), `frontend/components/`, `frontend/lib/`.

**Expected Artifacts:** the running ATLAS web application.

**Expected Screenshots:** every dashboard (these become the portfolio/README screenshots); the admin UI; a role-restricted view.

**Expected Documentation:** frontend README; a short UI walkthrough; screenshot set captured for the portfolio.

---

### PHASE 9 — Testing & Optimization  *(your Phase 8)*

**Objective:** System-level hardening — performance, query optimization, and end-to-end validation across the whole platform. (Per-phase tests already exist; this phase is consolidation, not first-time testing.)

**Deliverables:**
- Query optimization pass: `EXPLAIN` analysis on the heaviest dashboard/warehouse queries; add/adjust indexes or summary tables where NFR-9 is missed; document before/after.
- ETL performance validation against the full 5-year dataset; confirm NFR-8 batch window; tune if needed.
- Load-style testing of API endpoints at target volume for NFR-10.
- Full data-quality verification run; confirm scores and quarantine behavior end-to-end.
- Consolidated API test pass; bug-fix sweep.

**Dependencies:** Phases 5–8 complete.

**Estimated Effort:** ~1 week. Difficulty 6/10.

**Risks:** Medium. This phase can *reveal* problems that require real fixes (e.g. a query that won't hit target latency). That's its purpose — budget for fixes, don't treat it as a rubber stamp.

**Definition of Done:** NFR-8, NFR-9, NFR-10 targets demonstrably met at target volume, with `EXPLAIN`/timing evidence documented; no known correctness bugs in core flows; DQ verification clean.

**Testing Requirements:** Performance/timing evidence captured; query plans documented; full regression run green in CI.

**Expected Commits:** `perf(dw): index tuning from EXPLAIN analysis` · `perf(etl): batch-window optimization` · `perf(api): endpoint latency tuning` · `test: full-volume performance + regression` · `fix: <bugs surfaced during hardening>`.

**Expected Project Structure (populated):** performance notes under `docs/`; possibly new migration(s) for added indexes.

**Expected Artifacts:** a performance report (targets, measured results, query plans before/after).

**Expected Screenshots:** an `EXPLAIN` before/after; a dashboard-latency measurement at target volume; ETL batch-window timing.

**Expected Documentation:** performance/optimization report; updated ADRs if tuning changed any documented decision.

---

### PHASE 10 — Documentation & Release  *(your Phase 9)*

**Objective:** Make ATLAS presentable, reproducible, and interview-ready. (Diagrams and the data dictionary were built incrementally; this phase finalizes and packages everything.)

**Deliverables:**
- **README** finalized: overview, architecture summary, feature list, screenshots, one-command setup, tech stack, and the honest scope/MVP statement.
- **Diagrams** finalized and embedded: System Architecture, ERD, Star Schema, ETL Flow (DOC-1–DOC-4).
- **Data Dictionary** finalized across OLTP + OLAP (DOC-5).
- **ADRs** finalized — the full set, each with decision/alternatives/rationale (DOC-6).
- **Screenshots** — full set of dashboards + key flows.
- **Demo walkthrough** — a scripted narrative (or short recorded demo) showing data → ETL → warehouse → dashboards → a recommendation with its reasoning.
- **Deployment guide** — `docker compose up` path plus the single-VM deployment note (containerized design makes this small; live deploy itself is a stretch goal).
- **Resume bullets** — quantified, honest (see samples below).
- **Interview preparation notes** — the ADRs restated as "why did you…" Q&A, plus the MySQL-vs-Postgres discussion (ADR-010), the grain/SCD2 reasoning, and the DQ framework.

**Dependencies:** Everything.

**Estimated Effort:** ~0.5–1 week. Difficulty 4/10.

**Risks:** Low — but do not skip. A strong platform with weak documentation under-sells the work in exactly the moment (portfolio skim, interview) that matters.

**Definition of Done:** A stranger can clone, run `docker compose up`, and reach a working ATLAS from the README alone; every diagram and the data dictionary are current; the ADR set is complete; resume bullets and interview notes exist.

**Testing Requirements:** A clean-clone reproducibility test — fresh checkout, follow README only, confirm the stack comes up and the simulation→ETL→dashboards path works.

**Expected Commits:** `docs: finalize README + screenshots` · `docs: finalize architecture/ERD/star-schema/ETL diagrams` · `docs: complete data dictionary` · `docs: complete ADR set` · `docs: demo walkthrough + deployment guide` · `docs: resume bullets + interview notes`.

**Expected Project Structure (populated):** complete `docs/` tree; `docs/adr/` fully populated; `docs/diagrams/` finalized.

**Expected Artifacts:** portfolio-ready README; complete documentation set; demo materials.

**Expected Screenshots:** hero screenshots for README; the demo walkthrough frames.

**Expected Documentation:** the whole set, finalized.

**Sample resume bullets (to refine with real measured numbers):**
- Designed and built a supply-chain analytics platform on MySQL 8 with a normalized OLTP schema and a Kimball star-schema warehouse (6 fact tables at distinct grains, SCD2 dimensions), populated from a rule-driven simulation of ~5 years of operations (1–2M order lines).
- Engineered an incremental, watermark-based ETL pipeline with a data-quality framework (completeness, referential integrity, duplicate/invalid detection, per-run quality scoring) and audit logging, meeting a sub-30-minute batch window at full volume.
- Delivered executive and operational dashboards plus explainable, rule-based decision support (reorder, supplier-risk, route optimization) with statistical demand forecasting, exposed via a FastAPI backend (role-based access, three least-privilege DB roles) and a Next.js/TypeScript frontend, alongside Power BI reporting.

**Interview-prep note topics (to write up from the ADRs):** why MySQL over PostgreSQL (ADR-010, including where Postgres is stronger); why a periodic snapshot fact for inventory (ADR-003); why SCD2 only on supplier/warehouse (ADR-006); why incremental ETL over full reload (ADR-008); why the simulation writes through domain services (ADR-007); how the data-quality framework works and how it's tested; why a modular monolith over microservices.

---

## 3. Folder Structure (deferred from TDD, defined here)

```
atlas/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
│   ├── srs.md
│   ├── tdd.md
│   ├── roadmap.md
│   ├── data-dictionary.md
│   ├── adr/                     # one file per ADR (001..010+)
│   └── diagrams/                # ER, star schema, ETL flow, architecture
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── core/                # config, db session, security, settings
│   │   ├── domains/             # modular-monolith boundaries (Phase 2)
│   │   │   ├── procurement/
│   │   │   ├── inventory/
│   │   │   ├── warehousing/
│   │   │   ├── transportation/
│   │   │   ├── orders/
│   │   │   └── returns/
│   │   ├── decision_support/    # reorder, risk, route, forecasting (Phase 7)
│   │   ├── api/                 # v1 route definitions (Phase 6)
│   │   └── models/              # SQLAlchemy OLTP models (Phase 1)
│   ├── alembic/                 # migrations
│   └── tests/
├── simulation/
│   ├── engine.py                # day-advancing loop (Phase 3)
│   ├── generators/              # order, supplier, warehouse, transport, returns
│   └── config/                  # world-state config
├── etl/
│   ├── pipeline.py              # extract→validate→transform→load→audit (Phase 5)
│   ├── extract/
│   ├── validate/                # DQ-1..DQ-7
│   ├── transform/               # fact/dim mapping + SCD2
│   ├── load/
│   ├── warehouse_ddl/           # OLAP schema (Phase 4)
│   └── tests/
└── frontend/
    ├── app/                     # Next.js App Router; role-based route groups (Phase 8)
    ├── components/              # dashboards, charts, tables
    ├── lib/                     # API client, types
    └── ...
```

---

## 4. Weekly Sprint Plan

One phase ≈ one sprint, except the ETL phase (largest) spans ~1.5–2 sprints and Phases 7–8 are ~1.5 each. Each sprint ends with something demonstrable.

| Week | Sprint Focus | Demonstrable at week's end |
|---|---|---|
| 1 | Phase 0 + start Phase 1 | Stack boots via compose; CI green; first OLTP tables migrating |
| 2 | Finish Phase 1 → **schema review gate** | Full OLTP schema live; ERD + data dictionary; constraint tests pass |
| 3 | Phase 2 | Domain services enforcing BR-1–BR-5; business-rule tests pass |
| 4 | Phase 3 | Simulation generating realistic multi-year data (validate on 3-month run, then full 5-year) |
| 5 | Phase 4 → **grain review gate** | Warehouse schema + star diagram; SCD2 structure; summary shells |
| 6 | Phase 5 Stage A | Incremental extract + full DQ framework + quarantine + audit log; DQ tests pass |
| 7 | Phase 5 Stage B | Transform + SCD2 + idempotent load + summary tables + DQ score; **warehouse fully populated** |
| 8 | Phase 6 | Secured REST API over the warehouse; role-based access; Swagger docs |
| 9 | Phase 7 (+ Power BI parallel) | Reorder/risk/route recommendations with reasoning + forecasting; Power BI report |
| 10 | Phase 8 (part 1) | Executive + operational dashboards rendering real data |
| 11 | Phase 8 (part 2) + Phase 9 | Full dashboard suite + admin UI; performance/optimization pass |
| 12 | Phase 10 (+ buffer) | Docs, diagrams, demo, resume bullets finalized; clean-clone reproducibility check |

**MVP functionally complete at end of Week 11** (platform works end-to-end). **Week 12 is documentation/release + buffer.** If earlier phases slip, Week 12 buffer absorbs it and the MVP cut line (below) protects scope.

---

## 5. MVP Boundary

**MVP (the flagship deliverable) = Phases 0–10:** a complete, coherent platform — rule-driven simulation → clean incremental ETL with a tested data-quality framework → dimensional warehouse → secured API → full dashboard suite → explainable decision support + forecasting → Power BI reporting → full documentation. This is what goes on the resume and gets demoed.

- **Testing & documentation are inside the MVP**, not optional — they're what make it presentable and reproducible.
- **Phase 2 features (post-MVP, exactly as frozen in the SRS):** Scenario / What-If Analysis (SRS §6.9) — supplier disruption, demand spike, capacity reduction, transport delay, fuel-cost scenarios; re-run forecasts/recommendations against isolated scenario data; save/compare scenarios. The simulation config mechanism (TDD §5) is its designed extension point. **Begins only after the MVP is stable.**
- **Future enhancements (beyond Phase 2):** advanced/seasonal forecasting (Holt-Winters); date-partitioning of fact_inventory_snapshot if volume warrants; additional decision-support rules (warehouse transfer, pricing/campaign optimization); cloud deployment for a live URL.

---

## 6. Risk Management

**Highest-risk tasks (watch closely):**
1. **Phase 5 ETL — Stage B (SCD2 + idempotent load + batch window).** Hardest work, most likely to slip. Highest single-phase risk.
2. **Phase 1 & Phase 4 schemas.** Low probability if reviewed, but highest *blast radius* if wrong — everything downstream depends on them.
3. **Phase 3 simulation realism + generation speed.** If data looks fake or takes too long to generate, it undermines the premise.

**Tasks to complete early (high leverage, unblock everything):**
- Both schemas (Phases 1 and 4) and their review gates — do them carefully and early; they're the critical path's foundation.
- The data-quality test suite (Phase 5 Stage A) — proves the DQ framework before Stage B builds on it.

**Tasks that can safely be postponed:**
- Power BI (parallelizable any time after Phase 5 — never on the critical path).
- Frontend visual polish / Framer Motion niceties (functional dashboards first; polish in Phase 9 slack).
- Everything in Phase 2 / future enhancements — by definition post-MVP.
- Cloud deployment — the Docker design makes it a late, small, optional step.

**Critical path:** Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → (7 → 8) → 9 → 10. Phases 1 and 4 are the foundation; Phase 5 is the high-water mark; Phases 7 and 8 are sequential (frontend displays decision-support output). Power BI is the one notable off-critical-path track.

**Buffer time:** Week 12 is explicit buffer + release. Additionally, the strict MVP cut line is itself risk insurance: if the schedule compresses, Phase 2 and future work were never in the core timeline, so slippage costs stretch goals, not the MVP.

---

*End of Document 3 (Development Roadmap / Execution Blueprint) v1.0. Two ordering conflicts with the frozen TDD were identified and corrected (§0); no scope or technology was added. Ready to proceed to Document 4 (Claude Code Master Prompt) on your confirmation.*
