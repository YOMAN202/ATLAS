# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 8 Grounding Specification — Analytics Copilot Verification Harness

**Status: SPECIFICATION — 2026-08-14, NOT IMPLEMENTED**
*Companion to `docs/phase8-analytics-copilot.md`. Defines the verification harness that, per Phase 8 authorization, is the first implementation deliverable and a mandatory CI-blocking release gate — no chat interface may merge until this passes.*

This document exists because "grounded" is a claim that has to be proven the same way every other claim in this platform has been proven — with real, computed evidence, not an assertion. Every other module earned its place with a number: MAPE 24.13% (A), Brier 0.0287 (D), achieved service level 97.7–98.2% (B), a live-rechecked 0.0011-day transit-time spread (F). This spec defines the equivalent evidence bar for the copilot, and it does not let the copilot ship without meeting it.

---

## 1. Design principle: verify claims, not prose

Post-hoc regex extraction of numbers from free-generated text is a viable fallback, but the primary design is **generate-then-verify-then-render**: the LLM first produces a structured list of *claims* (typed, machine-checkable statements), each claim is verified programmatically against retrieved tool payloads, and only verified claims are rendered into natural-language prose — by a template, not by asking the LLM to "please be accurate" a second time.

```
Question + role
    │
    ▼
Tool router selects tools, retrieves payloads (+ code-built citations)
    │
    ▼
LLM drafts a CLAIMS LIST (structured, typed — not prose yet)
    e.g. [{claim_type: "fact", entity: "product_key=4231, warehouse_key=2",
           metric: "stockout_probability", value: 0.62, citation_id: "c1"},
          {claim_type: "comparison", entity_a: "demand_surge_50pct",
           entity_b: "baseline", metric: "inventory_investment",
           direction: "higher", value_a: 4497458.60, value_b: 2998304.58,
           citation_id: "c2"}]
    │
    ▼
VERIFIER (deterministic code, §2) checks every claim against the
retrieved payloads. Unverifiable claims are dropped.
    │
    ▼
If zero or insufficient verified claims survive → REFUSAL (§4)
Otherwise → render verified claims into prose via template,
            attach the Sources panel from the citation objects used.
```

A claims-list intermediate representation is checkable in a way free text is not: "is `stockout_probability` for `(4231, 2)` really `0.62` in the retrieved payload" is a lookup; "did the prose paragraph correctly convey that number in context" is not. The pure post-hoc numeric-extraction approach described in the companion doc's §4 is retained as a fallback/defense-in-depth layer (§2.3), not the primary mechanism.

## 2. Numeric and answer verification

### 2.1 Numeric consistency
Every claim's `value` field is checked against the flattened set of values in the tool payloads actually retrieved for this question, within a tolerance:

- **Exact match preferred.** A claim value equal (after normalizing currency/percent formatting) to a retrieved payload field is verified directly.
- **Derived-arithmetic match.** A claim may state a value *derived* from two or more retrieved values (a difference, a percentage delta, a sum) — these are legitimate, not fabrications, and must be verified by recomputing the same arithmetic from the retrieved values, not rejected as "not literally present in the payload." Example: "$1.9M more" derived from Module B's $2,336,061 (90% target) and $4,240,550 (99% target) sensitivity rows is a verified derived claim, not a hallucination, because both source values are present and the arithmetic is checked.
- **Tolerance**: relative tolerance of 0.5%, or an absolute tolerance of 0.01 for currency-cent-level values — wide enough to absorb reasonable rounding/formatting choices, narrow enough that a materially wrong number still fails.
- **Unmatched numeric claims are dropped from the claims list before rendering**, not shown with a disclaimer — an unverified number is worse than no number.

### 2.2 Citation correctness
Every surviving claim must carry a `citation_id` that resolves to a real citation object built by the orchestrator (§3), which in turn resolves to a real tool call actually made for this question. A claim referencing a citation that was never actually retrieved (an LLM inventing a plausible-sounding source) fails verification and is dropped, independent of whether its numeric value happens to be correct — citing the wrong source for a right number is still a grounding failure.

