# ATLAS — Claude Code Master Prompt
## The Implementation Contract (Engineering Constitution)
**Version 2.1** — adds §18 (Session Continuity & Recovery); supersedes v2.0
*Binds to: ATLAS-SRS.md v1.3 (FROZEN) · ATLAS-TDD.md v1.1 (FROZEN) · ATLAS-Roadmap.md v1.1 (FROZEN)*

> Paste this document into Claude Code before development begins. It governs implementation for the entire lifetime of this repository. Every rule here is enforceable and actionable. Where this contract and the three frozen documents disagree, that is a conflict — invoke §17. Where this contract and your own defaults disagree, this contract wins.

---

## 1. Project Mission

**Purpose.** ATLAS is a production-grade, simulated **Enterprise Supply Chain Intelligence Platform** for a fictional multinational logistics/distribution company. It simulates realistic operations (procurement, inventory, warehousing, transportation, orders, returns), moves that data through an incremental ETL pipeline into a dimensional warehouse, and exposes executive/operational dashboards plus explainable, rule-based decision support. It is a modular monolith. SQL and the database/analytics layer are the core; every other component exists to expose that layer.

**Engineering goals.** Advanced MySQL, normalized OLTP design, Kimball dimensional warehousing, incremental ETL, a tested data-quality framework, rule-based analytics, and clean modular-monolith architecture — all at professional standard.

**Interview goals.** Every decision must be defensible aloud with a correct, trade-off-aware answer grounded in an ADR or a frozen-document section. Build so this stays true.

**Quality standards.** Correctness over cleverness. Clarity over brevity. Defensibility over feature count. No code is "done" until it passes the §16 Quality Gate. Working software at every phase boundary; the main line is always runnable.

---

## 2. Frozen Documentation Rules

**Authoritative documents and precedence** (highest first, by domain):
1. **SRS v1.3** — *what* the system does: requirements, business rules, scope, MVP boundary, data quality, security, NFRs.
2. **TDD v1.1** — *how* it is architected: components, schemas, ADRs, performance strategy, communication rules.
3. **Roadmap v1.1** — *build order*: phases, dependencies, per-phase Definition of Done, MVP cut line, folder structure.
4. **This Master Prompt v2.0** — *how you work*: engineering conventions and enforcement. It never overrides the design in 1–3; it operationalizes it.

When two authoritative documents both speak to a point, the higher-precedence document controls its own domain (requirements → SRS; architecture → TDD; sequencing → Roadmap).

**Implementation boundaries.** The frozen documents are the source of truth. You implement them; you do not reinterpret, extend, or "improve" them. Anything not specified is resolved by asking (§17), not by inventing.

**Conflict resolution.** If following the frozen documents is impossible, self-contradictory, or clearly wrong, **STOP and invoke §17.** Do not silently resolve. Silent drift is the primary failure mode this contract exists to prevent.

**Phase 2 fence.** Scenario / What-If Analysis (SRS §6.9) is post-MVP. Do not build, scaffold, or design toward it during the MVP. The simulation config mechanism (TDD §5) is its designated future extension point — leave that hook clean and build nothing on it.

---

## 3. Architecture Rules

**Summary.** One deployable FastAPI backend of bounded internal modules; one MySQL 8 instance hosting two logically separate schemas — `atlas_oltp` (normalized, 3NF) and `atlas_olap` (Kimball star schema); a separate scheduled ETL process; a separate Next.js frontend; Power BI connected read-only to the warehouse. No inter-service network calls. No message broker. Module boundaries are enforced in code, not over the network (**ADR-001**).

**Modules:** OLTP Domain Services · Simulation Engine · OLAP Warehouse · ETL Pipeline · Decision Support · Backend API · Frontend · Power BI.

**Communication matrix (enforce exactly):**

| From | May talk to | May NOT |
|---|---|---|
| Simulation Engine | Domain Services | Write any DB table directly (**ADR-007**); read OLAP |
| Domain Services | `atlas_oltp` (read/write) | Read or write `atlas_olap` |
| ETL Pipeline | `atlas_oltp` (read), `atlas_olap` (write) | Write OLTP; bypass DQ checks |
| Decision Support | `atlas_olap` (read) | Write anything; read OLTP |
| Backend API — dashboard reads | `atlas_olap` (via reporting role) | Write OLAP |
| Backend API — admin writes | Domain Services | Write OLTP directly, bypassing Domain Services |
| Frontend | Backend API only | Talk to any database directly |
| Power BI | `atlas_olap` (read-only, `atlas_reporting`) | Any write |

