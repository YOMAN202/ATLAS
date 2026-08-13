"""Module A entrypoint: register models, backtest, select the winner,
generate and persist forecasts for every qualifying series across all
three grains. Prints a structured summary to stdout (redirected to a
log file when run detached) — this is what docs/phase7-module-a-
completion.md's evaluation numbers are drawn from directly, not a
separately hand-typed report.

Run as: python -m app.decision_support.run_module_a
"""

import time

from app.api.deps import get_current_etl_run_id
from app.decision_support.db import get_engine
from app.decision_support.forecasting import (
    FORECAST_HORIZON_DAYS,
    MIN_ACTIVE_DAYS,
    run_backtests,
    select_backtest_sample,
    select_best_model,
)
from app.decision_support.models import MODEL_SPECS
from app.decision_support.persist import mark_active_model, persist_forecasts
from app.decision_support.series import (
    load_category_series,
    load_region_series,
    load_sku_warehouse_series,
)


def main() -> None:
    engine = get_engine()
    t0 = time.perf_counter()

    with engine.connect() as conn:
        # One transaction for this whole run (SQLAlchemy 2.0 "autobegin":
        # the first execute() below opens it implicitly) — backtest
        # writes and forecast writes commit together at the end, or not
        # at all if anything raises.
        etl_run_id = get_current_etl_run_id(conn)
        print(f"etl_run_id={etl_run_id}", flush=True)

        print("Loading feature-layer series...", flush=True)
        sku_series = load_sku_warehouse_series(conn, min_active_days=MIN_ACTIVE_DAYS)
        category_series = load_category_series(conn, min_active_days=MIN_ACTIVE_DAYS)
        region_series = load_region_series(conn)
        print(
            f"series_loaded sku_warehouse={len(sku_series)} category={len(category_series)} "
            f"region={len(region_series)}",
            flush=True,
        )

        sku_sample = select_backtest_sample(sku_series, n=20)
        print(
            f"backtest_sample sku_warehouse_n={len(sku_sample)} region_n={len(region_series)}",
            flush=True,
        )

        t_backtest = time.perf_counter()
        backtest_results = run_backtests(conn, region_series, sku_sample)
        backtest_seconds = time.perf_counter() - t_backtest

        for model_name, data in backtest_results.items():
            points = data["mape_points"]
            if points:
                avg = sum(m * n for m, n, _ in points) / sum(n for _, n, _ in points)
                print(
                    f"model={model_name} model_id={data['model_id']} "
                    f"weighted_avg_mape={avg:.2f} n_series_scored={len(points)}",
                    flush=True,
                )
            else:
                print(
                    f"model={model_name} model_id={data['model_id']} no_scoreable_series",
                    flush=True,
                )

        best_name, best_model_id, best_mape = select_best_model(backtest_results)
        print(
            f"selected_model={best_name} model_id={best_model_id} "
            f"weighted_avg_mape={best_mape:.2f}",
            flush=True,
        )
        mark_active_model(conn, "demand_forecasting", best_model_id)

        best_params = next(params for name, params, _ in MODEL_SPECS if name == best_name)
        best_fn = next(fn for name, _, fn in MODEL_SPECS if name == best_name)

        t_persist = time.perf_counter()
        n_sku = persist_forecasts(
            conn,
            "sku_warehouse",
            sku_series,
            best_fn,
            best_params,
            best_model_id,
            etl_run_id,
            FORECAST_HORIZON_DAYS,
        )
        n_cat = persist_forecasts(
            conn,
            "category",
            category_series,
            best_fn,
            best_params,
            best_model_id,
            etl_run_id,
            FORECAST_HORIZON_DAYS,
        )
        n_reg = persist_forecasts(
            conn,
            "region",
            region_series,
            best_fn,
            best_params,
            best_model_id,
            etl_run_id,
            FORECAST_HORIZON_DAYS,
        )
        persist_seconds = time.perf_counter() - t_persist

        conn.commit()

        print(
            f"forecasts_persisted sku_warehouse={n_sku} category={n_cat} region={n_reg} "
            f"total={n_sku + n_cat + n_reg}",
            flush=True,
        )
        print(
            f"timing backtest_seconds={backtest_seconds:.1f} persist_seconds={persist_seconds:.1f} "
            f"total_seconds={time.perf_counter() - t0:.1f}",
            flush=True,
        )

    print("status=SUCCEEDED", flush=True)


if __name__ == "__main__":
    main()
