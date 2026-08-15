# ATLAS
## Enterprise Supply Chain Intelligence Platform
### v1.0.1 Performance Audit

**Status: complete — 2026-08-15**

A measurement-first pass across the platform: profile everything, fix what's real, measure again. No new features, no interface changes — those are gated behind this report, per the v1.0.1 scope. Every number below came from the actual running stack (local Docker Compose, real seeded/simulated data), not an estimate.

---

## 1. Method

Backend endpoints were timed directly with `curl`'s `time_total`/`time_starttransfer` against the live containers. Frontend bundle size came from real `next build` output, compared before/after with the same commit via `git stash`. The copilot's live Gemini path was exercised with a real `GEMINI_API_KEY` against Google AI Studio. All numbers are from a warm, idle system unless labeled "cold."

One methodology note worth stating plainly: an early measurement pass was contaminated by a background test suite hammering the same MySQL container concurrently, producing a nonsense 46-second dashboard response. That run was discarded, not reported. All numbers below are from isolated runs.

## 2. Baseline: dashboard and copilot latency (warm)

| Endpoint | Latency |
|---|---|
| Executive summary | 0.24s |
| Data Quality summary | 0.27s |
| Data Quality quarantine detail | 0.22s |
| Forecast summary | 0.26s |
| Forecast detail (200 rows) | 0.34s |
| Supplier Risk summary | 0.23s |
| Supplier Risk detail (50-row page) | 0.29s |
| Supplier Risk detail (direct lookup) | 0.23s |
| Inventory Policy summary | 0.24s |
| Inventory Policy detail (direct lookup) | 0.25s |
| Scenarios list | 0.23s |
| Scenarios compare | 0.31s |
| Copilot status | 0.29s |
| Copilot ask, out-of-scope (keyword refusal, no LLM call) | 0.38–0.59s |
| Copilot ask, live Gemini round trip | 12.5–18.3s (historical, still current — see §5) |

This matches the range already documented in `docs/ATLAS-v1.0-final-report.md` §15. Nothing in the core dashboard-query path was slow to begin with; the real problems were elsewhere.

## 3. The biggest finding: frontend dev-mode compilation

The frontend container ran `next dev`. In development mode, Next.js compiles each route lazily on its **first** request after the server starts — every request after that is fast. Measured directly:

| Route | First hit (dev mode) | Every hit after |
|---|---|---|
| `/dashboard` | 42.98s | <1s |
| `/copilot` | 11.25s | <1s |
| `/data-quality` | 6.13s | <1s |

This is invisible once a developer has clicked around for a minute, which is exactly why it hadn't been caught — but it's a real problem for the stated goal ("a recruiter never notices latency during a live demo"): the first click on almost any page could hang for tens of seconds.

**Fix**: added a production build target to `frontend/Dockerfile` (multi-stage: `next build` in a builder stage, `next start` serving the compiled output in the final stage) and `docker-compose.prod.yml`, an override that switches the frontend service to that target and drops the dev bind-mount. Confirmed directly:

| Route | First hit (production mode) |
|---|---|
| `/dashboard` | 0.32s |
| `/copilot` | 0.27s |