**Dependency rules.** Dependencies flow toward the core, never outward. Domain Services depend on OLTP models; the API depends on Domain Services (writes) and the warehouse (reads); the frontend depends only on the API. No module reaches around its boundary. No circular dependencies.

**The cardinal rule.** No code writes to the database except through **Domain Services** (OLTP) or the **ETL load stage** (OLAP). Any other write path is a contract violation.

**Prohibited interactions.** Simulation writing directly to tables; Decision Support or the API writing to OLTP; the frontend querying the database; ETL writing to OLTP; any component reading a schema the matrix forbids.

---

## 4. Technology Stack Rules

**Approved stack — use only these.**
- Database: **MySQL 8** (InnoDB).
- Backend: **Python, FastAPI, SQLAlchemy, Alembic**.
- Frontend: **Next.js, React, TypeScript, TailwindCSS, shadcn/ui, Apache ECharts, TanStack Table, Framer Motion**.
- Analytics/BI: **Power BI**.
- ETL/Simulation: **Python, Pandas, NumPy, Faker**.
- Containerization/CI: **Docker, Docker Compose, GitHub Actions**.
- Testing: **Pytest**.
- Docs: **Markdown, Mermaid, draw.io, dbdiagram.io**.
- VCS: **Git**.

**Prohibited additions** (do not introduce, do not scaffold toward): Kafka, Spark, Airflow, Hadoop, Redis, RabbitMQ, Elasticsearch, MongoDB, Snowflake, BigQuery, ClickHouse; any AWS/Azure/GCP managed service; Terraform; Kubernetes; microservices; any message queue, streaming platform, or NoSQL store; any generative-AI dependency in decision support.

**Library selection philosophy.** Prefer the standard library and the already-approved stack. A new third-party library is added only when (a) it is necessary to satisfy a frozen requirement, (b) no approved tool covers it, and (c) it is approved via §17 first. "Convenient," "popular," or "I usually use it" are not justifications. No new runtime dependency enters the frontend or backend without §17 approval — this explicitly includes data-fetching/state libraries: frontend server data is fetched through the typed API client using React's built-in primitives; no global-state or query library is added unless approved.

---

## 5. Database Standards

**Migrations.** Every OLTP schema change is an Alembic migration. Migrations apply *and* roll back cleanly; both are tested in CI. Never alter a table outside a migration. Never edit a previously applied migration — add a new one. The OLAP DDL lives in `etl/warehouse_ddl/` and is version-controlled identically.

**Schema evolution.** Additive where possible. A destructive change (drop/rename/retype) requires a migration that preserves or explicitly migrates existing data, and a data-dictionary update in the same change.

**Constraints.** OLTP is 3NF unless a denormalization is documented and justified (**NFR-1**). DB-level foreign keys enforced by InnoDB (**ADR-002**). Unique constraints on all business keys — order_number, po_number, shipment_number (**DQ-2**). Money as `DECIMAL(12,2)`; never FLOAT/DOUBLE for currency or quantity (**NFR-4**). Status fields as constrained lookup tables, never free text.

**Indexing.** Index every foreign-key column and document it explicitly. Add composite indexes for known dashboard filter patterns (TDD §4.3), e.g. `(warehouse_id, date_id)` on `fact_inventory_snapshot`, `(supplier_id, delivery_date)` on `fact_supplier_delivery`. Add an index to solve a demonstrated query cost, not speculatively; justify non-obvious indexes in a comment or ADR, with `EXPLAIN` evidence during the Phase 9 tuning pass.

**SQL style.** Uppercase keywords; one major clause per line in multi-line queries; explicit column lists — no `SELECT *` in application or analytical queries. Use MySQL 8 features (window functions, recursive CTEs, aggregate functions) where they express intent clearly and correctly; never contrive them where a simpler query reads better.

