from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    data_quality,
    executive,
    forecast,
    inventory,
    operational,
    procurement,
    sales,
    supplier,
    supplier_risk,
)
from app.core.config import settings

app = FastAPI(title="ATLAS API", version="0.1.0")

# Dashboard frontend origin only — this API has no public/anonymous
# consumers (SEC-5's role header is meaningful only from a trusted
# frontend, not a wildcard origin).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET"],
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
