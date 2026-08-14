"""The copilot's fixed tool set (docs/phase8-analytics-copilot.md §3):
one tool per approved-scope dashboard endpoint, called over the SAME
read-only REST API the frontend already uses -- never SQL, never a
direct database connection. Each tool returns a ToolResult (payload +
code-built citation), never raw prose.

`HttpCaller` is the minimal interface both a real `httpx.Client` and
FastAPI's `TestClient` already satisfy (`.get(path, headers=...) ->
Response` with `.status_code`/`.json()`), so tests exercise the exact
same tool code as production, pointed at an in-process app instead of
a live server (see backend/tests/copilot/conftest.py).
"""

from typing import Protocol

from app.copilot.citations import Citation, ToolResult

# The bounded page scan below exists because the underlying detail
# endpoints (frozen, per-module dashboard contracts -- not modified
# here) have no single-entity lookup filter, only pagination and
# coarse filters. Bounding it keeps a lookup miss cheap and turns into
# a correct `entity_not_found` refusal rather than an unbounded scan.
_MAX_LOOKUP_PAGES = 10
_LOOKUP_PAGE_SIZE = 500


class HttpCaller(Protocol):
    def get(self, url: str, headers: dict | None = None, params: dict | None = None): ...


class ToolError(Exception):
    """A tool call could not complete (endpoint error, timeout, non-200
    response) -- distinct from a tool call that succeeded but found no
    matching entity. Callers map this to Refusal(reason_code=
    'data_unavailable'), never to a fabricated answer."""


def _get_json(client: HttpCaller, role: str, path: str, params: dict | None = None) -> dict:
    # None-valued params must be dropped, not sent -- an HTTP client
    # serializes {"risk_classification": None} as the literal string
    # "None", which fails the endpoint's own pattern validation rather
    # than being treated as "unset" (the same care the frontend's own
    # buildQuery() already takes, lib/api-client.ts).
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    resp = client.get(path, headers={"X-Atlas-Role": role}, params=clean_params)
    if resp.status_code != 200:
        raise ToolError(f"{path} returned HTTP {resp.status_code}")
    return resp.json()


def get_executive_kpis(client: HttpCaller, role: str, citation_id: str) -> ToolResult:
    """KPI explanation: headline revenue/margin/fulfillment KPIs."""
    payload = _get_json(client, role, "/api/v1/dashboards/executive")
    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/executive",
        source_tables=("summary_daily_revenue_by_region", "fact_orders"),
        etl_run_id=payload.get("as_of", {}).get("etl_run_id"),
    )
    return ToolResult(tool_name="get_executive_kpis", payload=payload, citation=citation)


def get_forecast_summary(client: HttpCaller, role: str, citation_id: str) -> ToolResult:
    """Forecast explanation: Module A's active model and headline
    numbers."""
    payload = _get_json(client, role, "/api/v1/dashboards/planning/forecast/summary")
    active_model = payload.get("active_model") or {}
    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/planning/forecast/summary",
        source_tables=("ds_demand_forecast", "ds_model_registry", "ds_experiment_run"),
        model_id=active_model.get("model_id"),
        model_name=active_model.get("model_name"),
        etl_run_id=payload.get("etl_run_id"),
        generated_at=payload.get("forecast_generated_at"),
    )
    return ToolResult(tool_name="get_forecast_summary", payload=payload, citation=citation)


def get_supplier_risk(
    client: HttpCaller,
    role: str,
    citation_id: str,
    supplier_key: int | None = None,
    risk_classification: str | None = None,
) -> ToolResult:
    """Supplier risk explanation (and existing-flag "anomaly"
    explanation for High-classified suppliers -- no new detection
    logic, only retrieval of what Module C already computed)."""
    summary = _get_json(client, role, "/api/v1/dashboards/planning/supplier-risk/summary")

    row = None
    if supplier_key is not None:
        for page in range(1, _MAX_LOOKUP_PAGES + 1):
            detail = _get_json(
                client,
                role,
                "/api/v1/dashboards/planning/supplier-risk/detail",
                params={
                    "page": page,
                    "page_size": _LOOKUP_PAGE_SIZE,
                    "risk_classification": risk_classification,
                },
            )
            match = next((r for r in detail["data"] if r["supplier_key"] == supplier_key), None)
            if match is not None:
                row = match
                break
            if page * _LOOKUP_PAGE_SIZE >= detail["total"]:
                break
        payload = {"summary": summary, "supplier": row}
    else:
        detail = _get_json(
            client,
            role,
            "/api/v1/dashboards/planning/supplier-risk/detail",
            params={
                "page": 1,
                "page_size": _LOOKUP_PAGE_SIZE,
                "risk_classification": risk_classification,
            },
        )
        payload = {"summary": summary, "suppliers": detail["data"]}

    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/planning/supplier-risk/detail",
        source_tables=("ds_supplier_risk_score",),
        model_id=summary.get("model_id"),
        model_name=summary.get("model_name"),
        etl_run_id=summary.get("etl_run_id"),
        generated_at=summary.get("generated_at"),
    )
    return ToolResult(tool_name="get_supplier_risk", payload=payload, citation=citation)


