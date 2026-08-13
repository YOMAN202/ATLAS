"""Module C entrypoint: load supplier feature views, score every
supplier, validate the scores behave as designed, register the scoring
formula in ds_model_registry (the same registry Module A's forecasting
models use — "model" here means a named, versioned formula, not a
forecasting-specific concept), and persist to ds_supplier_risk_score.

Run as: python -m app.decision_support.run_module_c
"""

import json
import time
from datetime import UTC, datetime

from sqlalchemy import text

from app.api.deps import get_current_etl_run_id
from app.decision_support.db import get_engine
from app.decision_support.supplier_scoring import (
    SCORING_PARAMETERS,
    SupplierMetrics,
    score_suppliers,
)
from app.decision_support.supplier_validation import (
    assert_scores_behave_as_designed,
    validate_scores,
)


def _load_supplier_metrics(conn) -> list[SupplierMetrics]:
    rows = conn.execute(
        text(
            "SELECT s.supplier_key, s.n_deliveries, s.on_time_rate, s.quality_rejection_rate, "
            "s.fill_rate, s.avg_lead_time_variance_days, s.lead_time_stddev_days, "
            "t.recent_on_time_rate, t.prior_on_time_rate, "
            "COALESCE(u.total_spend, 0) AS total_spend, "
            "COALESCE(u.share_of_total_spend, 0) AS share_of_total_spend, "
            "COALESCE(u.distinct_products_supplied, 0) AS distinct_products_supplied, "
            "COALESCE(u.distinct_warehouses_served, 0) AS distinct_warehouses_served "
            "FROM v_supplier_delivery_stats s "
            "JOIN v_supplier_trend t ON t.supplier_key = s.supplier_key "
            "LEFT JOIN v_supplier_utilization u ON u.supplier_key = s.supplier_key "
            "WHERE t.recent_on_time_rate IS NOT NULL AND t.prior_on_time_rate IS NOT NULL"
        )
    ).all()
    return [
        SupplierMetrics(
            supplier_key=r.supplier_key,
            n_deliveries=r.n_deliveries,
            on_time_rate=float(r.on_time_rate),
            quality_rejection_rate=float(r.quality_rejection_rate),
            fill_rate=float(r.fill_rate),
            avg_lead_time_variance_days=float(r.avg_lead_time_variance_days),
            lead_time_stddev_days=float(r.lead_time_stddev_days),
            recent_on_time_rate=float(r.recent_on_time_rate),
            prior_on_time_rate=float(r.prior_on_time_rate),
            total_spend=float(r.total_spend),
            share_of_total_spend=float(r.share_of_total_spend),
            distinct_products_supplied=r.distinct_products_supplied,
            distinct_warehouses_served=r.distinct_warehouses_served,
        )
        for r in rows
    ]


def _get_or_create_model(conn) -> int:
    params_json = json.dumps(SCORING_PARAMETERS, sort_keys=True)
    existing = conn.execute(
        text(
            "SELECT id FROM ds_model_registry WHERE module = 'supplier_risk_scoring' "
            "AND model_name = 'weighted_composite_v1' AND parameters = CAST(:params AS JSON)"
        ),
        {"params": params_json},
    ).scalar()
    if existing is not None:
        return existing
    result = conn.execute(
        text(
            "INSERT INTO ds_model_registry "
            "(module, model_name, parameters, is_active, created_at) "
            "VALUES ('supplier_risk_scoring', 'weighted_composite_v1', "
            "CAST(:params AS JSON), 1, :now)"
        ),
        {"params": params_json, "now": datetime.now(UTC)},
    )
    return result.lastrowid


def main() -> None:
    engine = get_engine()
    t0 = time.perf_counter()

    with engine.connect() as conn:
        etl_run_id = get_current_etl_run_id(conn)
        print(f"etl_run_id={etl_run_id}", flush=True)

        metrics = _load_supplier_metrics(conn)
        print(f"suppliers_loaded={len(metrics)}", flush=True)

        results = score_suppliers(metrics)
        validation = validate_scores(metrics, results)
        print(
            f"validation corr_on_time={validation.correlation_with_on_time_rate} "
            f"corr_quality={validation.correlation_with_quality_rejection_rate} "
            f"corr_variability={validation.correlation_with_lead_time_stddev} "
            f"corr_trend={validation.correlation_with_trend_delta}",
            flush=True,
        )
        print(
            f"classification n_low={validation.n_low} n_medium={validation.n_medium} "
            f"n_high={validation.n_high}",
            flush=True,
        )

        problems = assert_scores_behave_as_designed(validation)
        if problems:
            for p in problems:
                print(f"VALIDATION_FAILURE: {p}", flush=True)
            print("status=FAILED", flush=True)
            raise SystemExit(1)

        model_id = _get_or_create_model(conn)
        print(f"model_id={model_id}", flush=True)

        conn.execute(
            text("DELETE FROM ds_supplier_risk_score WHERE model_id = :model_id"),
            {"model_id": model_id},
        )

        by_key = {m.supplier_key: m for m in metrics}
        now = datetime.now(UTC)
        rows = [
            {
                "supplier_key": r.supplier_key,
                "risk_score": r.risk_score,
                "risk_classification": r.risk_classification,
                "on_time_rate": by_key[r.supplier_key].on_time_rate,
                "quality_rejection_rate": by_key[r.supplier_key].quality_rejection_rate,
                "fill_rate": by_key[r.supplier_key].fill_rate,
                "avg_lead_time_variance_days": by_key[r.supplier_key].avg_lead_time_variance_days,
                "lead_time_stddev_days": by_key[r.supplier_key].lead_time_stddev_days,
                "on_time_rate_trend_delta": r.on_time_rate_trend_delta,
                "trend_direction": r.trend_direction,
                "total_spend": by_key[r.supplier_key].total_spend,
                "share_of_total_spend": by_key[r.supplier_key].share_of_total_spend,
                "distinct_products_supplied": by_key[r.supplier_key].distinct_products_supplied,
                "distinct_warehouses_served": by_key[r.supplier_key].distinct_warehouses_served,
                "n_deliveries": by_key[r.supplier_key].n_deliveries,
                "triggering_metrics": json.dumps(r.triggering_metrics),
                "model_id": model_id,
                "etl_run_id": etl_run_id,
                "generated_at": now,
            }
            for r in results
        ]
        conn.execute(
            text(
                "INSERT INTO ds_supplier_risk_score "
                "(supplier_key, risk_score, risk_classification, on_time_rate, "
                "quality_rejection_rate, "
                "fill_rate, avg_lead_time_variance_days, lead_time_stddev_days, "
                "on_time_rate_trend_delta, "
                "trend_direction, total_spend, share_of_total_spend, distinct_products_supplied, "
                "distinct_warehouses_served, n_deliveries, triggering_metrics, model_id, "
                "etl_run_id, "
                "generated_at) "
                "VALUES (:supplier_key, :risk_score, :risk_classification, :on_time_rate, "
                ":quality_rejection_rate, :fill_rate, :avg_lead_time_variance_days, "
                ":lead_time_stddev_days, :on_time_rate_trend_delta, :trend_direction, "
                ":total_spend, "
                ":share_of_total_spend, :distinct_products_supplied, :distinct_warehouses_served, "
                ":n_deliveries, CAST(:triggering_metrics AS JSON), :model_id, :etl_run_id, "
                ":generated_at)"
            ),
            rows,
        )
        conn.commit()

        print(f"scores_persisted={len(rows)}", flush=True)
        print(f"timing total_seconds={time.perf_counter() - t0:.1f}", flush=True)

    print("status=SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()
