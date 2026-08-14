"""Planning dashboard — scenario simulation (Phase 7.2 Module E).
Read-only, via the dashboard API's existing atlas_reporting connection
(its schema-wide SELECT on atlas_olap already covers the new ds_*
tables — no new grant needed). Scenarios and their results are written
exclusively by the batch process
(backend/app/decision_support/run_module_e.py, via the separate
atlas_decision_support role) — there is no write-capable endpoint
here, per docs/phase7-2-architecture.md §1.2 (a precomputed scenario
library, not live user-submitted parameters).

Role: supply_planner, administrator — same actor as Modules A/C/D/B's
dashboards.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from app.api.cache import cache_key, get_cached, set_cached
from app.api.deps import get_current_etl_run_id, get_olap_connection
from app.core.security import ADMINISTRATOR, SUPPLY_PLANNER, require_role

router = APIRouter(prefix="/api/v1/dashboards/planning/scenarios", tags=["planning"])

_SELECT_RESULT_COLUMNS = (
    "s.id, s.scenario_type, s.scenario_name, s.parameters, s.description, "
    "r.baseline_avg_stockout_probability, r.scenario_avg_stockout_probability, "
    "r.baseline_n_high_stockout_risk, r.scenario_n_high_stockout_risk, "
    "r.baseline_avg_backorder_probability, r.scenario_avg_backorder_probability, "
    "r.baseline_inventory_investment, r.scenario_inventory_investment, "
    "r.baseline_avg_service_level, r.scenario_avg_service_level, "
    "r.baseline_procurement_volume, r.scenario_procurement_volume, "
    "r.baseline_n_suppliers_utilized, r.scenario_n_suppliers_utilized, "
    "r.changed_assumptions, r.affected_modules, r.key_drivers, r.confidence, "
    "r.sensitivity_indicators, r.n_pairs_evaluated, "
    "r.source_forecast_model_id, r.source_supplier_model_id, "
    "r.source_service_level_model_id, r.source_inventory_policy_model_id, "
    "r.generated_at"
)


class ScenarioSummary(BaseModel):
    id: int
    scenario_type: str
    scenario_name: str
    description: str
    parameters: dict
    scenario_avg_stockout_probability: float
    scenario_avg_service_level: float
    scenario_inventory_investment: float
    stockout_probability_delta: float
    service_level_delta: float
    investment_delta: float
    confidence: str


class ScenarioResultDetail(BaseModel):
    id: int
    scenario_type: str
    scenario_name: str
    description: str
    parameters: dict
    baseline_avg_stockout_probability: float
    scenario_avg_stockout_probability: float
    baseline_n_high_stockout_risk: int
    scenario_n_high_stockout_risk: int
    baseline_avg_backorder_probability: float
    scenario_avg_backorder_probability: float
    baseline_inventory_investment: float
    scenario_inventory_investment: float
    baseline_avg_service_level: float
    scenario_avg_service_level: float
    baseline_procurement_volume: float
    scenario_procurement_volume: float
    baseline_n_suppliers_utilized: int
    scenario_n_suppliers_utilized: int
    changed_assumptions: dict
    affected_modules: list[str]
    key_drivers: list[str]
    confidence: str
    sensitivity_indicators: dict
    n_pairs_evaluated: int
    source_forecast_model_id: int | None
    source_supplier_model_id: int | None
    source_service_level_model_id: int | None
    source_inventory_policy_model_id: int | None
    generated_at: str | None


def _row_to_detail(r) -> ScenarioResultDetail:
    return ScenarioResultDetail(
        id=r.id,
        scenario_type=r.scenario_type,
        scenario_name=r.scenario_name,
        description=r.description,
        parameters=json.loads(r.parameters),
        baseline_avg_stockout_probability=float(r.baseline_avg_stockout_probability),
        scenario_avg_stockout_probability=float(r.scenario_avg_stockout_probability),
        baseline_n_high_stockout_risk=r.baseline_n_high_stockout_risk,
        scenario_n_high_stockout_risk=r.scenario_n_high_stockout_risk,
        baseline_avg_backorder_probability=float(r.baseline_avg_backorder_probability),
        scenario_avg_backorder_probability=float(r.scenario_avg_backorder_probability),
        baseline_inventory_investment=float(r.baseline_inventory_investment),
        scenario_inventory_investment=float(r.scenario_inventory_investment),
        baseline_avg_service_level=float(r.baseline_avg_service_level),
        scenario_avg_service_level=float(r.scenario_avg_service_level),
        baseline_procurement_volume=float(r.baseline_procurement_volume),
        scenario_procurement_volume=float(r.scenario_procurement_volume),
        baseline_n_suppliers_utilized=r.baseline_n_suppliers_utilized,
        scenario_n_suppliers_utilized=r.scenario_n_suppliers_utilized,
        changed_assumptions=json.loads(r.changed_assumptions),
        affected_modules=json.loads(r.affected_modules),
        key_drivers=json.loads(r.key_drivers),
        confidence=r.confidence,
        sensitivity_indicators=json.loads(r.sensitivity_indicators),
        n_pairs_evaluated=r.n_pairs_evaluated,
        source_forecast_model_id=r.source_forecast_model_id,
        source_supplier_model_id=r.source_supplier_model_id,
        source_service_level_model_id=r.source_service_level_model_id,
        source_inventory_policy_model_id=r.source_inventory_policy_model_id,
        generated_at=str(r.generated_at) if r.generated_at else None,
    )


@router.get("/list", response_model=list[ScenarioSummary])
def list_scenarios(
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[ScenarioSummary]:
    """The "Scenario Planner" deliverable: every precomputed scenario
    with its headline deltas vs. the real baseline, for browsing."""
    etl_run_id = get_current_etl_run_id(conn)
    key = cache_key("scenario_list", etl_run_id)
    cached = get_cached(key)
    if cached is not None:
        return cached

    rows = conn.execute(
        text(
            f"SELECT {_SELECT_RESULT_COLUMNS} FROM ds_scenario s "
            "JOIN ds_scenario_result r ON r.scenario_id = s.id "
            "ORDER BY s.id"
        )
    ).all()

    result = [
        ScenarioSummary(
            id=r.id,
            scenario_type=r.scenario_type,
            scenario_name=r.scenario_name,
            description=r.description,
            parameters=json.loads(r.parameters),
            scenario_avg_stockout_probability=float(r.scenario_avg_stockout_probability),
            scenario_avg_service_level=float(r.scenario_avg_service_level),
            scenario_inventory_investment=float(r.scenario_inventory_investment),
            stockout_probability_delta=float(r.scenario_avg_stockout_probability)
            - float(r.baseline_avg_stockout_probability),
            service_level_delta=float(r.scenario_avg_service_level)
            - float(r.baseline_avg_service_level),
            investment_delta=float(r.scenario_inventory_investment)
            - float(r.baseline_inventory_investment),
            confidence=r.confidence,
        )
        for r in rows
    ]
    set_cached(key, result)
    return result


@router.get("/compare", response_model=list[ScenarioResultDetail])
def compare_scenarios(
    ids: str = Query(..., description="Comma-separated ds_scenario.id values to compare"),
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> list[ScenarioResultDetail]:
    """The "What-if Comparison" deliverable: full side-by-side detail
    (including Inventory Impact and Supplier Impact fields) for a
    caller-chosen set of scenarios."""
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        return []
    if not id_list:
        return []

    stmt = text(
        f"SELECT {_SELECT_RESULT_COLUMNS} FROM ds_scenario s "
        "JOIN ds_scenario_result r ON r.scenario_id = s.id "
        "WHERE s.id IN :ids ORDER BY s.id"
    ).bindparams(bindparam("ids", expanding=True))
    rows = conn.execute(stmt, {"ids": id_list}).all()

    return [_row_to_detail(r) for r in rows]


@router.get("/{scenario_id}", response_model=ScenarioResultDetail)
def get_scenario_detail(
    scenario_id: int,
    conn: Connection = Depends(get_olap_connection),
    _role: str = Depends(require_role(SUPPLY_PLANNER, ADMINISTRATOR)),
) -> ScenarioResultDetail:
    row = conn.execute(
        text(
            f"SELECT {_SELECT_RESULT_COLUMNS} FROM ds_scenario s "
            "JOIN ds_scenario_result r ON r.scenario_id = s.id WHERE s.id = :id"
        ),
        {"id": scenario_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return _row_to_detail(row)
