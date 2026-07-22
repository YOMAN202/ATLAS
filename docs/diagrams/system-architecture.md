# System Architecture Diagram (DOC-4)

**Status:** Initial version, committed in Phase 0. Source of truth for the
architecture itself is `docs/ATLAS-TDD.md` §2 — this diagram is kept in
sync with it as components are built; finalized in Phase 10.

```mermaid
flowchart TB
    subgraph Frontend["Frontend — Next.js / React / TS"]
        UI[Dashboards + Admin UI]
    end

    subgraph Backend["Backend — FastAPI Modular Monolith"]
        API[API Layer]
        SIM[Simulation Engine Module]
        OLTP_SVC[OLTP Domain Services\nProcurement / Inventory / Warehouse / Transportation / Orders]
        DS[Decision Support Module]
    end

    subgraph ETL["ETL Pipeline — Python / Pandas"]
        EXTRACT[Extract]
        VALIDATE[Validate + DQ Checks]
        TRANSFORM[Transform / Dimensional Model]
        LOAD[Load]
    end

    subgraph DB["MySQL 8"]
        OLTP[(OLTP Schema)]
        OLAP[(OLAP Warehouse Schema)]
    end

    subgraph BI["Power BI"]
        PBI[Executive + Operational Reports]
    end

    UI -->|REST| API
    API --> OLTP_SVC
    API --> DS
    SIM --> OLTP_SVC
    OLTP_SVC --> OLTP
    DS --> OLAP
    EXTRACT --> OLTP
    EXTRACT --> VALIDATE --> TRANSFORM --> LOAD --> OLAP
    PBI --> OLAP
    API -->|reporting queries| OLAP
```

**Phase 0 status:** MySQL, an empty FastAPI backend, and an empty Next.js
frontend are running via `docker compose up`. Every other box (Domain
Services, Simulation Engine, ETL, Decision Support, Power BI) is built in
its designated Roadmap phase — see `docs/ATLAS-Roadmap.md`.
