"""Gemini (Google AI Studio) live agentic orchestration for the Phase
8.1 chat interface (docs/phase8-analytics-copilot.md, ADR-024,
docs/phase8-gemini-provider-notes.md).

This is the only module in the copilot package that talks to a live
LLM. It reuses the SAME unmodified verify_claims / decide_refusal /
render functions that the 50-test CI-blocking harness
(backend/tests/copilot/) already proves correct against
FixtureClaimDraftingClient -- this module adds a live tool-selecting
and claim-drafting front end, nothing else. The core invariant
(docs/phase8-grounding-spec.md) still holds: the copilot must never
become a second analytics engine. Gemini selects among the six
existing read-only retrieval tools and drafts typed claims about what
it retrieved; it never computes a number itself, and no claim reaches
the user unless verify_claims independently confirms it against the
actually-retrieved payload.
"""

import json

from app.copilot import tools as tool_fns
from app.copilot.citations import ToolResult
from app.copilot.claims import Claim, ComparisonClaim, DerivedClaim, FactClaim
from app.copilot.llm_client import ClaimDraftingClient
from app.copilot.refusal import Refusal, check_out_of_scope, decide_refusal
from app.copilot.renderer import CopilotResponse, render
from app.copilot.tools import HttpCaller, ToolError
from app.copilot.verifier import verify_claims
from app.core.config import settings

MAX_AGENT_TURNS = 6

_TOOL_DISPATCH = {
    "get_executive_kpis": tool_fns.get_executive_kpis,
    "get_forecast_summary": tool_fns.get_forecast_summary,
    "get_supplier_risk": tool_fns.get_supplier_risk,
    "get_inventory_recommendation": tool_fns.get_inventory_recommendation,
    "get_service_level": tool_fns.get_service_level,
    "compare_scenarios": tool_fns.compare_scenarios,
}

# Gemini function declarations (google-genai's function-calling shape:
# plain JSON-schema dicts, no Schema class required) for the six
# read-only retrieval tools above.
_RETRIEVAL_TOOLS = [
    {
        "type": "function",
        "name": "get_executive_kpis",
        "description": (
            "Retrieve headline executive KPIs: revenue, gross margin, order "
            "fulfillment rate, order and order-line counts."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_forecast_summary",
        "description": "Retrieve Module A's active demand forecast model summary, including weighted MAPE.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_supplier_risk",
        "description": (
            "Retrieve supplier risk scoring (Module C). Omit supplier_key for the "
            "population summary; provide it to look up one supplier's score."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "supplier_key": {
                    "type": "integer",
                    "description": "A specific supplier's surrogate key, if asking about one supplier.",
                },
                "risk_classification": {
                    "type": "string",
                    "enum": ["Low", "Medium", "High"],
                    "description": "Filter the population summary by risk tier.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "get_inventory_recommendation",
        "description": (
            "Retrieve Module B's inventory policy (reorder point, safety stock) "
            "summary, or a specific (product_key, warehouse_key) pair's recommendation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_key": {"type": "integer"},
                "warehouse_key": {"type": "integer"},
            },
        },
    },
    {
        "type": "function",
        "name": "get_service_level",
        "description": (
            "Retrieve Module D's service-level (stockout/backorder/fulfillment-delay "
            "probability) summary, or a specific (product_key, warehouse_key) pair's "
            "prediction including its contributing factors."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product_key": {"type": "integer"},
                "warehouse_key": {"type": "integer"},
            },
        },
    },
    {
        "type": "function",
        "name": "compare_scenarios",
        "description": (
            "Retrieve Module E's precomputed what-if scenario comparison for one or "
            "more scenario IDs against the baseline."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Scenario IDs to compare.",
                },
            },
            "required": ["scenario_ids"],
        },
    },
]

