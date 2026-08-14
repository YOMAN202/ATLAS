# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Architecture Overview — v1.0

**Status: FINAL — v1.0, 2026-08-14**
*This document supersedes the Phase 0 drafts in `docs/diagrams/system-architecture.md` and `docs/diagrams/etl-flow.md` as the authoritative, current architecture reference. `docs/diagrams/erd.md` (OLTP entity-relationship diagram, Phase 1) and `docs/diagrams/star-schema.md` (OLAP star schema, Phase 4) remain accurate and are referenced, not duplicated, below. Companion document: `docs/ATLAS-v1.0-final-report.md` for the narrative, validated-numbers version of everything shown here as a diagram.*

---

## 1. System architecture

```mermaid
flowchart TB
    subgraph Client["Client"]
        Browser["Browser — Next.js frontend<br/>7 BI dashboards + Planning suite + Analytics Copilot"]
    end

    subgraph Backend["Backend — FastAPI"]
        API["API layer<br/>role-gated via X-Atlas-Role header"]
        DSCode["Decision Support batch modules<br/>A-F (forecasting → route optimization)"]
        Copilot["Copilot orchestration<br/>tool selection + claim generation + verification"]
    end

    subgraph DB["MySQL 8"]
        OLTP[("atlas_oltp<br/>transactional schema")]
        OLAP[("atlas_olap<br/>star-schema warehouse + ds_* tables")]
    end

    subgraph Roles["Database roles (least privilege, verified live)"]
        R_APP["atlas_app<br/>RW on atlas_oltp"]
        R_REPORT["atlas_reporting<br/>SELECT-only on atlas_olap"]
        R_DS["atlas_decision_support<br/>SELECT on atlas_olap,<br/>RW on ds_* only, per-table grants"]
    end

    Sim["Simulation engine<br/>Domain-Service-only writes (ADR-007)"]
    ETL["ETL pipeline<br/>Extract → Validate → Transform → Load"]
    Gemini[["Google Gemini<br/>(Google AI Studio, external)"]]

    Browser -->|"REST, GET + one scoped POST"| API
    API -->|"SELECT via atlas_reporting"| R_REPORT
    Copilot -->|"calls the SAME role-gated<br/>REST endpoints, never SQL"| API
    Copilot -.->|"function-calling<br/>(tool selection + claim drafting only)"| Gemini
    DSCode -->|"SELECT/INSERT/UPDATE/DELETE<br/>via atlas_decision_support"| R_DS
    Sim -->|"writes via Domain Services"| R_APP
    R_APP --> OLTP
    R_REPORT --> OLAP
    R_DS --> OLAP
    ETL -->|"reads"| OLTP
    ETL -->|"writes (its own role, root-equivalent<br/>ETL grant — see docs/ATLAS-TDD.md ADR-015)"| OLAP

    style Gemini fill:#451a03,stroke:#f59e0b,color:#fef3c7
```

**What this diagram makes explicit that a narrative can't as clearly**: three separate, least-privilege database roles enforce the read/write boundary structurally — verified live at every phase gate by actually attempting a denied write and confirming MySQL rejects it (error 1142), not just by reading the grant configuration. The only component with any external network dependency is the copilot's tool-selection/claim-drafting step, which talks to Google's Gemini API — and even that dependency is scoped to *proposing* claims, never to retrieving or computing anything; Gemini never receives a database credential and never touches `atlas_oltp` or `atlas_olap` directly.

## 2. Data flow — simulation to decision intelligence

```mermaid
flowchart LR
    A["Simulation<br/>365 days, 8 warehouses, 5,000 products,<br/>100 suppliers, 2,000 customers, 25 carriers"]
    B[("atlas_oltp<br/>292,925 orders / 732,549 order lines<br/>21,189 POs / 696,747 shipments / 33,764 returns")]
    C["ETL: Extract + Validate<br/>1,839,265 rows, 0 quarantined"]
    D["ETL: Transform + SCD2 + Load<br/>3,339,706 rows across 14 objects"]
    E[("atlas_olap<br/>7 dims, 6 facts, 1 summary table")]
    F["BI Dashboards (7)<br/>Executive / Sales / Inventory / Procurement<br/>/ Supplier / Operational / Data Quality"]
    G["Decision Intelligence (Modules A-F)<br/>writes to ds_* tables in atlas_olap"]
    H["Analytics Copilot<br/>reads BOTH the warehouse (via dashboards)<br/>AND ds_* outputs (via Planning dashboards)"]

    A --> B --> C --> D --> E
    E --> F
    E --> G
    G -.->|"ds_* results feed the<br/>Planning dashboard pages"| F
    F --> H
    G --> H
```

