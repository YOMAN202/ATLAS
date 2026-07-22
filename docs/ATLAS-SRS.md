# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Software Requirements Specification (SRS)
**Version 1.3 — FROZEN**

> **Roadmap note:** Scenario Analysis / What-If Analysis (Section 6.9, FR-9.x) remains part of the product vision and is retained in this SRS in full, but is designated a **Phase 2 / post-MVP** capability. The MVP scope is: OLTP schema, ETL pipeline, OLAP warehouse, Data Quality framework (Section 7), executive/operational dashboards, and rule-based decision support (Section 6.8). Scenario Analysis begins only once the core platform is stable and complete. This sequencing is authoritative in the Technical Design Document and Development Roadmap.

---

## 1. Executive Summary

ATLAS is a simulated enterprise supply chain intelligence platform demonstrating production-grade relational database design, dimensional data warehousing, ETL engineering, and business intelligence at the depth expected of a professional data/analytics engineering team. The platform models a fictional multinational logistics and distribution company — spanning procurement, warehousing, transportation, order fulfillment, and returns — and continuously simulates realistic operational events that flow through an OLTP system into an OLAP warehouse, surfaced through executive dashboards and explainable, rule-based decision-support recommendations.

The system is architected as a modular monolith. Every technology in the stack exists to expose or demonstrate the capability of the database and analytics layer — none is included for its own sake. This document specifies *what* the system must do and the constraints it must satisfy; it does not specify implementation.

## 2. Vision Statement

ATLAS should read, to an engineer evaluating it, like an internal operations and analytics platform a real logistics company (e.g. a regional 3PL, a mid-size distribution network) would actually run — not a classroom exercise wearing an enterprise costume. Every entity, business rule, and dashboard should be defensible: if asked "why does this table exist" or "why is this the grain of this fact table," the answer should be a real operational reason, not "the spec asked for it."

## 3. Business Objectives

| # | Objective |
|---|---|
| B1 | Demonstrate advanced relational database design at a complexity comparable to production ERP/logistics systems |
| B2 | Demonstrate dimensional data warehouse design (star schema, conformed dimensions, multiple fact grains, SCD handling) |
| B3 | Demonstrate a realistic, production-quality ETL pipeline (extract, validate, clean, transform, aggregate, load, monitor) |
| B4 | Demonstrate business intelligence capability — dashboards that answer real operational and executive questions |
| B5 | Demonstrate explainable, rule-based decision-support analytics (no generative AI) |
| B6 | Produce a project defensible in depth during Data Analyst / Business Analyst / Analytics Engineer / Data Engineer technical interviews |
| B7 | Keep the system architecturally coherent as a modular monolith — extensible without becoming a distributed-systems showcase |

## 4. Stakeholders

| Stakeholder | Interest |
|---|---|
| Project Owner (Akshat) | Flagship portfolio piece; must be fully explainable in interviews |
| Prospective Employers / Interviewers | Evaluate SQL depth, data modeling judgment, analytics reasoning, engineering practice |
| (Simulated) Executive Leadership | Consumers of executive dashboards — care about revenue, cost, service level, risk |
| (Simulated) Operations Managers | Consumers of operational dashboards — care about warehouse throughput, fleet utilization, supplier performance |
| (Simulated) Supply Planners | Consumers of forecasting, scenario analysis, and reorder recommendations |

## 5. Actors

| Actor | Type | Description |
|---|---|---|
| Simulation Engine | System | Generates realistic operational events per business rules (orders, shipments, supplier deliveries, returns, disruptions) |
| ETL Pipeline | System | Extracts from OLTP, validates/cleans/transforms, loads into OLAP warehouse on a schedule; scores data quality |
| Executive User | Human (role-played) | Views executive KPI dashboards; no write access |
| Operations Analyst | Human (role-played) | Views operational dashboards; can drill into shipment/warehouse/supplier detail |
| Supply Planner | Human (role-played) | Views forecasts, runs scenario analyses, and reviews reorder/risk recommendations |
| System Administrator | Human (role-played) | Manages reference data (products, warehouses, carriers, suppliers) |

## 6. Functional Requirements