# The terminal tool: Gemini's only way to deliver an answer. Modeled
# directly on the Claim union (app/copilot/claims.py) so parsing is a
# straight field-by-field reconstruction, not a free-text parse.
_SUBMIT_CLAIMS_TOOL = {
    "type": "function",
    "name": "submit_claims",
    "description": (
        "Submit your final answer as a list of typed, structured claims -- never as "
        "free text. Every claim must reference a citation_id from a tool result you "
        "actually retrieved this conversation (c1, c2, ... in the order you called "
        "tools). Call this with an empty claims list if the retrieved data does not "
        "support answering the question."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim_type": {
                            "type": "string",
                            "enum": ["fact", "comparison", "derived"],
                        },
                        "metric_path": {
                            "type": "string",
                            "description": (
                                "Dotted path into a retrieved tool payload (fact/"
                                "comparison claims), e.g. 'summary.avg_risk_score' or "
                                "'scenarios.0.scenario_inventory_investment'."
                            ),
                        },
                        "value": {"description": "The claimed value (fact claims)."},
                        "citation_id": {"type": "string", "description": "fact claims"},
                        "value_a": {"type": "number", "description": "comparison claims"},
                        "value_b": {"type": "number", "description": "comparison claims"},
                        "direction": {
                            "type": "string",
                            "enum": ["higher", "lower", "equal"],
                            "description": "comparison claims",
                        },
                        "citation_id_a": {
                            "type": "string",
                            "description": "comparison/derived claims",
                        },
                        "citation_id_b": {
                            "type": "string",
                            "description": "comparison/derived claims",
                        },
                        "operation": {
                            "type": "string",
                            "enum": ["difference", "sum", "pct_delta"],
                            "description": "derived claims",
                        },
                        "operand_metric_path_a": {
                            "type": "string",
                            "description": "derived claims",
                        },
                        "operand_metric_path_b": {
                            "type": "string",
                            "description": "derived claims",
                        },
                    },
                    "required": ["claim_type"],
                },
            },
        },
        "required": ["claims"],
    },
}

_SYSTEM_PROMPT = """You are ATLAS's grounded analytics copilot. You answer questions ONLY \
using data retrieved through the provided tools -- you never state a number, fact, or \
comparison that did not come from a tool result.

Rules:
1. Call retrieval tools to gather the data you need before answering.
2. When you have enough data, call submit_claims with your answer as a list of typed \
claims. Do not answer in free text.
3. Every claim's citation_id (or citation_id_a/citation_id_b) must be the id of a tool \
result you actually retrieved this conversation -- c1, c2, ... in the order you called \
tools.
4. If the retrieved data doesn't support answering the question, call submit_claims with \
an empty claims list rather than guessing.
5. You cannot generate forecasts, inventory policies, supplier scores, or optimization \
results -- you can only retrieve and explain what ATLAS's existing modules already \
computed.
6. You have no tool for executive briefing generation, EOQ, or any write operation -- if \
asked, call submit_claims with an empty list.
"""


def _claim_from_dict(d: dict) -> Claim | None:
    """Reconstructs a typed Claim from Gemini's submit_claims arguments.
    A malformed entry (missing a required field for its claim_type) is
    dropped, not crashed on -- the verifier would reject a garbage
    claim anyway, so failing soft here just means one fewer candidate
    claim, never a 500."""
    claim_type = d.get("claim_type")
    try:
        if claim_type == "fact":
            return FactClaim(metric_path=d["metric_path"], value=d["value"], citation_id=d["citation_id"])
        if claim_type == "comparison":
            return ComparisonClaim(
                metric_path=d["metric_path"],
                value_a=d["value_a"],
                value_b=d["value_b"],
                direction=d["direction"],
                citation_id_a=d["citation_id_a"],
                citation_id_b=d["citation_id_b"],
            )
        if claim_type == "derived":
            return DerivedClaim(
                operation=d["operation"],
                operand_metric_path_a=d["operand_metric_path_a"],
                operand_metric_path_b=d["operand_metric_path_b"],
                citation_id_a=d["citation_id_a"],
                citation_id_b=d["citation_id_b"],
                value=d["value"],
            )
    except (KeyError, TypeError):
        return None
    return None


def _require_gemini_client():
    if not settings.gemini_api_key:
        raise RuntimeError(
            "Gemini copilot provider requires settings.gemini_api_key (env var "
            "GEMINI_API_KEY) to be configured. Refusing to run rather than silently "
            "falling back to an unverified response."
        )
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


class GeminiClaimDraftingClient(ClaimDraftingClient):
    """Single-shot claim drafting: given a question and ALREADY-retrieved
    tool_results, ask Gemini to draft claims about them in one call.
    Fulfills the same ClaimDraftingClient contract as
    AnthropicClaimDraftingClient (app/copilot/llm_client.py) for
    provider-abstraction parity. The live chat endpoint uses
    run_agentic_pipeline below instead, which additionally lets Gemini
    choose which tools to call."""

    def __init__(self, model: str | None = None) -> None:
        self._client = _require_gemini_client()
        self._model = model or settings.copilot_gemini_model

    def draft_claims(self, question: str, tool_results: list[ToolResult]) -> list[Claim]:
        retrieved = [
            {"citation_id": tr.citation.citation_id, "tool_name": tr.tool_name, "payload": tr.payload}
            for tr in tool_results
        ]
        prompt = (
            f"Question: {question}\n\n"
            f"Retrieved tool results (JSON):\n{json.dumps(retrieved, default=str)}\n\n"
            "Call submit_claims now with claims drawn only from the above."
        )
        interaction = self._client.interactions.create(
            model=self._model,
            input=prompt,
            system_instruction=_SYSTEM_PROMPT,
            tools=[_SUBMIT_CLAIMS_TOOL],
        )
        for step in interaction.steps:
            if getattr(step, "type", None) == "function_call" and step.name == "submit_claims":
                raw_claims = (step.arguments or {}).get("claims", [])
                return [c for c in (_claim_from_dict(rc) for rc in raw_claims) if c is not None]
        return []


