"""Drops every warehouse object created by apply_ddl.py.

Explicit table list in reverse dependency order (facts/summary tables
before dimensions, since facts FK to dimensions) rather than DROP
DATABASE — this can run safely against a schema without assuming it
contains nothing else. FOREIGN_KEY_CHECKS is also disabled around the
drops as a defensive measure, since MySQL evaluates FKs at drop time too.
"""

import os
import subprocess

from app.core.config import settings
from sqlalchemy.engine import make_url

TABLES_IN_DROP_ORDER = [
    # ETL process metadata (Phase 5) — staging/quarantine/metrics FK to
    # etl_run_log, so they must go before it; etl_watermark has no FKs.
    "etl_run_table_metrics",
    "dq_quarantine",
    "etl_extract_staging",
    "etl_watermark",
    "etl_run_log",
    # Summary tables and facts next — they FK to dimensions.
    "summary_daily_revenue_by_region",
    "fact_returns",
    "fact_supplier_delivery",
    "fact_procurement",
    "fact_inventory_snapshot",
    "fact_shipments",
    "fact_orders",
    # Dimensions last, in reverse creation order (dim_customer/dim_warehouse
    # FK to dim_region, so they must go before it).
    "dim_customer",
    "dim_warehouse",
    "dim_supplier",
    "dim_carrier",
    "dim_product",
    "dim_region",
    "dim_date",
]


def _target_url() -> str:
    return os.environ.get("TEST_DATABASE_URL_OLAP", settings.database_url_olap)


def teardown_all(url: str | None = None) -> int:
    url = url or _target_url()
    parsed = make_url(url)
    env = os.environ.copy()
    if parsed.password:
        env["MYSQL_PWD"] = parsed.password
    cmd = [
        "mysql",
        "-h", parsed.host,
        "-P", str(parsed.port or 3306),
        "-u", parsed.username,
        parsed.database,
    ]  # fmt: skip

    sql = (
        "SET FOREIGN_KEY_CHECKS=0;\n"
        + "\n".join(f"DROP TABLE IF EXISTS {table};" for table in TABLES_IN_DROP_ORDER)
        + "\nSET FOREIGN_KEY_CHECKS=1;\n"
    )
    result = subprocess.run(cmd, input=sql.encode(), capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Teardown failed:\n{result.stderr.decode(errors='replace')}")
    print(f"Dropped {len(TABLES_IN_DROP_ORDER)} warehouse objects.", flush=True)
    return len(TABLES_IN_DROP_ORDER)


if __name__ == "__main__":
    teardown_all()
