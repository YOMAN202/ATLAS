"""Module F entrypoint: vehicle right-sizing and shipment consolidation
recommendations over real shipment/procurement data, scoped to a
representative 30-day analysis window (2021-12-02 through 2021-12-31 —
the last 30 real days of shipment activity, the same "recent window,
not the full year" convention Modules A/D's own backtests already
use), not the full 696,747-shipment history.

Run as: python -m app.decision_support.run_module_f
"""

import json
import time
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.deps import get_current_etl_run_id
from app.decision_support.db import get_engine
from app.decision_support.route_cost_optimization import (
    VehicleSpec,
    compute_consolidation_recommendation,
    compute_right_sizing_recommendation,
)

ANALYSIS_WINDOW_START = date(2021, 12, 2)
ANALYSIS_WINDOW_END = date(2021, 12, 31)

# A real-data-validated premise, checked at run time (not just
# assumed): right-sizing changes vehicle type, never transit time, so
# it has provable zero service-level impact. If a future data refresh
# ever broke this, this gate would catch it before persisting.
TRANSIT_DAYS_INVARIANCE_TOLERANCE_DAYS = 0.1

MODEL_PARAMETERS = {
    "formula": "cheapest_sufficient_vehicle_right_sizing_and_same_day_od_consolidation",
    "analysis_window_start": str(ANALYSIS_WINDOW_START),
    "analysis_window_end": str(ANALYSIS_WINDOW_END),
    "external_optimization_engine": False,
}


def _load_vehicle_types(conn: Connection) -> dict[str, VehicleSpec]:
    rows = conn.execute(
        text(
            "SELECT vehicle_type_code, vehicle_capacity_units, vehicle_cost_per_mile "
            "FROM dim_carrier GROUP BY vehicle_type_code, vehicle_capacity_units, "
            "vehicle_cost_per_mile"
        )
    ).all()
    return {
        r.vehicle_type_code: VehicleSpec(
            capacity_units=r.vehicle_capacity_units,
            cost_per_mile=float(r.vehicle_cost_per_mile),
        )
        for r in rows
    }


def _load_window_shipments(conn: Connection) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT fs.shipment_number, fs.origin_warehouse_key, fs.destination_customer_key, "
            "dd.full_date AS ship_date, fs.distance_miles, dc.vehicle_type_code "
            "FROM fact_shipments fs "
            "JOIN dim_date dd ON dd.date_key = fs.ship_date_key "
            "JOIN dim_carrier dc ON dc.carrier_key = fs.carrier_key "
            "WHERE dd.full_date BETWEEN :start AND :end AND fs.distance_miles IS NOT NULL"
        ),
        {"start": ANALYSIS_WINDOW_START, "end": ANALYSIS_WINDOW_END},
    ).all()
    return [dict(r._mapping) for r in rows]


def _load_shipment_quantities(conn: Connection) -> dict[str, int]:
    rows = conn.execute(
        text(
            "SELECT shipment_number, SUM(allocated_quantity) AS total_quantity "
            "FROM fact_orders WHERE shipment_number IS NOT NULL GROUP BY shipment_number"
        )
    ).all()
    return {r.shipment_number: int(r.total_quantity) for r in rows}


def _validate_transit_days_invariance(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT dc.vehicle_type_code, AVG(fs.transit_days) AS avg_transit_days "
            "FROM fact_shipments fs JOIN dim_carrier dc ON dc.carrier_key = fs.carrier_key "
            "WHERE fs.transit_days IS NOT NULL GROUP BY dc.vehicle_type_code"
        )
    ).all()
    averages = [float(r.avg_transit_days) for r in rows]
    spread = max(averages) - min(averages)
    if spread > TRANSIT_DAYS_INVARIANCE_TOLERANCE_DAYS:
        print(
            f"VALIDATION_FAILURE: transit_days varies by vehicle type (spread={spread:.4f} days) "
            "-- right-sizing's zero-service-level-impact premise no longer holds",
            flush=True,
        )
        print("status=FAILED", flush=True)
        raise SystemExit(1)
    print(f"transit_days_invariance_check=PASSED (spread={spread:.4f} days)", flush=True)


def _build_right_sizing_recommendations(
    shipments: list[dict], quantities: dict[str, int], vehicle_types: dict[str, VehicleSpec]
) -> list[dict]:
    recommendations = []
    for s in shipments:
        total_quantity = quantities.get(s["shipment_number"])
        if not total_quantity:
            continue
        rec = compute_right_sizing_recommendation(
            total_quantity=total_quantity,
            distance_miles=float(s["distance_miles"]),
            current_vehicle_type_code=s["vehicle_type_code"],
            vehicle_types=vehicle_types,
        )
        if rec is None:
            continue
        recommendations.append(
            {
                "recommendation_type": "right_sizing",
                "origin_warehouse_key": s["origin_warehouse_key"],
                "shipment_date": s["ship_date"],
                "shipment_numbers": [s["shipment_number"]],
                "total_quantity": total_quantity,
                "distance_miles": float(s["distance_miles"]),
                "current_vehicle_type_code": s["vehicle_type_code"],
                "rec": rec,
            }
        )
    return recommendations