**SCD2 (dim_supplier, dim_warehouse only — ADR-006).** Surrogate key PK; natural key retained; version columns effective-from / effective-to / current-flag. A tracked-attribute change closes the current row and inserts a new current row. Facts join to the surrogate key valid at the event date. SCD2 correctness is explicitly tested (constructed mid-history change → correct versioned rows). Do NOT apply SCD2 to any other dimension; the rest are Type 1 (overwrite) for the MVP.

**Warehouse conventions.** Every fact table has one documented grain (TDD §4.2.1): `fact_orders` = order line, `fact_shipments` = shipment, `fact_inventory_snapshot` = SKU×warehouse×day, `fact_procurement` = PO line, `fact_supplier_delivery` = delivery event, `fact_returns` = return line. Never mix grains in one fact. Conformed dimensions: dim_date, dim_product, dim_supplier, dim_warehouse, dim_carrier, dim_customer, dim_region. Pre-aggregated summary tables are **physical tables populated during ETL load** (not views), kept in sync with their source facts inside the same load transaction.

**ETL conventions (database side).** Loads are idempotent and transactional (**NFR-3**): re-running yields identical warehouse state, never duplicates or partial writes. Full-detail ETL rules are in §8.

---

## 6. Backend Standards (FastAPI · SQLAlchemy · Domain Services)

**Structure.** Follow the Roadmap §3 layout: `backend/app/domains/<module>/` for domain logic, `backend/app/api/` for v1 routers, `backend/app/models/` for SQLAlchemy OLTP models, `backend/app/core/` for config, DB sessions, security, settings, `backend/app/decision_support/` for the Phase 7 analytics layer.

**SQLAlchemy.** All database access goes through SQLAlchemy ORM or bound/parameterized statements — never string-concatenated SQL (**SEC-1**). Where a complex analytical query must be hand-written, use bound parameters only. DB sessions are provided by dependency injection; never open ad-hoc global connections.

**Domain Services.** The only sanctioned OLTP write path (**ADR-007**, §3). Each service enforces its business rules (BR-1–BR-5, and the FR-2.2 zone rules) and is callable and testable without the API or the simulation present. Business logic lives here, not in routers and not in the frontend.

**Validation.** Every inbound API payload is validated by a Pydantic model at the boundary before it reaches business logic (**SEC-2**). Reject malformed input with a typed error; never pass unvalidated input into a query or a service.

**Exception handling.** No bare `except`. Catch what you can handle; let the rest surface. Define typed domain exceptions and map them to HTTP responses centrally. ETL/service failures are logged with context (§8 audit), never silently swallowed.

**Logging.** Structured, leveled logging — never `print`. Log API requests and errors; never log secrets or full credential strings. ETL logging goes to `etl_run_log` (§8).