Every arrow in this diagram is a real, measured pipeline stage — see `docs/ATLAS-v1.0-final-report.md` §2–§13 for the validated numbers behind each one, and §15 for the runtime of each stage.

## 3. Warehouse star schema

Full entity-relationship diagram, fact grains, and design rationale: **`docs/diagrams/star-schema.md`** (unchanged since Phase 4, validated against the implemented DDL). Summary: 7 conformed dimensions (`dim_date`, `dim_region`, `dim_product`, `dim_supplier`, `dim_warehouse`, `dim_carrier`, `dim_customer`), 6 fact tables at Kimball-conformed grains (`fact_orders`, `fact_shipments`, `fact_inventory_snapshot`, `fact_procurement`, `fact_supplier_delivery`, `fact_returns`), 1 summary table (`summary_daily_revenue_by_region`). SCD2 (`effective_from`/`effective_to`/`is_current`) on `dim_supplier`/`dim_warehouse` only, ETL-enforced per ADR-012 (MySQL 8 has no native temporal-table support).

## 4. ETL pipeline

```mermaid
flowchart LR
    subgraph StageA["Stage A — Extract / Validate / Quarantine / Watermark"]
        direction LR
        EX["Extract<br/>watermark-based, per source table"]
        VA["Validate<br/>DQ-1..DQ-6 rule checks"]
        EX -->|pass| VA
        VA -->|pass| ST[("etl_extract_staging")]
        VA -->|fail| QT[("dq_quarantine")]
    end

    subgraph StageB["Stage B — Transform / SCD2 / Load / Reconcile"]
        direction LR
        TR["Transform<br/>dim/fact row-builders + SCD2 versioning"]
        SK["Surrogate key resolution<br/>Type 1 direct + SCD2 as-of-date"]
        LD["Load<br/>bulk upsert, per-object transaction"]
        RC["Reconcile<br/>row-count + grain-uniqueness checks"]
        TR --> SK --> LD --> RC
    end

    ST --> TR
    RC --> AU["Audit<br/>etl_run_log + etl_run_table_metrics<br/>(extracted/inserted/updated/quarantined/rejected,<br/>duration, rows/sec — per table, per stage)"]

    style StageA fill:#1e3a5f,stroke:#60a5fa,color:#dbeafe
    style StageB fill:#14532d,stroke:#22c55e,color:#dcfce7
```

**Real, measured throughput** (full run against the validated 365-day dataset): Stage A extracted 1,839,265 rows in 3,076s with 0 quarantined; Stage B loaded 3,339,706 rows across all 14 warehouse objects in 1,476s. A no-change rerun of Stage A completes in 2.1s (from 3,076s) — the literal, measured proof that watermark advancement only commits past durably-staged data (ADR-017). Full detail, including the three real bugs found and fixed against production-scale data: `docs/phase5-stage-a-completion.md`, `docs/phase5-stage-b-completion.md`.

## 5. Copilot verification pipeline

Full diagram, with the verification boundary highlighted explicitly and every node mapped to real code: **`docs/phase8-copilot-architecture-diagram.md`**. Summary: `User → Chat UI → Tool selection (Gemini) → Read-only analytics API → Warehouse → Claim generation (Gemini) → [Deterministic verification → Refusal decision → Verified rendering] → User`. Everything from claim generation onward runs through the same unmodified `verify_claims`/`decide_refusal`/`render` functions the 50-test CI-blocking harness proves independently of any LLM.

---

## 6. Why three diagrams live in `docs/diagrams/` and this file coexist

`docs/diagrams/erd.md` (OLTP, Phase 1) and `docs/diagrams/star-schema.md` (OLAP, Phase 4) were each finalized at their own phase gate against the actual implemented schema and have not needed to change since — they remain accurate and are referenced above rather than redrawn. `docs/diagrams/system-architecture.md` and `docs/diagrams/etl-flow.md` were Phase 0 drafts (the former still names Power BI, which the platform never actually used, and neither reflects the decision-support modules or the copilot) — this file's §1 and §4 supersede them as the current, accurate versions; the two stale files are left in place as historical record rather than deleted, each now carrying a pointer to this document.