### 6.1 Procurement & Supplier Management
- FR-1.1: System shall maintain a supplier master with contract terms, lead times, and reliability history.
- FR-1.2: System shall generate purchase orders and track their lifecycle (draft → submitted → confirmed → fulfilled → closed). Purchase orders are created during data generation by the Simulation Engine's internal reorder heuristic — operational logic that triggers PO creation while generating history (Phase 3). This is intentionally distinct from the Decision Support reorder recommendation (FR-8.1, Phase 7), which is an analytical recommendation computed from the OLAP warehouse for planners. The two are separate systems serving different purposes and must not be conflated.
- FR-1.3: System shall record supplier delivery performance (on-time %, quantity accuracy, quality rejection rate) per delivery.
- FR-1.4: System shall compute a supplier risk/reliability score from historical performance.

### 6.2 Inventory & Warehousing
- FR-2.1: System shall track inventory levels per SKU per warehouse/distribution center, updated by every relevant transaction (receipt, pick, transfer, adjustment, return).
- FR-2.2: System shall model warehouse capacity constraints and zone-level allocation. For the MVP, zone-level allocation means inventory positions are associated with warehouse zones, zone capacity is modeled, and inventory movements respect zone assignments (implemented in the Phase 2 Domain Services). Advanced warehouse slotting and optimization are future enhancements, out of scope for the MVP.
- FR-2.3: System shall support inter-warehouse stock transfers with in-transit tracking.
- FR-2.4: System shall flag stockouts and overstock conditions against configurable thresholds.

### 6.3 Transportation & Fleet Operations
- FR-3.1: System shall model a carrier/fleet master with vehicle types, capacity, and cost profiles.
- FR-3.2: System shall generate shipments with route, carrier, origin/destination DC, and cost.
- FR-3.3: System shall track shipment status through a realistic lifecycle (created → picked → in transit → delivered / exception).
- FR-3.4: System shall compute route efficiency metrics (cost per mile, on-time delivery rate, utilization).

### 6.4 Order Management & Returns
- FR-4.1: System shall generate customer orders that consume inventory and trigger downstream fulfillment.
- FR-4.2: System shall model order lifecycle including partial fulfillment and backorders.
- FR-4.3: System shall generate a realistic proportion of returns with reason codes, feeding back into inventory and quality metrics.

### 6.5 Demand Forecasting & Supply Planning
- FR-5.1: System shall compute demand forecasts per SKU/region using historical order data (statistical, not generative-AI based).
- FR-5.2: System shall generate reorder point recommendations from forecasted demand, lead time, and safety stock rules.
- FR-5.3: System shall support seasonal/promotional demand modifiers in the simulation.

### 6.6 ETL & Data Warehouse
- FR-6.1: System shall extract operational data from the OLTP database on a defined schedule.
- FR-6.2: System shall validate and cleanse extracted data, logging and quarantining records that fail quality checks.
- FR-6.3: System shall transform operational data into a dimensional warehouse schema (fact and dimension tables) with correct grain per fact table.
- FR-6.4: System shall implement slowly changing dimensions where a real business justification exists (e.g. supplier terms, warehouse capacity changes).
- FR-6.5: System shall log every ETL run's status, row counts, and errors for monitoring.

### 6.7 Business Intelligence & Dashboards
- FR-7.1: System shall provide an Executive Overview dashboard (revenue, cost, margin, service level, order volume trends).
- FR-7.2: System shall provide operational dashboards for Inventory, Warehouse, Transportation, and Supplier performance.
- FR-7.3: System shall provide a Risk & Exceptions view surfacing supplier risk, stockout risk, and shipment exceptions.
- FR-7.4: System shall provide a Forecasting & Planning dashboard showing demand forecasts vs. actuals and reorder recommendations.
- FR-7.5: System shall provide a Data Quality dashboard surfacing quality scores and ETL audit results (see Section 7).

### 6.8 Decision Support
- FR-8.1: System shall generate explainable reorder recommendations (SKU, quantity, reason, contributing factors).
- FR-8.2: System shall generate supplier risk alerts with the specific metrics that triggered the alert.
- FR-8.3: System shall generate route/cost optimization suggestions based on historical route efficiency data.
- FR-8.4: Every recommendation shall be traceable to the underlying data and rule that produced it — no black-box outputs.

### 6.9 Scenario Analysis / What-If Analysis
- FR-9.1: System shall allow a Supply Planner to define a scenario by adjusting one or more operational parameters, including but not limited to: supplier disruption (delayed/reduced supply from a given supplier), demand spike (percentage increase for a SKU/region/time window), warehouse capacity reduction, transportation delay (added lead time on a lane/carrier), and fuel/transportation cost increase.
- FR-9.2: System shall re-run the relevant forecasting and recommendation logic against the scenario parameters without altering production data, and present the resulting forecasts, reorder recommendations, and risk alerts side-by-side with the baseline.
- FR-9.3: System shall clearly label scenario output as hypothetical and distinct from live operational data at all times in the UI.
- FR-9.4: System shall allow scenarios to be saved and compared against each other.

