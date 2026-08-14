from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    copilot,
    data_quality,
    executive,
    forecast,
    inventory,
    inventory_policy,
    operational,
    procurement,
    route_cost_optimization,
    sales,
    scenario,
    service_level,
    supplier,
    supplier_risk,
)
from app.core.config import settings

app = FastAPI(title="ATLAS API", version="0.1.0")

# Dashboard frontend origin only — this API has no public/anonymous
# consumers (SEC-5's role header is meaningful only from a trusted
# frontend, not a wildcard origin).
#
# POST is allowed for exactly one route: /api/v1/copilot/ask (v1.0
# final improvement — a JSON body carries the question instead of a
# query string, for longer questions without URL-length/encoding
# limits). Every other router in this app remains GET-only, and POST
# /copilot/ask itself performs no data mutation anywhere — it is a
# transport-only change, not a new write capability. See
# docs/phase8-copilot-architecture-diagram.md.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-Atlas-Role", "Content-Type"],
)

app.include_router(executive.router)
app.include_router(sales.router)
app.include_router(inventory.router)
app.include_router(procurement.router)
app.include_router(supplier.router)
app.include_router(operational.router)
app.include_router(data_quality.router)
app.include_router(forecast.router)
app.include_router(supplier_risk.router)
app.include_router(service_level.router)
app.include_router(inventory_policy.router)
app.include_router(scenario.router)
app.include_router(route_cost_optimization.router)
app.include_router(copilot.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
