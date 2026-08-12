# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 3 — Simulation Engine: Validation Report

**Status: COMPLETE — approved 2026-08-12**
*Sources of truth: ATLAS-SRS.md (FROZEN), ATLAS-TDD.md (FROZEN), ATLAS-Roadmap.md*

---

## 1. Scope

Phase 3 (Roadmap: Simulation Engine) generates the full OLTP transaction history the rest of the platform depends on — orders, allocation, procurement, shipping, returns — entirely through the Domain Service layer (ADR-007; the simulation never writes to a table directly). This report is the final validation artifact gating Phase 4.

Final validation run: **365 simulated days** (2021-01-01 through 2021-12-31), full target world size per TDD §10 (8 warehouses, 5,000 SKUs, 100 suppliers, 2,000 customers, 25 carriers). The original target was 5 years, revised down to 2 years and then to 1 year over the course of the run for practical overnight-runtime reasons — documented in §11.

---

## 2. Runtime Summary

The dataset was produced across three compute legs, interrupted by two Docker Desktop crashes. Both were recovered via a checkpoint/resume mechanism (§13) rather than restarting from scratch.

| Leg | Days covered | Elapsed (measured) | Outcome |
|---|---|---|---|
| 1 | 0 → ~91 | ~4,100s | Crashed mid-way through the day-91→100 checkpoint interval |
| — | reconciliation | negligible | One orphaned day (91) reconciled — see §14 |
| 2 | 90 → 155 | not measured (log lost to container recreation on crash 2) | Landed cleanly on the day-155 checkpoint boundary; no reconciliation needed |
| 3 | 155 → 365 | **6,767s (1.88h), directly measured** | Completed cleanly, checkpoint file removed on success |