## 7. Data Quality Requirements

- DQ-1 (Completeness): Critical fields (foreign keys, quantities, dates, monetary amounts) shall be validated as non-null before load; incomplete records are quarantined, not silently dropped or loaded with defaults.
- DQ-2 (Uniqueness): Natural keys and business identifiers (e.g. order number, shipment number, PO number) shall be validated as unique within their defined scope; violations are logged.
- DQ-3 (Referential Integrity): Every foreign key reference from a fact record to a dimension shall resolve to a valid dimension row at load time; unresolved references are quarantined with the reason recorded.
- DQ-4 (Duplicate Detection): The ETL pipeline shall detect duplicate source records (exact and business-key duplicates) before load and log/deduplicate per a documented rule.
- DQ-5 (Invalid Values): Domain and range checks shall be applied to relevant fields (e.g. non-negative quantities, valid status enumerations, valid date ranges); violations are quarantined.
- DQ-6 (ETL Audit Logging): Every ETL run shall produce an audit record capturing run timestamp, source row counts, accepted/quarantined/rejected counts, rule-level failure breakdown, and duration.
- DQ-7 (Data Quality Scoring): The system shall compute a per-run and per-table data quality score derived from the above checks (e.g. percentage of records passing all checks), tracked over time and surfaced on the Data Quality dashboard (FR-7.5).

## 8. Non-Functional Requirements

| # | Requirement |
|---|---|
| NFR-1 | The OLTP schema shall be in at least 3NF unless a documented denormalization is justified. |
| NFR-2 | The OLAP warehouse shall follow dimensional modeling best practices (Kimball-style star schema, conformed dimensions). |
| NFR-3 | ETL jobs shall be idempotent and re-runnable without data corruption. |
| NFR-4 | All monetary and quantity fields shall use appropriate precise types (no floating-point currency). |
| NFR-5 | The system shall remain a modular monolith — no premature service decomposition. |
| NFR-6 | Architectural decisions shall be documented with rationale sufficient to defend in a technical interview. |
| NFR-7 | The codebase shall include automated tests covering core business rules, ETL correctness, and data quality checks. |
| NFR-8 (Performance — ETL) | A full nightly ETL run over a multi-year, multi-warehouse simulated dataset shall complete within a defined batch window (target: under 30 minutes on standard local development hardware); incremental runs shall complete within a few minutes. |
| NFR-9 (Performance — Dashboards) | Standard dashboard queries against the warehouse shall return within 2 seconds at the target data volume (target volume to be fixed in the TDD, e.g. multiple years of daily transactional volume across all warehouses); drill-down queries within 5 seconds. |
| NFR-10 (Performance — API) | Backend API endpoints backing dashboards shall respond within 500ms for cached/aggregated queries and within 2 seconds for on-demand aggregation queries. |
| NFR-11 (Scalability target) | The schema and ETL design shall remain performant as simulated data grows to a defined multi-year volume without requiring architectural rework (specific volume targets fixed in the TDD). |

## 9. Security Requirements

- SEC-1: All database access from application code shall use parameterized queries/prepared statements — no dynamic SQL string concatenation.
- SEC-2: All external input (API requests, ETL source data) shall be validated and sanitized before use in queries or business logic.
- SEC-3: Database access shall follow least-privilege principles — distinct database roles/users for the application layer, the ETL pipeline, and reporting/BI tools, each granted only the permissions it needs (e.g. reporting role is read-only).
- SEC-4: Secrets (database credentials, API keys) shall be managed via environment variables / a `.env` mechanism and never committed to source control.
- SEC-5: Role-based access shall govern which dashboards and actions each simulated actor (Executive, Operations Analyst, Supply Planner, Administrator) can view or perform.

## 10. Documentation Requirements

The following artifacts are required deliverables of the project, not optional extras:

- DOC-1: Entity-Relationship (ER) Diagram for the OLTP schema.
- DOC-2: Star Schema Diagram(s) for the OLAP warehouse, showing fact tables, dimensions, and grain.
- DOC-3: ETL Flow Diagram showing extract → validate → transform → load → audit stages and data quality checkpoints.
- DOC-4: System Architecture Diagram showing the modular monolith's components (OLTP DB, ETL, warehouse, API, frontend, BI layer) and their interactions.
- DOC-5: Data Dictionary covering every table and column across OLTP and OLAP schemas, including type, constraints, and business meaning.
- DOC-6: Architecture Decision Records (ADRs) for each significant design decision, capturing the decision, alternatives considered, and rationale.

