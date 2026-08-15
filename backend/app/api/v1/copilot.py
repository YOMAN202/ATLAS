"""Phase 8.1 chat interface backend endpoint
(docs/phase8-analytics-copilot.md, docs/phase8-chat-interface-completion.md).

`POST /ask` is the primary route (v1.0 final improvement -- a request
body carries the question instead of a query string, avoiding
URL-length/encoding limits on longer questions); `GET /ask` is kept
for backward compatibility, both routed through the same `_ask_copilot`
implementation. This is the ONE deliberate, scoped exception to
main.py's historical `allow_methods=["GET"]` CORS policy -- but POST
here changes only how the question is TRANSMITTED, not what the
endpoint DOES: it is still purely read-only. Nothing in this router,
or in app.copilot.provider.run_copilot_pipeline underneath it, ever
performs an INSERT/UPDATE/DELETE anywhere; the tool layer it drives
calls back into this same backend over HTTP using the identical
read-only, role-gated dashboard endpoints the frontend already uses.
No new trust boundary, no new write path -- see
docs/phase8-copilot-architecture-diagram.md for the full pipeline and
its verification boundary.

The response wraps the SAME CopilotResponse/Refusal shape the
verification harness already proves against FixtureClaimDraftingClient
(backend/tests/copilot/) -- this route is a thin HTTP layer around
app.copilot.provider.run_copilot_pipeline, nothing more.

Role gating is broad (every role that can see at least one of the six
underlying tools) rather than per-capability -- the copilot's own
role-visibility is enforced downstream, per tool call, by the same
require_role(...) dependencies already on each dashboard endpoint
(app/api/v1/executive.py, forecast.py, supplier_risk.py, ...). A
question the caller's role can't see data for naturally refuses
(ToolError -> data_unavailable), the same way the dashboard UI would
hide or 403 that page.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.copilot.provider import run_copilot_pipeline
from app.copilot.refusal import Refusal
from app.core.config import settings
from app.core.security import ADMINISTRATOR, EXECUTIVE, SUPPLY_PLANNER, require_role

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


class CitationOut(BaseModel):
    citation_id: str
    endpoint: str
    source_tables: list[str]
    model_id: int | None = None
    model_name: str | None = None
    source_forecast_model_id: int | None = None
    source_supplier_model_id: int | None = None
    source_service_level_model_id: int | None = None
    source_inventory_policy_model_id: int | None = None
    etl_run_id: int | None = None
    generated_at: str | None = None


class CopilotAnswerOut(BaseModel):
    verified: bool
    status: str  # "answered" | "refused"
    answer: str | None = None
    sources: list[CitationOut] = []
    claim_count: int = 0
    reason_code: str | None = None
    explanation: str | None = None
    provider: str = ""


class CopilotStatusOut(BaseModel):
    provider: str
    configured: bool
    model: str | None = None


class AskRequestBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


def _http_caller() -> httpx.Client:
    # Self-referential call: the copilot's tool layer talks to THIS
    # same backend over HTTP (copilot_api_base_url, ADR-023) -- never a
    # direct DB connection, never a new trust boundary. Falls back to
    # localhost:backend_port, which is correct because this process is
    # itself listening there inside its own container.
    base_url = settings.copilot_api_base_url or f"http://localhost:{settings.backend_port}"
    return httpx.Client(base_url=base_url, timeout=60.0)


@router.get("/status", response_model=CopilotStatusOut)
def copilot_status() -> CopilotStatusOut:
    """Unauthenticated, like /health -- lets the frontend show a
    passive "is the copilot provider configured" indicator without the
    user having to ask a question first and discover a 503. Reports
    only whether a credential is PRESENT, never the credential itself,
    and never claims it's valid -- a present-but-bad key still shows
    "configured": that distinction surfaces at ask time instead (see
    the APIError handling below), the same way a bad ANTHROPIC_API_KEY
    would only be caught when actually used, not preemptively."""
    if settings.copilot_llm_provider == "gemini":
        return CopilotStatusOut(
            provider="gemini",
            configured=bool(settings.gemini_api_key),
            model=settings.copilot_gemini_model if settings.gemini_api_key else None,
        )
    return CopilotStatusOut(provider=settings.copilot_llm_provider, configured=False)


def _ask_copilot(question: str, role: str) -> CopilotAnswerOut:
    """Shared implementation behind both the POST (primary) and GET
    (backward-compatible) /ask routes -- one code path, two ways to
    supply the question, per the module docstring."""
    # google-genai has two separate, unrelated APIError classes: the
    # public one above (google.genai.errors), and an internal one used
    # by the Interactions API's implementation module
    # (google.genai._gaos.lib.compat_errors -- confirmed by introspecting
    # the installed SDK, not documented anywhere public). Every real
    # Gemini failure from run_agentic_pipeline (bad key, rate limit,
    # model unavailable) raises the LATTER, so catching only the public
    # class here left every one of those falling through to an unhandled
    # 500 -- found live when a rate-limit error surfaced as a raw
    # "Internal Server Error" during the v1.0.1 performance audit.
    from google.genai._gaos.lib.compat_errors import APIError as _GaosAPIError
    from google.genai.errors import APIError

    try:
        with _http_caller() as client:
            result = run_copilot_pipeline(question, role, client)
    except RuntimeError as exc:
        # Missing GEMINI_API_KEY (or an unset copilot_llm_provider's own
        # required config) -- a deployment/configuration problem, not a
        # server bug, so this matches the platform's existing
        # not-ready-yet convention (app/api/deps.py's 503 for "no
        # successful ETL run found yet") rather than surfacing as an
        # unhandled 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except APIError as exc:
        # A real call reached Google and failed there (bad key, quota
        # exhausted, model unavailable, ...) -- distinct from the
        # RuntimeError above (never even tried). Surfaced as 502
        # (upstream provider failure) with Gemini's own message, not a
        # raw 500 -- this is the "is Gemini actually up" signal beyond
        # "is a key configured" that /status alone can't give.
        raise HTTPException(
            status_code=502, detail=f"Gemini API error ({exc.status}): {exc.message}"
        ) from exc
    except _GaosAPIError as exc:
        # Same intent as above, for the Interactions API's own error
        # class -- shaped differently (status_code, no .message
        # attribute; the real detail is in str(exc)).
        raise HTTPException(
            status_code=502, detail=f"Gemini API error ({exc.status_code}): {exc}"
        ) from exc

    if isinstance(result, Refusal):
        return CopilotAnswerOut(
            verified=False,
            status="refused",
            reason_code=result.reason_code,
            explanation=result.explanation,
            provider=settings.copilot_llm_provider,
        )

    return CopilotAnswerOut(
        verified=True,
        status="answered",
        answer=result.answer,
        sources=[CitationOut(**c.to_dict()) for c in result.sources],
        claim_count=result.claim_count,
        provider=settings.copilot_llm_provider,
    )


@router.post("/ask", response_model=CopilotAnswerOut)
def ask_copilot_post(
    body: AskRequestBody,
    role: str = Depends(require_role(EXECUTIVE, SUPPLY_PLANNER, ADMINISTRATOR)),
) -> CopilotAnswerOut:
    return _ask_copilot(body.question, role)


@router.get("/ask", response_model=CopilotAnswerOut)
def ask_copilot_get(
    question: str = Query(..., min_length=1, max_length=2000),
    role: str = Depends(require_role(EXECUTIVE, SUPPLY_PLANNER, ADMINISTRATOR)),
) -> CopilotAnswerOut:
    """Backward-compatible GET form -- kept per instruction ("preserve
    backward compatibility if practical"). New callers should prefer
    POST /ask with a JSON body."""
    return _ask_copilot(question, role)
