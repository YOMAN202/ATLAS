"""Orchestration (docs/phase8-analytics-copilot.md §2): question ->
(out-of-scope check) -> tool calls -> claim drafting -> verification
-> refusal-or-render. Tool ROUTING (deciding which tools a question
needs) is, like claim drafting, an LLM-dependent step in the approved
architecture -- it is built behind the same kind of pluggable
interface as ClaimDraftingClient (ADR-023) for the identical reason:
the deterministic parts of this pipeline (verification, refusal,
rendering) must be provable without a live model call, and are.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.copilot import tools as tool_fns
from app.copilot.citations import ToolResult
from app.copilot.llm_client import ClaimDraftingClient
from app.copilot.refusal import Refusal, check_out_of_scope, decide_refusal
from app.copilot.renderer import CopilotResponse, render
from app.copilot.tools import HttpCaller, ToolError
from app.copilot.verifier import verify_claims

_TOOL_DISPATCH = {
    "get_executive_kpis": tool_fns.get_executive_kpis,
    "get_forecast_summary": tool_fns.get_forecast_summary,
    "get_supplier_risk": tool_fns.get_supplier_risk,
    "get_inventory_recommendation": tool_fns.get_inventory_recommendation,
    "get_service_level": tool_fns.get_service_level,
    "compare_scenarios": tool_fns.compare_scenarios,
}

# Payload keys that, when present but None, indicate a specific
# looked-up entity was not found -- vs. a summary-only call, which has
# no such key at all and is never treated as an "entity missing" case.
# The check only applies when the call actually asked for a specific
# entity (the paired kwarg below is present) -- a summary-only
# get_supplier_risk call, for instance, legitimately has no "supplier"
# key in its payload and must not be misread as a failed lookup.
_ENTITY_LOOKUP_KEYS = {
    "get_supplier_risk": ("supplier", "supplier_key"),
    "get_inventory_recommendation": ("recommendation", "product_key"),
    "get_service_level": ("prediction", "product_key"),
}


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    kwargs: dict


class ToolRouter(ABC):
    @abstractmethod
    def route(self, question: str) -> list[ToolCall]:
        raise NotImplementedError


class FixtureToolRouter(ToolRouter):
    """Deterministic, version-controlled tool routing keyed by
    question -- the same ADR-023 pattern as FixtureClaimDraftingClient,
    for the same reason: routing is also an LLM-dependent step this
    pass does not exercise live."""

    def __init__(self, routes: dict[str, list[ToolCall]]) -> None:
        self._routes = routes

    def route(self, question: str) -> list[ToolCall]:
        return self._routes.get(question, [])


def _execute_tool_calls(
    tool_calls: list[ToolCall], client: HttpCaller, role: str
) -> tuple[list[ToolResult], bool, str | None]:
    """Returns (tool_results, entity_missing, error_reason)."""
    results: list[ToolResult] = []
    for i, call in enumerate(tool_calls):
        fn = _TOOL_DISPATCH.get(call.tool_name)
        if fn is None:
            return results, False, f"unknown_tool: {call.tool_name}"
        try:
            result = fn(client, role, citation_id=f"c{i + 1}", **call.kwargs)
        except ToolError as exc:
            return results, False, str(exc)
        results.append(result)

        lookup = _ENTITY_LOOKUP_KEYS.get(call.tool_name)
        if lookup is not None:
            payload_key, kwarg_key = lookup
            if kwarg_key in call.kwargs and result.payload.get(payload_key) is None:
                return results, True, None
    return results, False, None


def answer_question(
    question: str,
    role: str,
    router: ToolRouter,
    claim_client: ClaimDraftingClient,
    http_client: HttpCaller,
) -> CopilotResponse | Refusal:
    out_of_scope = check_out_of_scope(question)
    if out_of_scope is not None:
        return out_of_scope

    tool_calls = router.route(question)
    if not tool_calls:
        return Refusal(
            reason_code="no_matching_tool",
            explanation="No available tool can retrieve data relevant to this question.",
        )

    tool_results, entity_missing, error_reason = _execute_tool_calls(tool_calls, http_client, role)
    if error_reason is not None:
        return Refusal(reason_code="data_unavailable", explanation=error_reason)
    if entity_missing:
        # Short-circuit before drafting claims -- there is nothing to
        # ask an LLM about data that doesn't exist, and in production
        # this also skips an unnecessary paid API call.
        return Refusal(
            reason_code="entity_not_found",
            explanation="The requested entity was not found in the retrieved data.",
        )

    claims = claim_client.draft_claims(question, tool_results)
    verified_claims = verify_claims(claims, tool_results)

    refusal = decide_refusal(
        verified_claims, had_tool_results=bool(tool_results), entity_missing=entity_missing
    )
    if refusal is not None:
        return refusal

    return render(verified_claims)