### 2.3 Answer (prose) verification — defense in depth
After the verified claims list is rendered into prose (by template, not free LLM generation), a final post-hoc numeric-extraction pass (regex over the rendered text) confirms every number appearing in the final answer traces to a verified claim. This catches template bugs, not LLM hallucination — the primary defense against hallucination is §2.1–2.2 acting on the claims list *before* rendering, not this pass.

### 2.4 Source completeness
An answer must not omit an available, relevant citation. If a claim is verified against `ds_scenario_result.source_inventory_policy_model_id` and three other `source_*_model_id` fields on the same row, all four are surfaced in the Sources panel for that claim, not just the one the prose happens to mention — the requirement is "every answer must include forecast version, optimization version, etc." (per authorization), enforced by always emitting the full citation object, not a partial one the LLM selectively quoted.

## 3. Citation generation

Citations are **built by code from fields every existing endpoint already returns** — never authored by the LLM. Each tool wrapper returns `(payload, citation)`:

```
Citation {
    endpoint: str            # e.g. "/api/v1/dashboards/planning/service-level/detail"
    source_tables: list[str] # e.g. ["ds_service_level_prediction"]
    model_id: int | None
    model_name: str | None
    source_forecast_model_id: int | None
    source_supplier_model_id: int | None
    source_service_level_model_id: int | None
    source_inventory_policy_model_id: int | None
    etl_run_id: int
    generated_at: str
}
```

