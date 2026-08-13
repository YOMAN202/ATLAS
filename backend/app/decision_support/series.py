"""Loads the feature-layer views (etl/warehouse_ddl/53_ds_feature_views.sql)
and turns their sparse rows into complete, gap-filled daily series —
every model in models.py requires no missing dates, since "no row" in
fact_orders means zero demand that day, not an unknown value.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass
class Series:
    key: tuple  # (product_key, warehouse_key) | (category,) | (region_key,)
    dates: list[date]
    values: list[float]


def _fill_gaps(rows: dict[date, float], start: date, end: date) -> tuple[list[date], list[float]]:
    dates, values = [], []
    d = start
    while d <= end:
        dates.append(d)
        values.append(rows.get(d, 0.0))
        d += timedelta(days=1)
    return dates, values


def _load(conn: Connection, view: str, key_columns: tuple[str, ...]) -> list[Series]:
    rows = conn.execute(
        text(
            f"SELECT {', '.join(key_columns)}, full_date, demand_quantity FROM {view} "
            "ORDER BY full_date"
        )
    ).all()
    if not rows:
        return []

    by_key: dict[tuple, dict[date, float]] = defaultdict(dict)
    all_dates: list[date] = []
    for row in rows:
        key = tuple(row[: len(key_columns)])
        by_key[key][row.full_date] = float(row.demand_quantity)
        all_dates.append(row.full_date)

    start, end = min(all_dates), max(all_dates)
    series = []
    for key, day_values in by_key.items():
        dates, values = _fill_gaps(day_values, start, end)
        series.append(Series(key=key, dates=dates, values=values))
    return series


def load_sku_warehouse_series(conn: Connection, min_active_days: int = 30) -> list[Series]:
    """One series per (product_key, warehouse_key). min_active_days
    filters out series too sparse to fit any of the models meaningfully
    (e.g. a product with 3 total orders in the year) — series shorter
    than this are skipped, not forecast with insufficient history
    silently presented as confident."""
    series = _load(conn, "v_daily_demand", ("product_key", "warehouse_key"))
    return [s for s in series if sum(1 for v in s.values if v > 0) >= min_active_days]


def load_category_series(conn: Connection, min_active_days: int = 30) -> list[Series]:
    series = _load(conn, "v_daily_demand_by_category", ("category",))
    return [s for s in series if sum(1 for v in s.values if v > 0) >= min_active_days]


def load_region_series(conn: Connection) -> list[Series]:
    return _load(conn, "v_daily_demand_by_region", ("region_key",))