Usage: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`. Backend and simulation were left on their existing dev-reload setup — Python doesn't have an equivalent up-front compile cost, so there was nothing to fix there.

## 4. Copilot: entity-lookup pagination scans

`get_supplier_risk`, `get_inventory_recommendation`, and `get_service_level` (`backend/app/copilot/tools.py`) looked up a single entity by paging through the dashboard's `/detail` endpoint — up to 10 pages of 500 rows, scanned client-side for a match — because those endpoints had no direct key filter.

Real scale matters here: there are 100 suppliers (always fit in one 500-row page, even under the old code) but 2,290 (product, warehouse) pairs for inventory policy and service level (up to 5 pages under the old code). Measured the actual old-style worst case against live data:

| | Old (paginated scan, worst case) | New (direct filter) |
|---|---|---|
| Inventory Policy lookup | 5.96s | 0.40s |
| Service Level lookup | 4.15s | 0.37s |
| Supplier Risk lookup | no round-trip change (100 ≤ 500 already) | smaller payload, no client-side scan |

**Fix**: added an optional `supplier_key` / `product_key`+`warehouse_key` query parameter to the three underlying dashboard endpoints (backward compatible — existing callers unaffected) and switched the copilot's tools to use them. One request instead of a scan.

## 5. Copilot: Gemini round trip

Unchanged and not reduced this pass: a typical question still costs 12.5–18.3s, dominated by two sequential `interactions.create` network calls to Google (one to select a tool, one to submit claims) — inherent to the verification-first design, where the model must retrieve before it can propose a claim. `verify_claims`/`decide_refusal`/`render` remain sub-millisecond, pure Python, untouched.

Two things investigated here:

- **Parallel tool retrieval**: `run_agentic_pipeline` previously executed multiple tool calls within a single Gemini turn serially, even when independent. Now dispatched concurrently via a thread pool. In practice this rarely triggers — most questions result in one tool call per turn — but it's correct and free when it does apply (e.g., a question comparing two suppliers in one turn).
- **Rate limiting, found live**: testing the real Gemini path hit Google AI Studio's free-tier quota (`limit: 20` requests in a short rolling window). This surfaced a real bug: the `google-genai` SDK has two separate, unrelated `APIError` classes — the copilot's exception handling only caught the public one, but the Interactions API (what the live agentic path actually uses) raises the other. Every real Gemini failure — rate limit, bad key, model unavailable — was falling through to an unhandled 500 instead of the intended clean 502. Fixed, confirmed live (500 → 502 with a real message), and covered with a regression test (`tests/copilot/test_ask_endpoint_unit.py`) that didn't exist before.

Response streaming was not implemented — doing it correctly would mean restructuring how claims get verified before any partial text reaches the user, which risks the verification boundary this platform is built around. Progress feedback (a "retrieving… verifying…" indicator instead of a blank wait) is a frontend/UX change, deferred to the gated v2 pass along with the rest of the interface work.

## 6. Frontend bundle size

`components/chart.tsx` imported the entire `echarts` library (`import * as echarts from "echarts"`) — every chart type and component it ships, including ones this app never uses. Every chart option in the app was grepped to confirm actual usage: only `bar`, `line`, and `pie` series, with `grid`/`tooltip`/`legend`/`title`. Replaced with a tree-shaken `echarts/core` import registering only those.

Measured with real production builds, before and after (`git stash` isolated the change for a clean A/B):

| Route | Before | After | Change |
|---|---|---|---|
| `/dashboard` | 450 kB | 304 kB | −146 kB (−32%) |
| `/data-quality` | 463 kB | 317 kB | −146 kB (−32%) |
| `/forecast` | 464 kB | 318 kB | −146 kB (−31%) |
| `/inventory-policy` | 464 kB | 318 kB | −146 kB (−31%) |
| `/route-cost-optimization` | 464 kB | 318 kB | −146 kB (−31%) |
| `/scenarios` | 451 kB | 305 kB | −146 kB (−32%) |
| `/service-level` | 464 kB | 318 kB | −146 kB (−31%) |
| `/supplier-risk` | 464 kB | 318 kB | −146 kB (−31%) |

Non-chart routes (`/inventory`, `/operational`, `/procurement`, `/sales`, `/supplier`, `/copilot`, `/`) were already small (103–125 kB) and unaffected, since they never imported `echarts` at all.

Also fixed: the two dashboards (Executive, Data Quality) that were rebuilding their chart `option` object as a new literal on every render, forcing an unnecessary `echarts.setOption` call each time. The six newer "planning" dashboards already memoized this with `useMemo`; these two now match.

## 7. Backend: redundant cache-key query

`get_current_etl_run_id` (`backend/app/api/deps.py`) ran a small `SELECT` against `etl_run_log` on **every** dashboard request — including cache hits — just to compute the cache key that `app/api/cache.py` needs before it can even check the cache. Added a 5-second TTL cache around it.

This is safe because of how ETL runs actually behave: they complete on the order of minutes, not seconds, so a request landing in that 5-second window keys off the previous run — which is still a real, complete, successfully-loaded run, never a partial one. Worst case is "briefly one ETL cycle behind," which the existing cache-key design already tolerates by nature (§8).

Fixing this surfaced a real gap: the existing test fixture that clears the dashboard-response cache between tests (`app/api/cache.py`'s `_cache`) didn't know about this new cache, and that fixture turned out to be duplicated across two separate `conftest.py` files (`tests/api/` and `tests/copilot/`), both missing it. Fixed both.

## 8. Caching strategy

**Dashboard responses** (`backend/app/api/cache.py`): an in-memory LRU cache (512 entries), keyed on `(route, etl_run_id, sorted params)`. Correctness comes from the key, not a timer — once a new ETL run completes, every request computes a new key, and the previous run's entries simply age out of the bounded LRU rather than needing an explicit invalidation step. Every dashboard router uses this.

**Current ETL run id** (`backend/app/api/deps.py`, new this pass): a 5-second TTL cache, described in §7. The only cache in the platform where staleness is time-bound rather than key-bound, and the bound is small and safe for the reason given above.

**Copilot tool responses**: not separately cached. Each tool call is itself an HTTP request into the already-cached dashboard endpoints above, so it inherits that caching transparently — a repeated tool call within the cache's TTL window is already fast (~0.25s, confirmed in §2). A dedicated question-level cache (verbatim question → answer) was considered and rejected: it only catches exact repeated strings, not paraphrases, and every answer needs to stay freshly verified against the current retrieved payload — caching a full answer risks serving a claim that was true under a since-rotated ETL run. The actual latency complaint (a single question takes 12–18s) is Gemini round-trip time, which caching a repeat of the same exact question wouldn't address in practice.

**Invalidation, summarized**: nothing here needs a manual invalidation step. The dashboard cache invalidates itself the moment a new ETL run completes (new key). The ETL-run-id cache self-expires every 5 seconds. There's no cache in this platform that can silently serve stale data past one ETL cycle plus 5 seconds.

## 9. Top 5 bottlenecks, ranked by real measured impact

1. **Frontend dev-mode route compilation** — up to 43s on a page's first hit. The single largest number measured anywhere in this audit. Fixed (§3).
2. **Copilot Gemini round trip** — 12.5–18.3s per question, every question. The largest *remaining* cost in the platform, and structural: it's the price of retrieve-then-generate under a verification boundary that refuses to skip retrieval. Not reduced this pass without weakening verification or taking on a UX change (deferred to v2).
3. **Copilot entity-lookup pagination scans** — up to 5.96s worst case. Fixed (§4).
4. **Backend connection-pool/cold-start jitter** — up to ~19s on the first handful of requests after a backend restart, before settling into the steady 0.22–0.34s range. Real and measured; not root-caused this pass (see §10).
5. **Frontend bundle size** — 146 kB (32%) of unnecessary JS on every chart-bearing page. Fixed (§6).

Two items didn't make the top 5 only because they were already documented and unchanged: Operational's cross-table warehouse-capacity query and Route/Cost Optimization's 57,912-row aggregate remain the heaviest *individual* dashboard queries at 3.9–8.7s on a cache miss (`docs/ATLAS-v1.0-final-report.md` §15) — but the existing ETL-run-keyed cache means a real user pays that cost at most once per ETL cycle, not once per page load, which is why they rank below the four items above that affect every single interaction.

## 10. Remaining limitations

- **Gemini round-trip latency is not reduced.** It's inherent to the architecture this platform deliberately built (verification-first, retrieve-before-generate). The only real levers left — response streaming or a "retrieving… verifying…" progress indicator — either risk the verification boundary or belong to the frontend/UX work gated behind this report.
- **Backend cold-start jitter is measured but not explained.** The first several requests after a container restart show elevated, inconsistent latency (0.28s–18.87s observed across different endpoints) before settling into the steady ~0.25s range. Plausible causes — SQLAlchemy connection-pool warm-up, MySQL query-plan cache, or this development machine's own documented disk/host-I/O constraints — were not isolated. Worth a dedicated pass if it matters for a specific demo timing (e.g., warming the stack with a few throwaway requests before a live walkthrough is a safe, available workaround today).
- **The two heaviest individual dashboard queries were not touched this pass** (§9) — cache-protected, so lower priority than the items that were fixed, but still the right next target if further backend optimization is authorized.
- **No browser-based hydration/paint measurement.** Everything reported for the frontend is network-observed (bundle size, shell/response delivery time), not a Lighthouse or React Profiler pass measuring actual paint/hydration cost in a real browser. The bundle-size reduction in §6 should help hydration cost proportionally (less JS to parse and execute), but that specific number wasn't independently re-measured.
- **`docker-compose.prod.yml` is new and minimal.** It solves the one problem found (dev-mode compile cost) without introducing image-size optimizations (e.g., Next's `output: "standalone"`) that weren't necessary to fix that problem — a reasonable follow-up, not a gap in what was asked for here.

---

**v1.0.1 is complete.** Every fix above is backward compatible, none required changing the verification pipeline, the warehouse schema, or any decision-intelligence formula, and every number in this report came from measuring the real running stack. No interface or visual changes were made — that work starts only after this report, per the v1.0.1 → v2 gate.