def _build_consolidation_recommendations(
    shipments: list[dict], quantities: dict[str, int], vehicle_types: dict[str, VehicleSpec]
) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for s in shipments:
        if s["destination_customer_key"] is None:
            continue
        total_quantity = quantities.get(s["shipment_number"])
        if not total_quantity:
            continue
        key = (s["origin_warehouse_key"], s["destination_customer_key"], s["ship_date"])
        groups[key].append({**s, "total_quantity": total_quantity})

    recommendations = []
    for (origin_warehouse_key, _destination_customer_key, ship_date), members in groups.items():
        if len(members) < 2:
            continue
        rec = compute_consolidation_recommendation(
            quantities=[m["total_quantity"] for m in members],
            distances=[float(m["distance_miles"]) for m in members],
            current_vehicle_type_codes=[m["vehicle_type_code"] for m in members],
            vehicle_types=vehicle_types,
        )
        if rec is None:
            continue
        recommendations.append(
            {
                "recommendation_type": "consolidation",
                "origin_warehouse_key": origin_warehouse_key,
                "shipment_date": ship_date,
                "shipment_numbers": [m["shipment_number"] for m in members],
                "total_quantity": rec.total_quantity,
                "distance_miles": rec.avg_distance_miles,
                "current_vehicle_type_code": members[0]["vehicle_type_code"],
                "rec": rec,
            }
        )
    return recommendations


def _get_or_create_model(conn: Connection) -> int:
    params_json = json.dumps(MODEL_PARAMETERS, sort_keys=True)
    existing = conn.execute(
        text(
            "SELECT id FROM ds_model_registry WHERE module = 'route_cost_optimization' "
            "AND model_name = 'vehicle_right_sizing_and_consolidation_v1' "
            "AND parameters = CAST(:params AS JSON)"
        ),
        {"params": params_json},
    ).scalar()
    if existing is not None:
        return existing
    result = conn.execute(
        text(
            "INSERT INTO ds_model_registry (module, model_name, parameters, is_active, created_at) "
            "VALUES ('route_cost_optimization', 'vehicle_right_sizing_and_consolidation_v1', "
            "CAST(:params AS JSON), 1, :now)"
        ),
        {"params": params_json, "now": datetime.now(UTC)},
    )
    return result.lastrowid


