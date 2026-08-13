"""Roadmap Phase 4 Testing Requirement: "DDL apply/teardown tested in CI."
Proves teardown -> teardown-again (idempotent no-op) -> apply is clean
and produces exactly the expected object count — the same up/down/up
shape the backend CI job runs for Alembic (see .github/workflows/ci.yml).
"""

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apply_ddl import apply_all  # noqa: E402
from teardown_ddl import teardown_all  # noqa: E402

# 7 dimensions + 6 facts + 1 summary table (Phase 4) + 5 ETL process
# metadata tables (Phase 5 Stage A: etl_run_log, etl_watermark,
# etl_extract_staging, dq_quarantine, etl_run_table_metrics — ADR-015)
# + 3 Phase 7 Module A decision-support tables (ds_model_registry,
# ds_experiment_run, ds_demand_forecast — docs/phase7-architecture.md
# §5; the 3 feature views in that same DDL pass are VIEWs, not BASE
# TABLEs, so they don't count here).
# apply_ddl.py applies everything in warehouse_ddl/, so this count is the
# running total across phases, not Phase 4 alone. File count (25) exceeds
# table count (22) by 3, all pre-existing-pattern files that add no new
# BASE TABLE: 30_composite_indexes.sql (ALTER, indexes only, Phase 4),
# 45_etl_run_table_metrics_stage_timing.sql (ALTER, Phase 5), and the
# new 53_ds_feature_views.sql (3 VIEWs, Phase 7).
EXPECTED_TABLE_COUNT = 22
EXPECTED_DDL_FILE_COUNT = 25


def test_ddl_applies_cleanly_and_teardown_is_idempotent(engine):
    teardown_all()
    teardown_all()  # tearing down an already-empty schema must not error

    n_applied = apply_all()
    assert n_applied == EXPECTED_DDL_FILE_COUNT

    with engine.connect() as conn:
        table_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
            )
        ).scalar_one()
    assert table_count == EXPECTED_TABLE_COUNT


def test_dim_date_populated_across_full_source_data_range(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*), MIN(full_date), MAX(full_date) FROM dim_date")
        ).one()
    count, min_date, max_date = row
    assert count == 396
    assert str(min_date) == "2021-01-01"
    assert str(max_date) == "2022-01-31"