Every Phase 7/7.2 endpoint already returns a subset of these fields directly (e.g. `ServiceLevelSummary.model_id`/`source_forecast_model_id`/`source_supplier_model_id`; `ScenarioResultDetail`'s four `source_*_model_id` fields; `OptimizationSummary.model_id`) — citation generation for the initial scope is a matter of mapping existing response fields into this shared structure, not inventing new provenance data. No endpoint needs to change to support this.

## 4. Refusal criteria

Refusal is a **structured response type**, not free-text "I don't know" prose, so the eval harness (§5) can check it deterministically:

```
Refusal {
    status: "refused"
    reason_code: "no_matching_tool" | "entity_not_found"
               | "out_of_scope" | "insufficient_verified_evidence"
               | "data_unavailable"
    explanation: str   # human-readable, references the reason_code
}
```

| `reason_code` | Triggered when |
|---|---|
| `no_matching_tool` | The question asks for something no tool in the fixed set can retrieve — e.g. demand beyond Module A's 30-day horizon. |
| `entity_not_found` | Tool calls succeed but return empty/null for the specific entity asked about — e.g. a `product_key` that doesn't exist, or a query against a module with no active `ds_model_registry` row. |
| `out_of_scope` | The question requires a capability explicitly excluded from this release — EOQ, live scenario submission, executive briefing generation, or anything requiring a write. |
| `insufficient_verified_evidence` | Tools returned data, but the verification pass (§2) left zero or too few verified claims to construct a meaningful answer. |
| `data_unavailable` | A tool call itself failed at runtime (endpoint error, timeout) — see §7. |

**A refusal is always preferred to a fabrication.** This is the single non-negotiable behavior the whole harness exists to prove.

## 5. Evaluation datasets

Checked into the repository, versioned, and — critically — **changes to the eval set are reviewed like a code change**, not edited freely to make a failing build pass. (This guards against the same failure mode Module D's own build caught once already: an evaluation harness that was quietly measuring the wrong thing. See `docs/phase7-module-d-completion.md` §9's `naive_baseline_brier_score` bug.)

| Set | Contents | Minimum size | Tests |
|---|---|---|---|
| **Positive — known-correct** | One or more questions per initial-scope capability (KPI, forecast, supplier-risk, inventory-recommendation, service-level, scenario-comparison, existing-flag explanation), each with a hand-verified expected answer AND expected citation set | ≥ 15 per capability (≈105 total minimum) | Correctness of verified claims; citation completeness (§2.4) |
| **Scenario comparison** | Representative pairs/subsets across Module E's 13 real scenarios (not just baseline-vs-one-scenario; includes scenario-vs-scenario) | All 13 vs. baseline + ≥ 10 cross-scenario pairs | Direction and magnitude of comparison claims |
| **Explanation** | "Why" questions referencing real `contributing_factors`/`business_rationale` fields already persisted by Modules B/D | ≥ 20 | Claim traces to the correct contributing-factor field, not just *a* true number |
| **Adversarial (hallucination-provoking)** | False-premise questions ("why did service level *increase*" when it decreased), nonexistent entities, requests for out-of-scope capability, requests for predictions beyond the forecast horizon, requests mixing incompatible model versions | ≥ 30 | Must not fabricate; must either correct the false premise using real retrieved data or refuse |
| **Negative — should refuse** | Direct requests for something structurally unanswerable (EOQ, executive briefing, live scenario submission, a write) | ≥ 15 | Must refuse with the correct `reason_code` |

## 6. CI thresholds — all blocking

| Metric | Threshold | Rationale |
|---|---|---|
| Verifier self-test accuracy (synthetic injected-fabrication cases correctly caught by §2) | 100% | The verifier is the thing everything else depends on; it must be tested against known-bad inputs, not just trusted. |
| Citation-traceability on positive set (every rendered number traces to a verified claim) | 100% | Non-negotiable per §2.1 — this is enforced by construction (unverified numbers are dropped before rendering), so a failure here indicates a pipeline bug, not an occasional LLM slip. |
| Correctness on positive set (verified answer matches the hand-verified expected answer) | ≥ 95% | The one threshold allowed real slack — natural-language phrasing variance is expected; the underlying claims must still be correct. |
| Refusal correctness on negative + adversarial sets (`reason_code` matches expected, zero confident fabrications) | 100% | Any confident fabrication on a set designed to be unanswerable is a hard failure — this is the metric that most directly tests "does it know when it can't," which matters more than raw helpfulness. |
| False-refusal rate on positive set | < 5% | A softer threshold — over-caution is a UX cost, not a trust violation, but a copilot that refuses too often on answerable questions isn't useful. |

**Any threshold violation blocks the build.** The chat interface may not merge, per authorization, until every threshold above passes against the current eval sets.

## 7. Failure handling

- **Tool call failure at runtime** (endpoint error, timeout, DB connection issue): the affected claim is never drafted from data that wasn't actually retrieved — refuse with `data_unavailable`, never fall back to an LLM's unretrieved "memory" of a similar prior answer.
- **Verification failure post-draft**: one constrained regeneration attempt (draft claims again, explicitly excluding the claim(s) that failed verification), then fall back to `insufficient_verified_evidence` rather than looping. No unbounded retry.
- **Partial verification**: if some claims in a multi-part answer verify and others don't, the verified subset is still rendered (with the Sources panel reflecting only what's shown) rather than discarding a partially-good answer — but the unverified portion is never silently included.
- **Audit logging**: every interaction (question, tools called, retrieved payloads' citation objects, drafted claims, verification result per claim, final rendered answer or refusal reason_code) is logged — mirroring the platform's existing "fully auditable" standard, and providing the raw material to grow the eval sets from real observed edge cases over time, the same way Module D's calibration buckets are built from real outcomes rather than assumed ones.

## 8. Regression testing

The full eval suite (§5) re-runs on any change to: tool definitions, the claims-drafting prompt, the verifier (§2), or any existing endpoint's response schema (since a citation field renamed or removed on an existing dashboard endpoint would silently break citation generation for the copilot without anyone touching copilot code at all — this is a real cross-module coupling worth naming explicitly, not an edge case). Metrics from §6 are logged over time, not just pass/fail, so a slow decline that stays just above threshold is still visible before it becomes a failure.

## 9. What this spec deliberately does not cover

Per the approved initial scope, this spec does not define evaluation or verification behavior for **executive briefing generation** — it is out of scope for the initial release specifically because it is the hardest capability to verify (the most sources synthesized per answer, the largest surface for a claim to misattribute a fact to the wrong entity). Extending this harness to that capability is a distinct, later specification, to be written only after the initial-scope harness has run against real usage.
