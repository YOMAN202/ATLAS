# ATLAS Demo Guide

How to watch, share, and (if needed) reproduce the ATLAS v2 product demo.

## Watch it

- **Video**: [`docs/demo/atlas-demo.mp4`](demo/atlas-demo.mp4) — a ~3-minute walkthrough of
  the live production deployment.
- **Live site**: https://atlas-supply-chain-yoman202s-projects.vercel.app
- **Production verification & performance data**: [`docs/ATLAS-production-deployment.md`](ATLAS-production-deployment.md)

## What's in the video

Every shot is a real screen recording of the live production URL — no mockups, no local
dev environment, no staged data. Structure:

| Time | Segment | What's shown |
|---|---|---|
| 0:00–0:15 | Open | ATLAS branding, "Enterprise Supply Chain Intelligence Platform," key platform metrics |
| 0:15–0:55 | Executive Command Center | Revenue, margin, fulfillment, inventory value, forecast accuracy, supplier risk, stockout/backorder risk, the revenue & margin trend chart, and live operational alerts |
| 0:55–2:00 | Forecasting & intelligence | Demand forecast accuracy, supplier risk scoring and classification, inventory reorder policy — real computed figures from the production database |
| 2:00–2:15 | Supply Chain Map | Warehouse network grouped by real region, supplier risk watch panel |
| 2:15–2:30 | Scenario Simulation | Selecting scenarios from the library and reading the baseline-vs-scenario impact comparison |
| 2:30–2:38 | Verified Analytics Copilot | A real question typed and submitted live against the production API — "Retrieving, drafting, and verifying claims" mid-flight, showing the verification pipeline in motion |
| 2:38–2:46 | Close | Tagline: "Verified analytics. Explainable decisions. Enterprise-scale supply chain intelligence." |

### About the copilot segment specifically

The video shows the copilot **mid-verification** rather than a completed answer. This is an
honest constraint, not a staging choice: Google's Gemini free API tier enforces multiple
low, layered rate limits, and this session's live copilot testing (see the verification table
in `docs/ATLAS-production-deployment.md`) exhausted them during the same testing pass used to
produce this video. Three separate re-recording attempts, spaced minutes apart, all landed
mid-quota-window.

**What a completed answer actually looks like** — captured moments earlier, before the quota
tripped, against the exact same production endpoint:

```json
{
  "verified": true,
  "status": "answered",
  "answer": "summary.classification_breakdown.high is 4. suppliers.0.supplier_key is 20. suppliers.0.risk_score is 76.46. ...",
  "sources": [{
    "citation_id": "c1",
    "endpoint": "/api/v1/dashboards/planning/supplier-risk/detail",
    "source_tables": ["ds_supplier_risk_score"],
    "model_id": 7,
    "model_name": "weighted_composite_v1",
    "etl_run_id": 9,
    "generated_at": "2026-08-13 19:02:04"
  }],
  "claim_count": 9,
  "provider": "gemini"
}
```

Four such answers were captured live during this session (supplier risk, forecast accuracy,
scenario comparison, and a clean out-of-scope refusal for an explicitly-excluded capability) —
full detail in the production deployment doc. For a live demo to a recruiter with more
breathing room between questions than a rapid automated test pass, the copilot answers
normally within its free-tier limits.

## Reproducing / re-recording

The video is assembled from real Playwright screen recordings, not hand-edited footage, so
it can be regenerated at any time by re-running the same pipeline:

1. **Record clips** — `node D:/pw-cache/record_video.js` (adjust the `BASE` constant to the
   current production URL) records short interactions on each key page: landing page scroll,
   executive dashboard load, forecast/supplier-risk/inventory-policy pages, scenario card
   selection, and the supply chain map. `node record_copilot.js` separately records a live
   copilot question being typed and submitted.
2. **Build title cards** — `ffmpeg` `drawtext` over a `#0a0a0b` background (matching the
   app's own design token), driven by the filter definitions in `filter_open.txt` /
   `filter_close.txt`.
3. **Assemble** — `build_video.py` normalizes every clip to 1920×1080/30fps, trims or holds
   each to its allotted segment length, and stitches them together with `xfade` crossfade
   transitions (0.6s each) into the final MP4.

All of this requires Playwright + a Chromium binary (this session installed both to a
non-system drive to avoid disk-space constraints — see `docs/ATLAS-v2-ui-review.md`'s
verification section for that setup) and `ffmpeg`, both of which are standalone tools, not
project dependencies — nothing here is part of the app itself.

## Screenshots

Publication-quality screenshots of the live production deployment are in
[`docs/screenshots/production/`](screenshots/production/): landing, executive dashboard,
supply chain map, forecast, supplier risk, inventory policy, scenario simulation, route/cost
optimization, data quality, and the copilot workspace.
