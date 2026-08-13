# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 7 — Decision Intelligence and Optimization: Implementation Roadmap

**Status: PROPOSAL — AWAITING APPROVAL — 2026-08-13**
*Companion to `docs/phase7-architecture.md`. No implementation has begun.*

---

## 1. Module priority ranking

| Rank | Module | Business impact | Technical feasibility | Reuse |
|---|---|---|---|---|
| 1 | **A — Demand Forecasting** | High — answers the single most common planning question, and is a hard dependency for B and D | High — ADR-004 already prescribes the exact method family; real 365-day validated data enables genuine backtesting; zero external policy inputs required to produce a first result | 100% from `fact_orders`, already fully validated (`docs/phase5-validation.md`) |
| 2 | **C — Supplier Intelligence** | High — directly answers "which suppliers are becoming unreliable," fully self-contained (no dependency on any other new module) | High — `fact_supplier_delivery` already carries every needed column (`is_on_time`, `quality_rejected_quantity`, `lead_time_variance_days`); no missing policy inputs | 100% from `fact_supplier_delivery` + `fact_procurement` |
| 3 | **D — Service-Level Prediction** | High — stockout/backorder risk is directly actionable | Medium — depends on Module A's forecasts being available first; shipment-delay coverage is partially blocked by the `estimated_delivery_date` gap (§8 of the architecture doc) | Depends on A's output + `fact_inventory_snapshot` |
| 4 | **B — Inventory Optimization** | High — reorder point/safety stock is the most directly prescriptive output in this phase | Medium — reorder point/safety stock are fully computable now; **EOQ is blocked** until order-cost/holding-cost policy inputs are supplied (architecture §2) | Depends on A's output + `fact_supplier_delivery` for lead time |
| 5 | **F — Route/Cost Optimization** | Medium — real but narrower question (carrier/lane efficiency) than A–D | High — purely descriptive ranking over already-available columns, no forecasting needed | 100% from `fact_shipments` + `dim_carrier`, already what Phase 6's Operational dashboard surfaces |
| — | **E — Scenario Simulation** | Deferred | Deferred | Interface only (architecture §5/§8) — not sequenced for implementation this phase, per frozen SRS/Roadmap and your confirmation |

## 2. Recommended first module: **A — Demand Forecasting**

**Business impact.** Of your six example questions, "What will demand be next month?" is both the most frequently-asked in real supply planning and the one every other prescriptive question implicitly depends on: you cannot recommend a reorder point (Module B) or predict a stockout (Module D) without a demand forecast feeding into it. Shipping Module A first isn't just "the easiest" — it's the one whose absence blocks the most other value.

**Technical feasibility.** This is the most de-risked module in the set:
- ADR-004 already specifies the method family (statistical: moving average, exponential smoothing) — no algorithm-selection debate needed.
- The evaluation metric is already named in frozen spec (MAPE, SRS §15) — no metric-definition debate needed.
- The real, already-validated 365-day dataset supports genuine walk-forward backtesting from day one, not synthetic placeholder data.
- Unlike Module B (blocked on EOQ's missing cost inputs) or Module E (blocked on frozen-spec sequencing), Module A has **zero open policy questions** — it can be fully specified and evaluated using only what's already in the warehouse.

**Reuse.** Built entirely from `fact_orders` (already the single most row-validated fact table in the warehouse — 732,549 rows, exact reconciliation proven in `docs/phase5-validation.md` §1) via the `v_daily_demand` feature view (architecture §4). No new source data, no new ETL work, no touching frozen pipeline code.

**Runner-up: Module C (Supplier Intelligence).** Equally low-risk and fully self-contained (no dependency on any other new module), and arguably *simpler* to implement than A (no forecasting/backtesting machinery, just a weighted formula over already-computed rates). If sequencing purely by implementation simplicity rather than downstream leverage, C would be the safer first pick. A is still recommended over C because A unblocks two further modules (B, D) that C does not unblock any of — but C is the natural second module regardless of what's picked first, since it has no dependency on A's output either.

## 3. Proposed implementation order (pending your approval)

1. **Module A — Demand Forecasting.** Feature view (`v_daily_demand`, `v_demand_calendar_features`), `ds_model_registry`/`ds_experiment_run`, three benchmark models (seasonal-naive baseline, moving average, exponential smoothing), backtested via walk-forward evaluation, `ds_demand_forecast` populated for the best-performing model per (product, warehouse). New read endpoint + Planning dashboard forecast view.
2. **Module C — Supplier Intelligence.** `v_lead_time_stats`, `v_supplier_performance_trend`, `ds_supplier_risk_score` with documented weighted formula, recomputed per ETL cycle (BR-4). New read endpoint + Planning dashboard supplier-risk view.
3. **Module D — Service-Level Prediction.** Consumes Module A's forecasts + `v_inventory_position`; `ds_stockout_risk` (stockout/backorder risk only — shipment fulfillment-delay explicitly out per the architecture's disclosed gap).
4. **Module B — Inventory Optimization.** Reorder point + safety stock (fully computable) shipped first; EOQ column left `NULL` with a documented reason until you supply order-cost/holding-cost policy values, at which point it activates without a schema change.
5. **Module F — Route/Cost Optimization.** Lower priority per your decision; a self-contained, low-risk descriptive module, sequenced last because A–D collectively deliver more of the phase's stated objective ("supports operational decision-making" on demand/inventory/supplier questions) than F does.

Each module ships as: feature view(s) → model/computation logic → backtested evaluation (where applicable) → `ds_*` table populated → new read-only API endpoint → Planning dashboard view — the same "prove it before presenting it" discipline every prior phase in this project has used, not skipped for this one.

## 4. Explicit gate

Per your instruction, no module implementation begins until you approve `docs/phase7-architecture.md`. This roadmap and `docs/phase7-review-checklist.md` are presented alongside it for the same review, but approval of the roadmap's *sequencing* doesn't itself authorize starting Module A — a separate go-ahead is expected, consistent with how Phase 5 (Stage A → Stage B) and Phase 6 (proposal → implementation) were each separately gated in this project.