## 11. User Stories

- As an **Executive**, I want to see revenue, cost, and service-level trends at a glance, so I can assess overall business health.
- As an **Operations Analyst**, I want to see which warehouses are over/under capacity, so I can plan transfers.
- As a **Supply Planner**, I want reorder recommendations with the reasoning behind them, so I can trust and act on them.
- As a **Supply Planner**, I want to see supplier risk scores and what's driving them, so I can decide whether to diversify sourcing.
- As a **Supply Planner**, I want to model a supplier disruption or demand spike and see the resulting recommendations, so I can prepare contingency plans before they're needed.
- As an **Operations Analyst**, I want to see route efficiency by carrier and lane, so I can identify cost-reduction opportunities.
- As a **System Administrator**, I want to manage product, warehouse, and supplier reference data, so the simulation and analytics stay accurate.
- As an **Operations Analyst**, I want to see the data quality score of each warehouse load, so I can trust (or question) the numbers on my dashboards.

## 12. Use Cases (Representative)

**UC-1: Generate Reorder Recommendation**
Trigger: Scheduled analytics job or planner-initiated review.
Flow: System reads current inventory, in-transit quantities, forecasted demand, supplier lead time, and safety stock policy → computes reorder point and recommended quantity → records recommendation with contributing factors → surfaces on Planning dashboard.
Postcondition: Recommendation is visible and traceable to its inputs.

**UC-2: Process Customer Order Through Fulfillment**
Trigger: Simulation engine generates an order.
Flow: Order created → inventory checked → allocated from warehouse (or backordered) → shipment generated → inventory decremented → shipment tracked to delivery → revenue and COGS recognized → downstream KPIs updated.

**UC-3: ETL Nightly Load**
Trigger: Schedule.
Flow: Extract changed OLTP records since last watermark → validate/cleanse (data quality checks per Section 7) → transform into fact/dimension changes (including SCD logic where applicable) → load into warehouse → compute data quality score → log run metrics → alert on failure or quality-score drop below threshold.

**UC-4: Run a Scenario Analysis**
Trigger: Supply Planner defines a scenario (e.g. "Supplier X delayed 14 days").
Flow: Planner selects scenario type and parameters → system re-runs forecasting/recommendation logic against a scenario-scoped copy of relevant data → resulting forecasts and recommendations displayed alongside baseline, clearly labeled hypothetical → planner may save the scenario for later comparison.
Postcondition: Production data and baseline forecasts remain unaffected.

## 13. Acceptance Criteria (Representative)

- Given a SKU falls below its computed reorder point, the system generates a recommendation within one planning cycle, showing the specific inventory, demand, and lead-time figures used.
- Given an ETL run encounters malformed records, those records are quarantined and logged, and the run completes for all valid records rather than failing entirely.
- Given an ETL run completes, a data quality score is computed and visible on the Data Quality dashboard, broken down by table/check type.
- Given a supplier's on-time delivery rate drops below a defined threshold over a rolling window, a risk alert is generated referencing the underlying metric and threshold.
- Given a warehouse's utilized capacity exceeds a defined threshold, it is flagged on the operational dashboard with the current and threshold values shown.
- Given a planner runs a "demand spike" scenario, the system returns updated forecasts and recommendations without modifying any production/baseline data, and the output is visibly marked as a scenario result.
- Given a standard dashboard query against the target data volume, the response returns within the threshold defined in NFR-9.

## 14. Business Rules (Representative)

- BR-1: A purchase order cannot be marked "fulfilled" until received quantity matches ordered quantity within an approved tolerance.
- BR-2: Inventory cannot go negative; an order that cannot be fully allocated is partially fulfilled and the remainder backordered.
- BR-3: Reorder point = (average daily demand × lead time in days) + safety stock.
- BR-4: A supplier's risk score is recalculated during each ETL cycle, using all delivery events loaded since the previous ETL run — not synchronously after every individual delivery event. (Consistent with the incremental ETL design, ADR-008, and NFR-8; the score is a warehouse-derived analytical measure produced by the Decision Support layer, per the TDD.)
- BR-5: A return decrements "sellable" inventory only after a quality/inspection step; failed inspection routes to a separate disposition.
- BR-6: A record failing any Section 7 data quality check is quarantined, not loaded, and logged with the specific rule it violated.
- BR-7: Scenario analyses never write to production OLTP or baseline warehouse tables; they operate on isolated scenario-scoped data structures.