def _execute_tool_call(
    name: str, arguments: dict, http_client: HttpCaller, role: str, citation_id: str
) -> ToolResult:
    fn = _TOOL_DISPATCH.get(name)
    if fn is None:
        raise ToolError(f"unknown_tool: {name}")
    return fn(http_client, role, citation_id=citation_id, **arguments)


def run_agentic_pipeline(
    question: str, role: str, http_client: HttpCaller, model: str | None = None
) -> CopilotResponse | Refusal:
    """The live path behind GET /api/v1/copilot/ask. Gemini selects
    tools via function calling AND drafts claims via the terminal
    submit_claims call, within one bounded multi-turn loop -- then,
    exactly like the fixture-tested pipeline in pipeline.py, hands off
    to the SAME unmodified verify_claims / decide_refusal / render.
    Nothing in this function computes or asserts a number; Gemini only
    proposes claims, and the deterministic verifier is what actually
    decides what's true.

    The Interactions API manages conversation history server-side via
    previous_interaction_id -- unlike the Anthropic-style pattern
    considered earlier in this project, this loop never resends the
    full message history itself.
    """
    out_of_scope = check_out_of_scope(question)
    if out_of_scope is not None:
        return out_of_scope

    client = _require_gemini_client()
    model = model or settings.copilot_gemini_model
    tools = _RETRIEVAL_TOOLS + [_SUBMIT_CLAIMS_TOOL]

    tool_results: list[ToolResult] = []
    submitted_claims: list[Claim] | None = None
    previous_interaction_id: str | None = None
    current_input: str | list = question
    # The Interactions API's exact steps-accumulation semantics across
    # previous_interaction_id chaining aren't documented at the level
    # this loop depends on, so track step ids already acted on and
    # never process one twice -- correct whether a given response's
    # `.steps` turns out to be delta-only or cumulative.
    seen_step_ids: set[str] = set()

    for _turn in range(MAX_AGENT_TURNS):
        interaction = client.interactions.create(
            model=model,
            input=current_input,
            system_instruction=_SYSTEM_PROMPT,
            tools=tools,
            previous_interaction_id=previous_interaction_id,
        )
        previous_interaction_id = interaction.id

        function_call_steps = [
            s
            for s in interaction.steps
            if getattr(s, "type", None) == "function_call" and s.id not in seen_step_ids
        ]
        for s in function_call_steps:
            seen_step_ids.add(s.id)
        if not function_call_steps:
            break  # Gemini produced only text -- no tool calls, no submission

        function_results_input = []
        for step in function_call_steps:
            if step.name == "submit_claims":
                raw_claims = (step.arguments or {}).get("claims", [])
                submitted_claims = [
                    c for c in (_claim_from_dict(rc) for rc in raw_claims) if c is not None
                ]
                function_results_input.append(
                    {
                        "type": "function_result",
                        "name": step.name,
                        "call_id": step.id,
                        "result": [{"type": "text", "text": "Claims received."}],
                    }
                )
                continue

            citation_id = f"c{len(tool_results) + 1}"
            is_error = False
            try:
                result = _execute_tool_call(
                    step.name, step.arguments or {}, http_client, role, citation_id
                )
                tool_results.append(result)
                result_text = json.dumps(
                    {"citation_id": citation_id, "payload": result.payload}, default=str
                )
            except ToolError as exc:
                is_error = True
                result_text = f"Error: {exc}"

            function_results_input.append(
                {
                    "type": "function_result",
                    "name": step.name,
                    "call_id": step.id,
                    "is_error": is_error,
                    "result": [{"type": "text", "text": result_text}],
                }
            )

        current_input = function_results_input

        if submitted_claims is not None:
            break

    if submitted_claims is None:
        return Refusal(
            reason_code="insufficient_verified_evidence",
            explanation="The copilot did not submit a grounded answer within the allotted turns.",
        )

    if not tool_results:
        return Refusal(
            reason_code="no_matching_tool",
            explanation="No available tool was used to answer this question.",
        )

    verified_claims = verify_claims(submitted_claims, tool_results)
    refusal = decide_refusal(verified_claims, had_tool_results=True, entity_missing=False)
    if refusal is not None:
        return refusal
    return render(verified_claims)