def _validate_cost_reconciliation(recommendations: list[dict]) -> None:
    # current_total_cost, recommended_total_cost, and estimated_savings
    # are each independently rounded to cents, so double-rounding can
    # introduce up to ~1 cent of drift versus recomputing the identity
    # from the already-rounded fields -- a disclosed tolerance, not a
    # sign of a broken formula.
    for r in recommendations:
        rec = r["rec"]
        expected = round(rec.current_total_cost - rec.estimated_savings, 2)
        if abs(expected - rec.recommended_total_cost) > 0.02:
            print(
                f"VALIDATION_FAILURE: cost reconciliation failed for shipment(s) "
                f"{r['shipment_numbers']}: current ({rec.current_total_cost}) - savings "
                f"({rec.estimated_savings}) != recommended ({rec.recommended_total_cost})",
                flush=True,
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
    print(f"cost_reconciliation_check=PASSED ({len(recommendations)} recommendations)", flush=True)


def _validate_feasibility(
    recommendations: list[dict], vehicle_types: dict[str, VehicleSpec]
) -> None:
    for r in recommendations:
        rec = r["rec"]
        capacity = vehicle_types[rec.recommended_vehicle_type_code].capacity_units
        if capacity < r["total_quantity"]:
            print(
                f"VALIDATION_FAILURE: recommended vehicle "
                f"{rec.recommended_vehicle_type_code} (capacity {capacity}) is too small for "
                f"total_quantity {r['total_quantity']}",
                flush=True,
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
    print("feasibility_check=PASSED", flush=True)


def _validate_explainability(recommendations: list[dict]) -> None:
    for r in recommendations:
        rec = r["rec"]
        if not rec.business_rationale or not rec.contributing_factors:
            print(
                f"VALIDATION_FAILURE: missing business_rationale/contributing_factors for "
                f"shipment(s) {r['shipment_numbers']}",
                flush=True,
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
    print("explainability_check=PASSED", flush=True)


def _persist(conn: Connection, recommendations: list[dict], model_id: int, etl_run_id: int) -> int:
    conn.execute(
        text("DELETE FROM ds_optimization_recommendation WHERE model_id = :model_id"),
        {"model_id": model_id},
    )
    now = datetime.now(UTC)
    rows = []
    for r in recommendations:
        rec = r["rec"]
        rows.append(
            {
                "recommendation_type": r["recommendation_type"],
                "origin_warehouse_key": r["origin_warehouse_key"],
                "shipment_date": r["shipment_date"],
                "shipment_numbers": json.dumps(r["shipment_numbers"]),
                "total_quantity": r["total_quantity"],
                "distance_miles": r["distance_miles"],
                "current_vehicle_type_code": r["current_vehicle_type_code"],
                "current_total_cost": rec.current_total_cost,
                "recommended_vehicle_type_code": rec.recommended_vehicle_type_code,
                "recommended_total_cost": rec.recommended_total_cost,
                "estimated_savings": rec.estimated_savings,
                "confidence": rec.confidence,
                "contributing_factors": json.dumps(rec.contributing_factors),
                "business_rationale": rec.business_rationale[:500],
                "model_id": model_id,
                "etl_run_id": etl_run_id,
                "generated_at": now,
            }
        )
    if rows:
        conn.execute(
            text(
                "INSERT INTO ds_optimization_recommendation "
                "(recommendation_type, origin_warehouse_key, shipment_date, shipment_numbers, "
                "total_quantity, distance_miles, current_vehicle_type_code, current_total_cost, "
                "recommended_vehicle_type_code, recommended_total_cost, estimated_savings, "
                "confidence, contributing_factors, business_rationale, model_id, etl_run_id, "
                "generated_at) "
                "VALUES (:recommendation_type, :origin_warehouse_key, :shipment_date, "
                "CAST(:shipment_numbers AS JSON), :total_quantity, :distance_miles, "
                ":current_vehicle_type_code, :current_total_cost, "
                ":recommended_vehicle_type_code, :recommended_total_cost, :estimated_savings, "
                ":confidence, CAST(:contributing_factors AS JSON), :business_rationale, "
                ":model_id, :etl_run_id, :generated_at)"
            ),
            rows,
        )
    return len(rows)


def main() -> None:
    engine = get_engine()
    t0 = time.perf_counter()

    with engine.connect() as conn:
        etl_run_id = get_current_etl_run_id(conn)
        print(f"etl_run_id={etl_run_id}", flush=True)

        _validate_transit_days_invariance(conn)

        vehicle_types = _load_vehicle_types(conn)
        print(f"vehicle_types={vehicle_types}", flush=True)

        shipments = _load_window_shipments(conn)
        quantities = _load_shipment_quantities(conn)
        print(
            f"n_shipments_in_window={len(shipments)} "
            f"n_shipments_with_order_lines={len(quantities)}",
            flush=True,
        )

        right_sizing = _build_right_sizing_recommendations(shipments, quantities, vehicle_types)
        consolidation = _build_consolidation_recommendations(shipments, quantities, vehicle_types)
        all_recommendations = right_sizing + consolidation
        print(
            f"n_right_sizing_recommendations={len(right_sizing)} "
            f"n_consolidation_recommendations={len(consolidation)}",
            flush=True,
        )

        # Recommendation consistency: apply_scenario-style pure functions
        # (no RNG, no hidden state) -- re-running against the same inputs
        # must reproduce identical results.
        right_sizing_2 = _build_right_sizing_recommendations(shipments, quantities, vehicle_types)
        if [r["rec"] for r in right_sizing] != [r["rec"] for r in right_sizing_2]:
            print(
                "VALIDATION_FAILURE: right-sizing recommendations are not deterministic", flush=True
            )
            print("status=FAILED", flush=True)
            raise SystemExit(1)
        print("recommendation_consistency_check=PASSED", flush=True)

        _validate_feasibility(all_recommendations, vehicle_types)
        _validate_cost_reconciliation(all_recommendations)
        _validate_explainability(all_recommendations)

        model_id = _get_or_create_model(conn)
        print(f"model_id={model_id}", flush=True)

        n_persisted = _persist(conn, all_recommendations, model_id, etl_run_id)
        conn.commit()

        total_savings = sum(r["rec"].estimated_savings for r in all_recommendations)
        print(
            f"recommendations_persisted={n_persisted} total_estimated_savings={total_savings:.2f}",
            flush=True,
        )
        print(f"timing total_seconds={time.perf_counter() - t0:.1f}", flush=True)

    print("status=SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()