def get_inventory_recommendation(
    client: HttpCaller,
    role: str,
    citation_id: str,
    product_key: int | None = None,
    warehouse_key: int | None = None,
) -> ToolResult:
    """Inventory recommendation explanation: Module B's reorder point /
    safety stock, and (already-generated) business_rationale for a
    specific (product, warehouse) pair."""
    summary = _get_json(client, role, "/api/v1/dashboards/planning/inventory-policy/summary")

    row = None
    if product_key is not None and warehouse_key is not None:
        for page in range(1, _MAX_LOOKUP_PAGES + 1):
            detail = _get_json(
                client,
                role,
                "/api/v1/dashboards/planning/inventory-policy/detail",
                params={"page": page, "page_size": _LOOKUP_PAGE_SIZE},
            )
            match = next(
                (
                    r
                    for r in detail["data"]
                    if r["product_key"] == product_key and r["warehouse_key"] == warehouse_key
                ),
                None,
            )
            if match is not None:
                row = match
                break
            if page * _LOOKUP_PAGE_SIZE >= detail["total"]:
                break
        payload = {"summary": summary, "recommendation": row}
    else:
        payload = {"summary": summary}

    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/planning/inventory-policy/detail",
        source_tables=("ds_inventory_policy",),
        model_id=summary.get("model_id"),
        model_name=summary.get("model_name"),
        source_forecast_model_id=summary.get("source_forecast_model_id"),
        source_supplier_model_id=summary.get("source_supplier_model_id"),
        source_service_level_model_id=summary.get("source_service_level_model_id"),
        etl_run_id=summary.get("etl_run_id"),
        generated_at=summary.get("generated_at"),
    )
    return ToolResult(tool_name="get_inventory_recommendation", payload=payload, citation=citation)


def get_service_level(
    client: HttpCaller,
    role: str,
    citation_id: str,
    product_key: int | None = None,
    warehouse_key: int | None = None,
) -> ToolResult:
    """Service-level (stockout/backorder/fulfillment-delay) explanation
    for a specific (product, warehouse) pair -- and existing-flag
    "anomaly" explanation for high-stockout-risk pairs."""
    summary = _get_json(client, role, "/api/v1/dashboards/planning/service-level/summary")

    row = None
    if product_key is not None and warehouse_key is not None:
        for page in range(1, _MAX_LOOKUP_PAGES + 1):
            detail = _get_json(
                client,
                role,
                "/api/v1/dashboards/planning/service-level/detail",
                params={"page": page, "page_size": _LOOKUP_PAGE_SIZE},
            )
            match = next(
                (
                    r
                    for r in detail["data"]
                    if r["product_key"] == product_key and r["warehouse_key"] == warehouse_key
                ),
                None,
            )
            if match is not None:
                row = match
                break
            if page * _LOOKUP_PAGE_SIZE >= detail["total"]:
                break
        payload = {"summary": summary, "prediction": row}
    else:
        payload = {"summary": summary}

    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/planning/service-level/detail",
        source_tables=("ds_service_level_prediction",),
        model_id=summary.get("model_id"),
        model_name=summary.get("model_name"),
        source_forecast_model_id=summary.get("source_forecast_model_id"),
        source_supplier_model_id=summary.get("source_supplier_model_id"),
        etl_run_id=summary.get("etl_run_id"),
        generated_at=summary.get("generated_at"),
    )
    return ToolResult(tool_name="get_service_level", payload=payload, citation=citation)


def compare_scenarios(
    client: HttpCaller, role: str, citation_id: str, scenario_ids: list[int]
) -> ToolResult:
    """Scenario comparison: Module E's precomputed what-if library,
    baseline vs. one or more scenarios."""
    payload_list = _get_json(
        client,
        role,
        "/api/v1/dashboards/planning/scenarios/compare",
        params={"ids": ",".join(str(i) for i in scenario_ids)},
    )
    payload = {"scenarios": payload_list}
    first = payload_list[0] if payload_list else {}
    citation = Citation(
        citation_id=citation_id,
        endpoint="/api/v1/dashboards/planning/scenarios/compare",
        source_tables=("ds_scenario", "ds_scenario_result"),
        source_forecast_model_id=first.get("source_forecast_model_id"),
        source_supplier_model_id=first.get("source_supplier_model_id"),
        source_service_level_model_id=first.get("source_service_level_model_id"),
        source_inventory_policy_model_id=first.get("source_inventory_policy_model_id"),
        generated_at=first.get("generated_at"),
    )
    return ToolResult(tool_name="compare_scenarios", payload=payload, citation=citation)
