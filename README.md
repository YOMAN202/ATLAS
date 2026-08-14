# ATLAS

## Enterprise Supply Chain Intelligence Platform — v1.0

ATLAS is a complete, end-to-end supply-chain intelligence platform: a rule-driven simulation engine that generates a realistic transactional history, a normalized OLTP schema, an incremental ETL pipeline with a tested data-quality framework, a Kimball star-schema warehouse, seven read-only BI dashboards, six deterministic decision-intelligence modules (forecasting, supplier risk, service-level prediction, inventory optimization, scenario simulation, route/cost optimization), and a verification-first analytics copilot — twelve gated stages, each built, validated against real data, and honestly reported before the next began.

**Status: v1.0 — complete, validated, feature-complete.** Full narrative: [`docs/ATLAS-v1.0-final-report.md`](docs/ATLAS-v1.0-final-report.md).

---

## Architecture

```mermaid
flowchart LR
    Sim["Simulation<br/>365-day synthetic history"] --> OLTP[("atlas_oltp")]
    OLTP --> ETL["ETL<br/>Extract → Validate → Transform → Load"]
    ETL --> OLAP[("atlas_olap<br/>star-schema warehouse")]
    OLAP --> BI["7 BI Dashboards<br/>read-only, role-gated"]
    OLAP --> DS["Decision Intelligence<br/>Modules A–F"]
    DS --> BI
    BI --> Copilot["Verified Analytics Copilot<br/>tool selection → claim generation<br/>→ deterministic verification → rendering"]
    DS --> Copilot
```

Full system architecture, data flow, warehouse star schema, ETL pipeline, and the copilot's verification-boundary diagram: [`docs/architecture-overview.md`](docs/architecture-overview.md).

## Feature summary

| Area | What it does | Headline validated result |
|---|---|---|
| **Simulation** | 365-day synthetic supply chain — 8 warehouses, 5,000 products, 100 suppliers, 2,000 customers, 25 carriers | 292,925 orders, 10/10 SQL invariants passed, determinism proven bit-exact |
| **OLTP + Warehouse** | Normalized transactional schema → Kimball star-schema warehouse | 14 warehouse objects, SCD2 on supplier/warehouse dimensions |
| **ETL** | Watermark-based incremental extract, DQ validation, SCD2 transform, bulk load | 3.3M+ rows loaded, 0 quarantined, idempotent reruns proven (3,076s → 2.1s) |
| **BI Dashboards (7)** | Executive, Sales, Inventory, Procurement, Supplier, Operational, Data Quality | Every KPI reconciled exactly to the warehouse; read-only enforcement verified live |
| **Forecasting (Module A)** | 30-day demand forecasts, 3 grains | 24.13% MAPE vs. 33.23% baseline |
| **Supplier Intelligence (Module C)** | 0–100 composite risk score | −0.8331 correlation (risk vs. on-time rate) |
| **Service-Level Prediction (Module D)** | Stockout/backorder/delay probability | Brier 0.0291 vs. 0.0301 baseline (stockout) |
| **Inventory Optimization (Module B)** | Reorder point / safety stock (EOQ excluded by design) | 97.7–98.2% achieved service level across 3 targets |
| **Scenario Simulation (Module E)** | 13 precomputed what-if scenarios | Baseline equivalence to 10 decimal places |
| **Route/Cost Optimization (Module F)** | Vehicle right-sizing + consolidation | $47.3M estimated savings, zero service-level impact |
| **Analytics Copilot (Phase 8/8.1)** | Verified natural-language Q&A over the whole platform | Claim-based, deterministically verified — live-validated with a real Gemini API key |

Every module is closed-form, standard-library-only, and deliberately excludes machine learning, reinforcement learning, and autonomous optimization — see [`docs/final-architecture-review.md`](docs/final-architecture-review.md) for why, and the permanent decision framework governing any future consideration of either.

## Screenshots

**Executive dashboard** — real KPIs and revenue/margin trend, reconciled exactly to the warehouse:

![Executive dashboard](docs/screenshots/executive-dashboard.png)

**Data Quality dashboard** — ETL run health, per-table DQ score, quarantine detail:

![Data Quality dashboard](docs/screenshots/data-quality-dashboard.png)

**Analytics Copilot** — a verified answer with visible citation, source endpoint, and model/ETL-run lineage:

![Analytics Copilot](docs/screenshots/analytics-copilot.png)

## Quick start

Requirements: Docker Desktop (with Compose).

```bash
cp .env.example .env      # fill in real local values
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/health
- MySQL: localhost:3306 (schemas `atlas_oltp`, `atlas_olap` created on first boot)

To use the Analytics Copilot, add a free [Google AI Studio](https://aistudio.google.com/apikey) key to `.env`:

```bash
GEMINI_API_KEY=your-key-here
```

The copilot page (`/copilot`) shows a live "provider ready" indicator once the key is picked up (`docker compose up -d --force-recreate backend` after editing `.env` on an already-running stack).

## Technology stack

**Database**: MySQL 8 (single instance, two schemas — `atlas_oltp` transactional, `atlas_olap` OLAP star-schema warehouse — with least-privilege, per-role database grants verified live: `atlas_app`, `atlas_reporting`, `atlas_decision_support`).

**Backend**: Python, FastAPI, SQLAlchemy, Alembic, Pytest. Decision-intelligence modules use only the Python standard library — no ML framework anywhere in the platform.

**Analytics Copilot**: Google Gemini (Google AI Studio) via a configuration-driven provider abstraction (`google-genai`) — the only external network dependency in the platform, structurally confined to proposing claims that a fully local, deterministic verifier checks before anything renders.

**Frontend**: Next.js, React, TypeScript, Tailwind CSS, ECharts, TanStack Table.

**Infrastructure**: Docker / Docker Compose, GitHub Actions CI.

## Repository structure

```
ATLAS/
├── docker-compose.yml
├── .env.example
├── docker/mysql/init/         # first-boot schema + role creation
├── docs/
│   ├── ATLAS-*.md               # frozen SRS / TDD / Roadmap / Master Prompt
│   ├── ATLAS-v1.0-final-report.md   # the complete, final platform narrative
│   ├── architecture-overview.md     # system/data-flow/star-schema/ETL/copilot diagrams
│   ├── final-architecture-review.md # the standing "should we add X" decision framework
│   ├── phase*-completion.md         # per-phase validation reports (the real evidence trail)
│   ├── phase8-*.md                  # analytics copilot: spec, verification, Gemini notes
│   ├── diagrams/                    # ERD, star schema (current); early architecture drafts (superseded)
│   └── screenshots/
├── backend/
│   ├── app/                     # FastAPI app: core/, domains/, decision_support/, copilot/, api/
│   ├── alembic/                  # OLTP migrations
│   └── tests/                   # 300 tests: simulation, ETL, warehouse, dashboards, all 6 modules, copilot
├── simulation/                   # day-advancing simulation engine
├── etl/                          # extract → validate → transform → load → audit
└── frontend/                     # Next.js dashboards, Planning suite, and Analytics Copilot
```

## Documentation index

Every phase has its own completion report with real, live-queried validation numbers — nothing in this README is asserted without evidence behind it in `docs/`:

- [`docs/ATLAS-v1.0-final-report.md`](docs/ATLAS-v1.0-final-report.md) — the complete final summary (start here)
- [`docs/architecture-overview.md`](docs/architecture-overview.md) — diagrams: system architecture, data flow, star schema, ETL pipeline, copilot verification boundary
- [`docs/final-architecture-review.md`](docs/final-architecture-review.md) — why the platform stops where it stops, and the permanent decision framework for any future capability
- [`docs/phase8-copilot-architecture-diagram.md`](docs/phase8-copilot-architecture-diagram.md) — the copilot's pipeline, verification boundary highlighted
- `docs/phase3` through `docs/phase8` completion/validation reports — the full, phase-by-phase evidence trail
- [`docs/ATLAS-SRS.md`](docs/ATLAS-SRS.md) / [`docs/ATLAS-TDD.md`](docs/ATLAS-TDD.md) — frozen requirements and technical design, with every architecture decision recorded as a numbered ADR in the TDD's §14