## 15. Key Performance Indicators (KPIs)

**Executive:** Revenue, gross margin, order volume, order fulfillment rate, cost-to-serve.
**Inventory:** Inventory turnover, stockout rate, days of supply, overstock value.
**Warehouse:** Capacity utilization, pick accuracy, throughput per zone.
**Transportation:** On-time delivery rate, cost per mile/shipment, carrier utilization.
**Supplier:** On-time delivery %, quality rejection rate, lead-time variance, risk score.
**Planning:** Forecast accuracy (MAPE), reorder recommendation acceptance rate.
**Data Quality:** Per-table data quality score, quarantine rate, referential integrity failure rate.

## 16. Assumptions

- All operational data is synthetically generated by the simulation engine using realistic business rules (no third-party data licensing concerns).
- The platform is a solo, single-developer project; "enterprise-grade" refers to design and engineering rigor, not multi-team scale.
- The system does not require real-time (sub-second) processing; near-real-time/batch-oriented analytics is acceptable and realistic for this domain.
- Simulated user roles (Executive, Analyst, Planner, Administrator) are role-played through the UI rather than backed by a full identity provider.

## 17. Constraints

- Database: MySQL 8, mandatory.
- Stack is fixed per project charter (Python/FastAPI backend, Next.js/React frontend, Power BI for BI, Docker/Compose for environment, GitHub Actions for CI, Pytest for testing).
- No distributed systems, no cloud provider services, no message queues, no NoSQL stores — modular monolith only.
- No generative AI in the decision-support or scenario-analysis layer; all outputs must be rule/statistics-based and explainable.
- Development is solo and must be realistically completable within roughly 8–12 weeks at the depth specified.

## 18. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Scope creep across 15+ business entities plus scenario analysis and data quality layers | High — could stall development | Strict MVP boundary defined in the roadmap; extensions sequenced after MVP |
| Simulation rules read as unrealistic/arbitrary | Medium — undermines "enterprise-grade" credibility | Base rules on publicly documented real-world supply chain logic (reorder point formulas, standard KPI definitions) |
| Warehouse schema design mistakes discovered late | High — costly to refactor | Dedicated schema/grain review before ETL implementation begins |
| Scenario analysis engine adds significant complexity for a "nice to have" capability | Medium | Treat as a post-MVP stretch goal in the roadmap unless MVP timeline allows it |
| Solo developer time constraints vs. 12-week target | Medium | Roadmap includes an explicit MVP cut line separate from stretch goals |
| Data quality framework is under-tested and gives false confidence | Medium | Section 7 checks must have dedicated automated tests, not just implementation |

## 19. Success Metrics

- All core business processes (procurement → inventory → fulfillment → delivery → returns) are simulated end-to-end and reflected correctly in the warehouse.
- Every dashboard KPI can be traced back to specific fact/dimension tables and ETL logic on demand.
- Every architectural decision has a documented ADR that can be explained in an interview setting.
- ETL runs meet the performance targets in Section 8 and produce a visible, trustworthy data quality score.
- At least one scenario analysis (e.g. demand spike or supplier disruption) is fully functional end-to-end.
- The project runs locally via Docker Compose with a single documented setup process.

## 20. Scope

In scope: OLTP schema for procurement, inventory, warehousing, transportation, orders, and returns; simulation engine generating realistic events across these domains; ETL pipeline into a dimensional warehouse with data quality checks and audit logging; executive and operational dashboards; rule-based forecasting, decision-support recommendations, and scenario/what-if analysis; supporting backend API and frontend UI to expose the above; baseline security engineering practices; full documentation set (Section 10).

## 21. Out of Scope

- Real-time streaming architectures (Kafka, event streaming platforms).
- Multi-tenant / multi-company support.
- Full identity/authentication infrastructure beyond role-based dashboard views needed to demonstrate the concept.
- Integration with real third-party logistics, ERP, or payment systems.
- Generative-AI-based recommendations, scenario generation, or natural-language interfaces.
- Mobile applications.

---

*End of Document 1 (SRS) — Finalized v1.1, incorporating Data Quality, Scenario Analysis, expanded NFRs, Security Requirements, and Documentation Requirements. Ready to proceed to Document 2 (Technical Design Document) pending final confirmation.*
