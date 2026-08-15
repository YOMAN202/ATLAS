"""Covers _ask_copilot's exception-to-HTTP-status mapping (app/api/v1/
copilot.py) by monkeypatching run_copilot_pipeline to raise each error
type directly -- no live Gemini call, no dependency on retrieved data.

Added after a live rate-limit error surfaced as a raw 500 during the
v1.0.1 performance audit: google-genai has two unrelated APIError
classes (google.genai.errors.APIError, and an internal
google.genai._gaos.lib.compat_errors.APIError used by the Interactions
API run_agentic_pipeline actually calls), and only the former was
caught. Every real Gemini failure from the live agentic path raises
the latter, so this endpoint had never actually turned a real upstream
failure into a clean 502 before -- this test would have caught it.
"""

import httpx
import pytest
from google.genai._gaos.lib.compat_errors import RateLimitError as GaosRateLimitError
from google.genai.errors import ClientError as PublicClientError


def _ask(client, question: str = "What is the average supplier risk score?"):
    return client.post(
        "/api/v1/copilot/ask",
        json={"question": question},
        headers={"X-Atlas-Role": "supply_planner"},
    )


def test_missing_config_returns_503(client, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("Gemini copilot provider requires settings.gemini_api_key")

    monkeypatch.setattr("app.api.v1.copilot.run_copilot_pipeline", _raise)
    resp = _ask(client)
    assert resp.status_code == 503


def test_public_api_error_returns_502(client, monkeypatch):
    def _raise(*_args, **_kwargs):
        raise PublicClientError(
            400, {"error": {"message": "bad request", "code": 400, "status": "INVALID_ARGUMENT"}}
        )

    monkeypatch.setattr("app.api.v1.copilot.run_copilot_pipeline", _raise)
    resp = _ask(client)
    assert resp.status_code == 502
    assert "Gemini API error" in resp.json()["detail"]


def test_gaos_rate_limit_error_returns_502_not_500(client, monkeypatch):
    """The specific bug found live: a real rate-limit error from the
    Interactions API path was falling through to an unhandled 500."""
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1/interactions")
    response = httpx.Response(429, request=request)

    def _raise(*_args, **_kwargs):
        raise GaosRateLimitError("quota exceeded, retry in 30s", response=response, body=None)

    monkeypatch.setattr("app.api.v1.copilot.run_copilot_pipeline", _raise)
    resp = _ask(client)
    assert resp.status_code == 502
    assert "Gemini API error" in resp.json()["detail"]


def test_unrelated_exception_still_propagates(client, monkeypatch):
    """This endpoint should only intercept the specific error types
    above -- anything else is a real bug and must still surface as a
    500, not be silently swallowed into a misleading 502/503."""

    def _raise(*_args, **_kwargs):
        raise ValueError("something genuinely unexpected")

    monkeypatch.setattr("app.api.v1.copilot.run_copilot_pipeline", _raise)
    with pytest.raises(ValueError):
        _ask(client)
