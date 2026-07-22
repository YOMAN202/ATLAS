# ATLAS

## Enterprise Supply Chain Intelligence Platform

ATLAS is a simulated enterprise supply chain intelligence platform: a
normalized OLTP schema, a rule-driven simulation engine, an incremental
ETL pipeline with a tested data-quality framework, a Kimball star-schema
warehouse, and executive/operational dashboards backed by explainable,
rule-based decision support. It is architected as a modular monolith on
MySQL 8, FastAPI, and Next.js.

Full requirements, architecture, and build order live in `docs/`:

- [`docs/ATLAS-SRS.md`](docs/ATLAS-SRS.md) — Software Requirements Specification (frozen)
- [`docs/ATLAS-TDD.md`](docs/ATLAS-TDD.md) — Technical Design Document (frozen)
- [`docs/ATLAS-Roadmap.md`](docs/ATLAS-Roadmap.md) — Development Roadmap / phase-by-phase plan
- [`docs/ATLAS-ClaudeCode-MasterPrompt.md`](docs/ATLAS-ClaudeCode-MasterPrompt.md) — the engineering contract implementation follows
- [`docs/coding-standards.md`](docs/coding-standards.md) — naming, formatting, commit, and branch conventions

## Status

**Phase 0 (Initialization & Scaffolding) — complete.** MySQL 8, a minimal
FastAPI backend, and a minimal Next.js frontend boot via Docker Compose.
No business logic yet — see the Roadmap for what each subsequent phase
adds.

## Setup

Requirements: Docker Desktop (with Compose), running.

```bash
cp .env.example .env      # fill in real local values
docker compose up --build
```

- Backend: http://localhost:8000/health
- Frontend: http://localhost:3000
- MySQL: localhost:3306 (schemas `atlas_oltp`, `atlas_olap` created on first boot — ADR-001)

## Repository Structure

```
ATLAS/
├── docker-compose.yml
├── .env.example
├── docker/mysql/init/     # first-boot schema creation (ADR-001)
├── docs/
│   ├── ATLAS-*.md          # frozen SRS / TDD / Roadmap / Master Prompt
│   ├── coding-standards.md
│   ├── adr/                # Architecture Decision Records
│   └── diagrams/           # ERD, star schema, ETL flow, system architecture
├── backend/
│   ├── app/                # FastAPI app: core/, domains/, decision_support/, api/, models/
│   ├── alembic/             # OLTP migrations
│   └── tests/
├── simulation/              # day-advancing simulation engine (Phase 3)
├── etl/                     # extract → validate → transform → load → audit (Phase 5)
└── frontend/                # Next.js dashboards + admin UI (Phase 8)
```

## Tech Stack

MySQL 8 · Python / FastAPI / SQLAlchemy / Alembic · Next.js / React /
TypeScript / Tailwind · Power BI · Docker / Docker Compose · GitHub
Actions · Pytest. See `docs/ATLAS-ClaudeCode-MasterPrompt.md` §4 for the
full approved-stack list and prohibited additions.