Total compute time across all legs is not precisely reconstructable (leg 2's log did not survive the second crash), but a reasonable bound is **~3.5–4 hours**, within the 6–8h target range set for this run. Wall-clock time including both crash-recovery gaps was longer but is not a meaningful "runtime" figure — it reflects Docker Desktop downtime, not compute.

Per-day cost varied noticeably across legs (roughly 18–60s/day depending on host conditions at the time), consistent with steady-state profiling expectations (§3) plus normal variance from running on a shared development machine rather than dedicated infrastructure.

---

## 3. Optimization Summary

Four bottlenecks were found and fixed via steady-state profiling (days 31–33, after a 30-day warmup so in-flight queues reach realistic size) and targeted batching through new bulk Domain Service functions — additive alongside the existing single-item functions, same validation/exceptions, same business-rule outcomes:

| # | Bottleneck | Measured cost | Fix | Commit |
|---|---|---|---|---|
| 0 | Single multi-hour transaction + unbounded SQLAlchemy identity map | ~178 rows/sec degrading to ~61 rows/sec past ~1.5M modified rows | Periodic `commit()` + `expunge_all()` | `facdd47` |
| 0 | `numpy` native weighted sampling without replacement | ~3.5x slower per day after calibration | Replacement+redraw sampling (1.7x speedup, 0.01pp ABC-share difference, verified) | `ddf0f3b` |
| 1 | Per-line carrier/vehicle-type lookups + per-line order/customer fetch | ~49% of a simulated day | Cached lookups at world-init; batched customer join | `2014109` |
| 1 | Remaining per-item round-trips (procurement position fetch, supplier lead time, warehouse zone) | N+1 across generators | Bulk fetch / WorldState caches | `e98fc2b` |
| 2 | Order-line allocation, one call per line (~2,700 lines/day) | highest-volume per-day op | `allocate_order_lines_bulk` | `e3237af` / `57f3cd6` |
| 3 | Shipment dispatch, one pick/create/mark-shipped sequence per line | ~49% of a simulated day | `pick_bulk` + `create_shipments_bulk` + `mark_lines_shipped_bulk` | `62ecdd2` / `6b52f2a` |
| 4 | Shipment status advancement (became new #1 cost after dispatch was batched) | ~56% of a simulated day | `advance_shipments_status_bulk` | `0ccaf9f` |
| 5 | Order creation, one `create_order()` call per order (~1,000+/day) | ~34% of steady-state total | `create_orders_bulk` | `81c9434` |

Net effect: per-day cost dropped from an early round-2 estimate of ~330s/day to a post-optimization steady-state range of roughly 20–40s/day (the exact figure varies with host load; see §2 for what was actually measured on the final run).

A real determinism bug was found and fixed during this work, not before it — see §12.

---

## 4. Row Counts (final dataset)

| Table | Count |
|---|---|
| warehouses | 8 |
| warehouse_zones | 32 |
| products | 5,000 |
| suppliers | 100 |
| customers | 2,000 |
| carriers | 25 |
| orders | 292,925 |
| order_lines | 732,549 |
| purchase_orders | 21,189 |
| purchase_order_lines | 21,189 |
| shipments | 696,747 |
| returns | 33,764 |
| return_lines | 33,764 |
| inventory_positions | 5,000 |
| inventory_transactions | 745,763 |

---

## 5. Procurement Metrics

- 21,189 purchase orders created; 20,493 fulfilled (96.7%)
- 4,856 / 5,000 distinct products reordered at least once (97.1% of catalog)
- 235.4 POs/day average
- 2,191,815 units ordered via procurement

---

## 6. Backorder Metrics

- Order lines with a backorder: 35,802 / 732,549 (4.887%)
- Units backordered: 100,156 / 2,198,058 ordered (4.557%)

Non-zero but modest backorder pressure — consistent with the calibration fix's design intent (Zipf/Pareto demand + per-product dynamic reorder thresholds derived only from configured demand weights, supplier lead times, and a safety-margin constant, never from historical/rolling data — kept structurally isolated from Phase 7's BR-3 analytical formula).

---

## 7. Inventory Analysis

- Units shipped in window: 2,083,144
- Initial total inventory: 193,998 units; final: 214,127 units
- Average inventory (2-point approximation): 204,062 units
- Turnover ratio over the window: 10.208
- **Annualized: 41.4 turns/year**

---

## 8. ABC Demand Analysis

By realized units ordered (Zipf/Pareto demand distribution, `demand_zipf_exponent=1.0`, decorrelated from SKU number via random rank permutation):

| Segment | SKUs | Units | Share of demand |
|---|---|---|---|
| Top 20% | 1,000 | 1,802,295 | 82.0% |
| Middle 30% | 1,500 | 229,039 | 10.4% |
| Bottom 50% | 2,500 | 166,724 | 7.6% |

A genuine Pareto shape, matching the calibration goal that motivated the original demand-distribution fix (the pre-fix uniform demand model produced zero purchase orders across a 90-day run — the bug that started this optimization work).

---

## 9. Supplier Analysis

- 100 / 100 configured suppliers received at least one PO (100% utilization)
- POs per active supplier: min 152, max 294, avg 211.9 — no dead suppliers, reasonably balanced load

---

## 10. SQL Invariant Results

Ten invariant checks run against the final dataset. **All passed with zero violations:**

| Check | Violations |
|---|---|
| Negative `quantity_on_hand` | 0 |
| Negative `quantity_reserved` | 0 |
| Over-reserved (`reserved > on_hand`) | 0 |
| Order line allocated > ordered | 0 |
| Order line (allocated + backordered) > ordered | 0 |
| Shipped line with no allocation | 0 |
| PO line received > ordered | 0 |
| Orphaned order_lines (no parent order) | 0 |
| Shipment with no linked order_line | 0 |
| Return line quantity > allocated quantity | 0 |

---

## 11. Seasonality Validation

The demand generator has a real seasonal signal (FR-5.3), not a flat random rate: daily order count is `Poisson(base_rate × seasonal_multiplier)`, where the multiplier is a cosine curve — `base_daily_order_rate=800`, `seasonality_amplitude=0.35`, peaking day-of-year 335 (late November), troughing exactly half a year away.

Observed monthly averages:

| Month | Avg orders/day | Month | Avg orders/day |
|---|---|---|---|
| Jan | 999 | Jul | 604 |
| Feb | 866 | Aug | 722 |
| Mar | 739 | Sep | 872 |
| Apr | 617 | Oct | 1,010 |
| May | 531 | Nov | 1,072 |
| Jun | **526 (trough)** | Dec | **1,073 (peak)** |

Theoretical trough/peak: 520 / 1,080 (800 × (1∓0.35)). Observed values match within Poisson sampling noise — confirmation the seasonal model is operating as designed rather than by coincidence.

---

## 12. Determinism Evidence

- **Proven bit-exact at 90-day scale** during the Phase C validation run. That run caught a real divergence against the calibrated baseline (`orders_created` off by 3 of 78,143, with proportional drift downstream) traced to a missing `ORDER BY` on a bulk query feeding `allocate_order_lines_bulk`'s shared-position reservation tracker — MySQL doesn't guarantee row order without one, so which line "won" a contested position could vary between runs, cascading into different RNG consumption on every later day. Fixed (`9574eaf`) by adding `ORDER BY OrderLine.id` to both the allocation-gathering query and the dispatch-gathering query. Re-run confirmed an exact match on all metrics.
- **Independently re-verified** via `verify_checkpoint_resume.py`: a 20-day simulation run two ways — straight through, and deliberately interrupted at day 10 with a real pickle round-trip then resumed — produces byte-identical final stats and dataset row counts.
- No simulation-engine code changed between either proof and this 365-day run, so both extend to it. A full independent 365-day determinism re-comparison was **not** run for this report (would cost another full run for a check already covered by the two proofs above) — see limitations, §14.

---

## 13. Checkpoint/Resume Validation

`engine.run()` accepts `resume_from_day_index` / `rng` / `initial_stats`; `run_2year.py` pickles `(day_index, world, rng, stats)` to disk after every 10th day's commit — never before, so a checkpoint always describes state already durable in the database — and resumes from the last checkpoint rather than from day 1. The checkpoint file lives under `simulation/` (host-mounted), surviving container recreation, not just container restart.

This mechanism was exercised for real, twice, during this run's production (§2, §14), not just in the controlled `verify_checkpoint_resume.py` test.

---

## 14. Known Limitations

- **Leg 2 runtime unmeasured.** The log for the day-90→155 compute leg did not survive the second Docker Desktop crash (in-container `/tmp` is ephemeral). Total compute time is bounded (~3.5–4h) but not exactly reconstructable.
- **One manual data reconciliation was required.** The first crash landed mid-interval (day 91 fully committed, but the next checkpoint save — due at day 100 — never happened), leaving one day of committed data unreflected in any checkpoint. Unlike a clean boundary, day 91's processing had also mutated pre-existing rows created on earlier days in place: purchase orders received that day, shipments advanced that day, and returns inspected that day. Every write path across all 5 generator modules and their domain services was traced to build a complete picture before writing a single transactional recovery script (`recover_day91_orphan.py`) that reverted those in-place mutations, deleted the orphaned day-91 rows, recomputed the two denormalized inventory fields (`quantity_on_hand` from the remaining transaction ledger, `quantity_reserved` from remaining unshipped allocated lines) from first principles, and verified no negative or over-reserved quantities before committing. This is **strongly supported, not bit-exact-proven**: there is no uninterrupted 365-day baseline to diff against (constructing one would have defeated the point of resuming instead of restarting). Confidence rests on the invariant checks in §10 (all passed), the seasonality match in §11 (an indirect but meaningful signal nothing drifted), and the exhaustiveness of the code-path trace — not on a byte-for-byte comparison the way §12's 90-day proof achieved.
- **No fresh 365-day determinism re-proof.** See §12 — covered by transitivity from two prior proofs plus no intervening engine changes, but not independently re-verified at this exact scale.
- **Known simplification carried from Phase 2/3 design** (not a defect): a line partially backordered at order time is never retried once new stock arrives — backorder-retry is out of scope for Phase 3.
- **Business rules, calibration parameters, deterministic behavior, database schema, and Domain Service boundaries were not changed** during any part of this optimization or validation work, per the governing constraint for this phase.

---

## 15. Definition of Done — Final Assessment

| Gate | Status |
|---|---|
| Phase A — steady-state profiling, hotspots ranked | ✅ Done |
| Phase B — targeted optimization of measured hotspots, benchmarked | ✅ Done |
| Phase C — clean 90-day validation vs. baseline, determinism bug found and fixed, re-verified exact | ✅ Done |
| Phase D — 365-day full-scale generation run | ✅ Done — dataset complete, validated, invariant-clean |
| SQL invariants | ✅ 10/10 passed |
| Seasonality behaves as designed | ✅ Confirmed against theory |
| Determinism | ✅ Proven at 90-day scale; extends by transitivity |
| Checkpoint/resume | ✅ Verified in test and exercised twice in production |
| No unauthorized scope drift (business rules, schema, Domain Service boundaries) | ✅ Unchanged throughout |

**Phase 3 is complete and approved.**