**API design.** RESTful, resource-oriented, versioned under `/api/v1` (e.g. `/api/v1/dashboards/executive`, `/api/v1/suppliers/{id}/risk`, `/api/v1/inventory/warehouse/{id}`). Dashboard reads hit `atlas_olap` (via the reporting role), preferring summary tables where defined; admin writes go through Domain Services. Standardize pagination and filtering across list endpoints (the frontend's TanStack Table depends on it). Expensive aggregate responses may be cached keyed to the ETL run version, invalidated on ETL completion (this is a batch-analytics system; dashboards refresh per ETL cycle, not per request). Meet NFR-10 latency (500 ms cached/aggregated; 2 s on-demand aggregation).

**Security roles.** Three MySQL roles, least privilege (**SEC-3**): `atlas_app` (RW OLTP only), `atlas_etl` (R OLTP, RW OLAP), `atlas_reporting` (R OLAP only; used by API dashboard reads and Power BI). Role-based access middleware governs which actor may reach which endpoint/dashboard (**SEC-5**). Secrets via environment variables / `.env`, never committed (**SEC-4**).

---

## 7. Frontend Standards (Next.js · React · TypeScript · Tailwind)

**Structure.** Next.js App Router. Role-based route groups for Executive / Operations / Planner / Admin (TDD §8). Components in `frontend/components/`, API client and shared types in `frontend/lib/`, routes in `frontend/app/`.

**TypeScript.** Strict mode. No `any` without a justifying comment. Types for API responses are derived from / aligned to the backend schema — do not hand-maintain a divergent duplicate type set.

**State management.** Local UI state via React hooks (`useState`/`useReducer`). Server data is fetched through the typed API client; cache/refetch with React built-ins. No global-state library and no new data-fetching dependency without §17 approval (see §4). No business logic in the frontend — it displays data and calls the API; all rules live in the backend.

**API client conventions.** A single typed client in `frontend/lib/` wraps all backend calls, centralizes base URL/config, applies consistent error handling, and exposes typed functions per resource. Components call the client, never `fetch` scattered inline.

**UI system.** Tailwind + shadcn/ui as the component/design system. ECharts for charts, TanStack Table for tabular/drill-down views. Framer Motion used sparingly and purposefully — meaningful transitions only, never decoration (TDD §8: commercial product, not flashy). Dashboards must meet NFR-9 latency (2 s standard, 5 s drill-down) at target volume, which they achieve by consuming summary-table-backed endpoints.

**Accessibility & consistency.** Consistent component primitives across all dashboards; no bespoke one-off widgets where a shared primitive exists. Keep the visual language uniform (SRS "resembles a commercial product").

---

## 8. ETL Standards

**Shape.** Batch, scheduled, incremental — never streaming (frozen constraint). Stages, each independently testable: Extract → Validate/DQ → Transform → Load → Audit & Score. Build **Stage A** (Extract + Validate/DQ + Audit) fully, including its data-quality test suite, **before Stage B** (Transform + SCD2 + Load + Score) — the DQ framework must be proven before the load logic builds on it.

**Extract.** Incremental, watermark-based per table — pull only rows changed since the last watermark (**ADR-008**). Never full-reload as the standard path. Watermark columns are indexed.

**Validation / Data Quality.** Apply DQ-1–DQ-6 on every run: completeness (DQ-1), uniqueness (DQ-2), referential integrity (DQ-3), duplicate detection (DQ-4), invalid values (DQ-5). Records failing any check are routed to `dq_quarantine` with the specific rule recorded — never silently dropped, never loaded with defaults (**BR-6**). The run continues for valid records.

**Transformation.** Map OLTP rows to fact/dimension structures at each fact's documented grain. Apply SCD2 logic for dim_supplier and dim_warehouse (§5). Compute derived measures. The supplier risk score is a warehouse-derived measure recalculated per ETL cycle from deliveries loaded since the previous run (**BR-4**), not per delivery event.

**Loading.** Transactional and idempotent per batch (**NFR-3**): a failed load leaves the warehouse unchanged; a re-run reproduces identical state. Populate pre-aggregated summary tables within the same load transaction.

**Auditing.** Every run writes `etl_run_log`: timestamps, per-stage row counts, accepted/quarantined/rejected counts, rule-level failure breakdown, duration (**DQ-6**).

**Data-quality scoring.** Compute a per-run and per-table data-quality score (**DQ-7**), tracked over time and surfaced on the Data Quality dashboard (FR-7.5).

**Performance.** A full run over the 5-year dataset meets the NFR-8 batch window (target < 30 min on standard local hardware); incremental runs complete within a few minutes.

---

## 9. Simulation Standards

**Operational realism.** Rule-driven, not random. Each simulated day advances business-rule generators: seasonality-aware demand/orders, supplier deliveries (lead-time distributions with occasional lateness), warehouse operations, shipment/transport with a cost model, returns with reason codes at realistic rates. Avoid purely random data; generate cause-and-effect.

**Deterministic business rules.** The simulation writes exclusively through Domain Services (**ADR-007**) — never directly to tables — so all generated data obeys the same rules and constraints as any other write path. Generation is seeded/reproducible: the same config + seed yields the same dataset.

**Purchase Order Generator.** The simulation's internal reorder heuristic triggers PO creation during data generation, through the procurement Domain Service, to populate procurement history (**FR-1.2**). This operational heuristic is **distinct from** the Phase 7 Decision Support reorder recommendation (analytical, warehouse-derived) and must not be conflated with it or share its code path.

**Separation from analytics.** The simulation never reads the OLAP warehouse or Decision Support output. It is a pure producer of operational (OLTP) history via Domain Services.

**Generation constraints.** World state is config-driven at the target volume (TDD §10): 8 warehouses, ~5,000 SKUs, ~100 suppliers, 5 years, ~1–2M order lines, ~500k shipments. Faker is used only for master/reference data (names, addresses), never for business-event logic. Validate realism on a short run before generating the full multi-year dataset.

---

## 10. Decision Support Standards

**Reads only the warehouse.** Decision Support reads `atlas_olap` and writes nothing (§3). It never reads OLTP and never calls Domain Services.

**Rule-based and statistical only.** No ML framework, no generative AI (**ADR-004**, frozen constraint). Recommendations come from documented business rules and statistics.

**Explainability (mandatory).** Every recommendation carries the inputs, the rule/formula, and the resulting "why" — traceable to the underlying data (**FR-8.4**). No black-box outputs. This is enforced by a traceability test asserting each recommendation's stated factors equal its actual inputs.

**Reorder recommendations.** Reorder point = (average daily demand × lead time in days) + safety stock (**BR-3**), surfaced with contributing factors (**FR-8.1**).

**Supplier risk alerts.** Reference the specific metric and threshold that triggered them (**FR-8.2**); the underlying score follows BR-4's per-ETL-cycle cadence.

**Route/cost optimization.** Suggestions derived from historical route-efficiency data in the warehouse (**FR-8.3**).

**Forecasting.** Statistical only — moving average / exponential smoothing (**ADR-004**). Report forecast-vs-actual and accuracy (MAPE) on the Planning view (FR-7.4).

---

## 11. Testing Standards

- **Every feature ships with tests.** A feature without tests is not done.
- **Test-first where practical**, especially business rules and data-quality checks: encode the rule as a failing test, then implement to green.
- **Unit** — Domain Service business rules (BR-1–BR-7), ETL transform functions, DQ check functions, reorder/risk/forecast math.
- **Integration** — full ETL pipeline (extract → validate → transform → load → audit) against a test database, including quarantine behavior, SCD2 correctness, and idempotency (run-twice → identical state).
- **API** — FastAPI test client per endpoint, including role-based access checks and input-validation rejection; latency assertions against NFR-10.
- **Data quality** — a dedicated suite proving each DQ-1–DQ-7 rule catches its specific bad-data case (frozen risk: the DQ framework must not give false confidence).
- **Frontend** — component tests for key dashboards; an end-to-end smoke test (load each dashboard, filter, drill down).
- **Performance** — NFR-8/9/10 validated with evidence in Phase 9 (`EXPLAIN` plans, timings), not assumed.
- **CI** — GitHub Actions runs lint + format + the full suite (against a containerized MySQL) on every push. **Never leave a failing test. Never skip, disable, or delete a test to make CI green. The main line stays green.**

---

## 12. Documentation Standards

- **Docs change in the same commit as the code they describe** — never deferred.
- **Kept current at all times:** README; the four diagrams (System Architecture, ERD, Star Schema, ETL Flow — DOC-1–DOC-4); the ADR set (DOC-6); the Data Dictionary across OLTP + OLAP (DOC-5).
- **Schema changes** update the ERD/star-schema diagram and data dictionary in the same change.
- **ADRs are a living record but change only through §17** — flag, get approval, then update the ADR to record the new decision, its rationale, and what changed. New significant decisions get a new ADR. ADRs are never edited silently.
- **Comments** explain *why*, not *what*. Every business rule in code carries its SRS BR- identifier in a comment. No rule is implicit.
- **Module documentation** — each module carries a short README or docstring stating its responsibility and boundaries.

---

## 13. Git Workflow

- **Branching.** Trunk-based: short-lived feature branches off `main`, merged back quickly. `main` is always green and runnable.
- **Conventional Commits.** `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `perf:`, `refactor:`, with scopes (`feat(etl):`, `feat(domain):`, `feat(api):`, `feat(fe):`, `feat(dw):`, `feat(sim):`, `feat(ds):`). Follow the representative commit grain listed per phase in the Roadmap.
- **Commit granularity.** Atomic — one logical change per commit, individually reviewable and ideally revertible. No giant catch-all commits; no mixing unrelated changes; do not dump a whole phase into one commit.
- **Pull request expectations.** Each feature/phase-slice lands via a PR whose description states what changed, why, which requirements/phase it advances, and how it was tested. CI must be green before merge. Even solo, the PR is the review artifact.
- **Review discipline.** Before merging, self-review against the §16 Quality Gate. Do not merge red CI, unresolved TODOs, or unmet Definition of Done.

---

## 14. Implementation Workflow

- **Phase by phase, in Roadmap order (0 → 10).** Do not start a phase whose dependencies are unmet. Do not implement future-phase functionality early — that is drift.
- **Finish a phase completely before the next.** "Complete" = its Definition of Done met (deliverables built, tests passing, lint/format clean, docs updated, CI green, `docker compose up` works).
- **Review gates are hard stops.** Pause after **Phase 1** (OLTP schema) and after **Phase 4** (warehouse schema/grain) and present the schema for review before building dependent code. Within **Phase 5**, complete Stage A (with its DQ tests) before Stage B.
- **Keep the project runnable at every commit.** Never commit a knowingly broken main line.
- **Stopping conditions.** STOP and surface the issue when: (a) a frozen-document conflict is found (§17); (b) a requirement is ambiguous or underspecified (ask, don't guess); (c) a review gate is reached; (d) a change would require a new dependency, pattern, or scope (§4, §15). Ambiguity is resolved by asking, never by assuming.
- **Progress reporting.** When reporting status, state the current phase, which Definition-of-Done items are complete, which remain, and any blockers — not a narrative of activity.

---

## 15. Anti-Patterns (explicitly prohibited)

- **Architecture drift** — any new tech/pattern/service/scope, or any deviation from the §3 communication matrix, without §17 approval.
- **Premature optimization** — optimizing before a demonstrated, measured need; performance work belongs to Phase 9 with evidence.
- **Unnecessary abstraction** — layers, interfaces, or generality for hypothetical futures. Build for the current phase.
- **Duplicated logic** — a business rule lives in exactly one place; no copy-paste of rule logic across modules.
- **Dead code** — nothing unused, nothing commented-out "just in case." Delete it; Git remembers.
- **Hidden business rules** — rules are explicit, named, tested, and traceable to their BR- identifier; never buried implicitly in a query or a component.
- **Undocumented changes** — code that ships without its README/diagram/ADR/data-dictionary update.
- **Bypassing Domain Services** — any DB write outside Domain Services (OLTP) or the ETL load (OLAP). The cardinal violation.
- **Silent requirement changes** — reinterpreting or extending a requirement without §17.
- **Introducing new dependencies** — any new library without §4 justification and §17 approval.
- **Speculative features** — building anything not required by the current phase, including Phase 2 work during the MVP.
- **Magic numbers** — named, meaningful constants; business thresholds/tolerances/rates traceable to the SRS.
- **Placeholder implementations / TODOs** — do not leave `TODO`/`FIXME` or stub functions in place of real work. If something genuinely cannot be built yet, flag it (§17) rather than stub it.

---

## 16. Quality Gate Checklist

Before declaring ANY task, feature, or phase complete, verify **all**:

- ☐ **Architecture preserved** — no new tech/pattern/service/scope; §3 matrix respected; no ADR violated; no DB write outside Domain Services / ETL load.
- ☐ **Requirements satisfied** — the specific SRS FR/BR/DQ/SEC/NFR items this work covers are met.
- ☐ **Tests passing** — full suite green, including new tests for this work; none skipped or disabled.
- ☐ **Lint passing** — ruff (Python), eslint (TypeScript).
- ☐ **Formatting passing** — black (Python), prettier (TypeScript).
- ☐ **Documentation updated** — README/diagrams/ADRs/data dictionary reflect this change.
- ☐ **CI passing** — and `docker compose up` still works.
- ☐ **No TODOs** — no placeholders or stubbed implementations left behind.
- ☐ **Roadmap milestone complete** — the phase's Definition of Done is met.

If any box cannot be checked, the task is **not complete**. Do not report it as complete.

---

## 17. Conflict Resolution

If implementation conflicts with the frozen documents — or requires anything this contract prohibits — **STOP. Never invent a solution.**

Surface the conflict with exactly these fields:
1. **Affected document** (SRS / TDD / Roadmap / this contract).
2. **Section** (specific section, requirement ID, or ADR).
3. **Explanation** — what the conflict or ambiguity is, precisely.
4. **Impact** — what it blocks and what breaks if resolved wrongly.
5. **Possible solutions** — the viable options.
6. **Trade-offs** — the cost of each option.

Then **wait for approval.** Do not proceed on the affected work until a decision is given. When a decision changes a frozen document, that document is updated and re-versioned through this same path, and the relevant ADR is recorded (§12). This protocol is the single most important behavior in this contract for preserving architectural integrity.

---

## 18. Session Continuity & Recovery Protocol

Long-running implementation may be interrupted by context limits, usage limits, network loss, IDE restarts, or manual stops. No meaningful progress may be lost, and implementation must be able to resume immediately after any interruption. **The repository — not conversation memory — is always the source of truth.** This protocol is mandatory.

### 18.1 Continuous Persistence
Never keep important work only in the conversation. Whenever a meaningful unit is complete, commit it: code, tests, migrations, configuration, documentation. Small, frequent commits are preferred over large uncommitted work. The main line stays runnable (§14).

### 18.2 Session Handoff
At every natural stopping point — a completed logical unit, or whenever the session may end soon — produce a Session Handoff in **exactly** this format:

```
SESSION HANDOFF

Current Phase:
Current Roadmap Milestone:

Completed:
- ...

Remaining:
- ...

Files Created:
- ...

Files Modified:
- ...

Database Changes:
- ...

Migrations Added:
- ...

Tests Added:
- ...

Tests Passing:
Yes / No

Documentation Updated:
- ...

Definition of Done Progress:
Completed:
Remaining:

Known Issues:
- ...

Current Branch:
- ...

Last Completed Commit:
- ...

Recommended Next Task:
- ...

Exact Resume Command:

Continue from the Session Handoff.
Read the repository state before making changes.
Verify completed work.
Resume from:
<current task>
```

### 18.3 Interruption & Usage-Limit Safety
When any interruption is imminent (usage limit, context limit, connection loss, IDE stop), **preserving work overrides continuing implementation** — stop advancing features and secure state instead. Do not attempt to work around the limit. Do not compress the project into memory. Do not rewrite or regenerate completed files. In order:
1. Finish the current file if reasonably possible.
2. Finish any migration currently being written.
3. Finish any test currently being written.
4. Save and commit all modified files.
5. Produce a complete Session Handoff (§18.2).
6. Stop immediately, leaving the repository in a runnable state.

Never continue partway into another feature during an interruption. (§17 still governs any frozen-document conflict; this section governs interruptions.)

### 18.4 Resuming on "Continue" / "resume"
When the user writes only `Continue`, `continue`, or `resume`: do NOT restart the project, and do NOT repeat previous explanations or re-summarize the project. Instead:
1. Inspect the current repository state.
2. Verify the latest commit.
3. Read the latest Session Handoff.
4. Verify completed files and run the tests.
5. Determine the current Roadmap phase.
6. Resume from the first unfinished task.

Never regenerate completed work; never overwrite it except to fix a bug; never restart an already-completed phase; never duplicate work.

### 18.5 If Conversation Memory Is Lost
Treat the repository as authoritative and assume no chat history exists. Reconstruct context from source code, documentation, ADRs, the Roadmap, the README, and the latest Session Handoff. Ask the user only if the repository genuinely cannot determine the correct next step.

### 18.6 Resume Priority (ordered)
1. Verify repository state. 2. Verify latest commit. 3. Verify latest Session Handoff. 4. Verify tests. 5. Resume the current phase. 6. Continue implementation.

The repository always has higher priority than conversation memory. Never restart a completed phase; never duplicate work; never discard completed work because the conversation restarted.

---

*End of Claude Code Master Prompt v2.1 — the definitive implementation contract for ATLAS. Supersedes v2.0. Binds to SRS v1.3, TDD v1.1, Roadmap v1.1. Deviation occurs only through §17.*
