"""Applies every etl/warehouse_ddl/NN_*.sql file, in ascending numeric
order, to the target OLAP schema.

Shells out to the `mysql` CLI (subprocess) rather than hand-splitting
multi-statement .sql files in Python — same pattern
backend/tests/conftest.py uses for `alembic`, chosen for the same reason:
01_dim_date.sql contains a recursive CTE, and a real SQL client is
simplest and most robust for that, not a hand-rolled statement splitter.

Target schema: TEST_DATABASE_URL_OLAP env var if set (used by
warehouse_ddl/tests/conftest.py against atlas_olap_test), otherwise
app.core.config.settings.database_url_olap (dev atlas_olap) — same
override pattern already used for OLTP (TEST_DATABASE_URL_OLTP).
"""

import os
import subprocess
from pathlib import Path

from app.core.config import settings
from sqlalchemy.engine import make_url

DDL_DIR = Path(__file__).parent


def _target_url() -> str:
    return os.environ.get("TEST_DATABASE_URL_OLAP", settings.database_url_olap)


def _mysql_cmd_and_env(url: str) -> tuple[list[str], dict]:
    parsed = make_url(url)
    env = os.environ.copy()
    if parsed.password:
        env["MYSQL_PWD"] = parsed.password  # avoids a plaintext -p flag showing in `ps`
    cmd = [
        "mysql",
        "-h", parsed.host,
        "-P", str(parsed.port or 3306),
        "-u", parsed.username,
        parsed.database,
    ]  # fmt: skip
    return cmd, env


def _run_sql_file(cmd: list[str], env: dict, sql_path: Path) -> None:
    with sql_path.open("rb") as f:
        result = subprocess.run(cmd, stdin=f, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Applying {sql_path.name} failed:\n{result.stderr.decode(errors='replace')}"
        )


def apply_all(url: str | None = None) -> int:
    url = url or _target_url()
    cmd, env = _mysql_cmd_and_env(url)
    sql_files = sorted(DDL_DIR.glob("[0-9][0-9]_*.sql"))
    for sql_path in sql_files:
        print(f"Applying {sql_path.name}...", flush=True)
        _run_sql_file(cmd, env, sql_path)
    print(f"Applied {len(sql_files)} DDL files.", flush=True)
    return len(sql_files)


if __name__ == "__main__":
    apply_all()
