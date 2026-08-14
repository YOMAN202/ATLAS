# ATLAS
## Enterprise Supply Chain Intelligence Platform
### Phase 8.1 — Gemini Provider Notes

**Status: Gemini is the primary/default copilot LLM provider (ADR-024, `docs/ATLAS-TDD.md` §14).**

This document is separate from `docs/phase8-analytics-copilot.md` and `docs/phase8-grounding-spec.md`, which stay provider-neutral by design (ADR-023, ADR-024) — the verification-first architecture, the claim schema, and the CI-blocking gate don't know or care which LLM proposed a claim. Everything below is specific to how Gemini's API shape differs from the Anthropic tool-use shape the earlier design notes were originally sketched against, and is a record of what actually had to be figured out to wire a real provider in.

---

## 1. SDK and API surface

- **Package:** `google-genai` (PyPI), pinned `==2.18.1` in `backend/requirements.txt`.
- **Primary API paradigm:** the **Interactions API** (`client.interactions.create(...)`), not the older `generate_content`/`chats` paradigm this project's earlier internal notes assumed based on pre-2026 Gemini SDK knowledge. The `google-genai` package major version jump (1.x → 2.x) corresponds to this: the client still exposes `.chats`, `.models`, etc. for the older paradigm, but `.interactions` is what this integration uses throughout.
- **Credential:** `GEMINI_API_KEY`, read via `settings.gemini_api_key` (`backend/app/core/config.py`) — never `ANTHROPIC_API_KEY`. A missing key raises `RuntimeError` from both `GeminiClaimDraftingClient.__init__` and `run_agentic_pipeline`, the same fail-loudly discipline `AnthropicClaimDraftingClient` already used (ADR-023).
- **Model:** `settings.copilot_gemini_model`, default `gemini-3.7-flash` — a real, valid model ID confirmed directly against the installed SDK's own type definitions (`Interaction.model`'s `Literal[...]` includes it), not guessed. Kept as a setting rather than a hardcoded constant so it can be corrected without a code change.

## 2. Request/response shape differences from Anthropic-style tool use

| Concept | Anthropic (`messages.create`) | Gemini (`interactions.create`) |
|---|---|---|
| Conversation history | Client resends the full `messages` array every turn | **Server-managed** via `previous_interaction_id` — the client sends only the new turn's input |
| Tool definition | `{"name", "description", "input_schema": {...}}` | `{"type": "function", "name", "description", "parameters": {...}}` (JSON-schema `parameters`, not `input_schema`) |
| Model's tool call | A `tool_use` content block on the response, with `.id`, `.name`, `.input` | A `function_call` **step** in `interaction.steps`, with `.id`, `.name`, `.arguments` |
| Submitting a tool result | A `tool_result` content block in the next user message, keyed by `tool_use_id` | A `function_result` **input item** on the next `interactions.create` call, keyed by `call_id` (= the function_call step's `.id`), with `result: [{"type": "text", "text": ...}]` and optional `is_error: bool` |
| Turn/loop termination signal | `response.stop_reason == "tool_use"` vs. `"end_turn"` | No single field this integration relies on — see §3 below |

Because of this shape difference, `app/copilot/gemini_agent.py` is a self-contained rewrite of the tool-use loop, not a drop-in swap of a provider parameter — exactly as ADR-024 anticipated. Nothing in `verifier.py`/`refusal.py`/`renderer.py` changed; only the code that talks to the LLM and turns its response into `Claim` objects did.

## 3. Multi-turn step accumulation — an open question, handled defensively

`Interaction.steps` is a list that includes every step type (`user_input`, `model_output`, `thought`, `function_call`, `function_result`, ...). Whether a given `interactions.create` response's `.steps` contains **only the steps produced by that call** or the **full accumulated history** of the chained interaction (via `previous_interaction_id`) was not resolved from the SDK's type definitions or from documentation available at implementation time.

`run_agentic_pipeline` handles this defensively rather than assuming either behavior: it tracks a `seen_step_ids: set[str]` across the loop and only acts on a `function_call` step whose `.id` hasn't already been processed. This is correct under both possible server behaviors — if `.steps` is cumulative, already-handled calls are skipped; if it's delta-only, every step is new anyway and the set costs nothing. This was the top item to confirm during live validation (§5) — if step accumulation had duplicated `tool_results` or misnumbered citation IDs across turns despite the dedup guard, that would show up as a citation-mismatch verification failure rather than a crash.

## 4. Request-shape validation performed without a live key

Before any `GEMINI_API_KEY` was available, every request shape `gemini_agent.py` constructs — the initial plain-string-input call, the `function_result` follow-up call (including the `is_error` field), tool declarations, and `system_instruction` — was validated by calling `client.interactions.create(...)` with a syntactically-invalid dummy API key and confirming the request reached Google's servers and failed **only** on `API_KEY_INVALID`, not on any request-shape or schema validation error. This confirms the request bodies are well-formed against the real API, short of confirming actual model behavior (tool selection quality, whether it follows the `submit_claims`-only instruction, refusal behavior) — which requires a real key and is exactly what §5 covers.

## 5. Live end-to-end validation

Status: **pending a real `GEMINI_API_KEY`.** See `docs/phase8-chat-interface-completion.md` for the outcome once performed. What live validation needs to specifically confirm, beyond "it returns an answer":

1. The verification harness catches an intentionally modified/corrupted claim from a real Gemini response (not just from `FixtureClaimDraftingClient` fixtures).
2. Citation rendering shows real, retrieved values — not placeholders.
3. Refusal behavior fires correctly for an out-of-scope, entity-not-found, and insufficient-evidence question asked through the live model, not just the keyword-based `check_out_of_scope` path.
4. End-to-end latency (multiple `interactions.create` round trips per question — one per tool call plus the final `submit_claims` call, each a real network request to Google).
5. Whether the `seen_step_ids` defensive dedup (§3) was actually load-bearing, or turned out to be unnecessary because `.steps` is delta-only in practice.

## 6. Free-tier considerations

Google AI Studio's free tier has its own request-per-minute and daily quota limits, separate from any Anthropic pricing/quota this project might have used. `MAX_AGENT_TURNS = 6` in `gemini_agent.py` bounds worst-case API calls per question (at most 6 `interactions.create` calls: up to 5 tool-selection turns plus the terminal `submit_claims` turn) — a deliberate ceiling chosen to keep a single chat question's quota consumption bounded and predictable, independent of what free-tier limits turn out to be in practice.
