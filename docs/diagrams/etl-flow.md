# ETL Flow Diagram (DOC-3)

**Status:** Initial version, committed in Phase 0 from `docs/ATLAS-TDD.md`
§6. Finalized in Phase 5, alongside the implemented pipeline.

```mermaid
flowchart LR
    A[Extract\nincremental, watermark-based] --> B[Validate\nDQ-1..DQ-6 checks]
    B -->|pass| C[Transform\nfact/dim mapping + SCD2]
    B -->|fail| Q[(dq_quarantine)]
    C --> D[Load\ntransactional upsert]
    D --> E[Audit + DQ Score\netl_run_log]
```

Stage A (Extract + Validate/DQ + Audit), with its full data-quality test
suite, is built and proven **before** Stage B (Transform + SCD2 + Load +
Score) — see Master Prompt §8 and Roadmap Phase 5.
