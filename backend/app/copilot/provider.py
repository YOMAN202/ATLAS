"""Configuration-driven provider selection for the Phase 8.1 chat
interface (ADR-024, docs/phase8-gemini-provider-notes.md). Gemini is
the primary/default provider; Anthropic is declared as an optional
future provider but has no live agentic implementation wired here --
selecting it raises a clear error rather than silently falling back to
Gemini.

Deliberately separate from app.copilot.pipeline (the CI-blocking,
FixtureToolRouter/FixtureClaimDraftingClient-only path proven by
backend/tests/copilot/): this module is the live-network entrypoint
used by the chat endpoint, and nothing here is imported by that test
suite.
"""

from app.copilot.llm_client import AnthropicClaimDraftingClient, ClaimDraftingClient
from app.copilot.refusal import Refusal
from app.copilot.renderer import CopilotResponse
from app.copilot.tools import HttpCaller
from app.core.config import settings


def get_claim_drafting_client() -> ClaimDraftingClient:
    """Single-shot ClaimDraftingClient for the configured provider
    (settings.copilot_llm_provider)."""
    if settings.copilot_llm_provider == "gemini":
        from app.copilot.gemini_agent import GeminiClaimDraftingClient

        return GeminiClaimDraftingClient()
    if settings.copilot_llm_provider == "anthropic":
        return AnthropicClaimDraftingClient()
    raise ValueError(f"Unknown copilot_llm_provider: {settings.copilot_llm_provider!r}")


def run_copilot_pipeline(question: str, role: str, http_client: HttpCaller) -> CopilotResponse | Refusal:
    """Live agentic entrypoint for GET /api/v1/copilot/ask
    (settings.copilot_llm_provider). Gemini is the only provider with a
    live agentic implementation in this pass -- Anthropic remains
    declared (ClaimDraftingClient ABC, AnthropicClaimDraftingClient
    stub) but is not wired to an agentic tool-selecting loop."""
    if settings.copilot_llm_provider == "gemini":
        from app.copilot.gemini_agent import run_agentic_pipeline

        return run_agentic_pipeline(question, role, http_client)
    raise ValueError(
        f"copilot_llm_provider={settings.copilot_llm_provider!r} has no live agentic "
        "implementation -- only 'gemini' is wired to the chat endpoint in this pass."
    )
