"""Proves the Data Quality dashboard's score/rate arithmetic against
known, hand-seeded etl_run_table_metrics/dq_quarantine rows.
"""

import pytest
from sqlalchemy import text


def test_data_quality_summary_computes_scores_from_seeded_metrics(client, olap_engine, seed_run):
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO etl_run_table_metrics "
                    "(etl_run_id, source_table, extracted_count, inserted_count, updated_count, "
                    "unchanged_count, quarantined_count, rejected_count, duration_seconds, "
                    "rows_per_second) "
                    "VALUES "
                    "(:run_id, 'table_a', 100, 90, 0, 0, 10, 0, 10.5, 9.52), "
                    "(:run_id, 'table_b', 50, 45, 0, 0, 0, 5, 5.5, 9.09)"
                ),
                {"run_id": seed_run},
            )
            conn.execute(
                text(
                    "INSERT INTO dq_quarantine (etl_run_id, source_table, source_id, "
                    "rule_violated, rule_detail, raw_data, quarantined_at) VALUES "
                    "(:run_id, 'table_a', 1, 'DQ-3', 'unresolved fk', '{}', NOW()), "
                    "(:run_id, 'table_a', 2, 'DQ-3', 'unresolved fk', '{}', NOW()), "
                    "(:run_id, 'table_a', 3, 'DQ-3', 'unresolved fk', '{}', NOW()), "
                    "(:run_id, 'table_a', 4, 'DQ-1', 'null required column', '{}', NOW())"
                ),
                {"run_id": seed_run},
            )

    resp = client.get("/api/v1/dashboards/data-quality", headers={"X-Atlas-Role": "administrator"})

    assert resp.status_code == 200
    body = resp.json()
    # overall = (150 extracted - 10 quarantined - 5 rejected) / 150
    assert body["overall_dq_score"] == 0.9
    assert body["quarantine_rate"] == pytest.approx(10 / 150)
    # 3 DQ-3 entries / 150 total extracted
    assert body["referential_integrity_failure_rate"] == 0.02
    assert body["duration_seconds"] == 16.0  # 10.5 + 5.5, summed rather than trusting etl_run_log
    assert {row["source_table"]: row["dq_score"] for row in body["per_table"]} == {
        "table_a": 0.9,
        "table_b": 0.9,
    }


def test_data_quality_dashboard_rejects_supply_planner(client, seed_run):
    resp = client.get("/api/v1/dashboards/data-quality", headers={"X-Atlas-Role": "supply_planner"})
    assert resp.status_code == 403


def test_quarantine_detail_filters_by_rule(client, olap_engine, seed_run):
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dq_quarantine (etl_run_id, source_table, source_id, "
                    "rule_violated, rule_detail, raw_data, quarantined_at) VALUES "
                    "(:run_id, 'table_a', 1, 'DQ-3', 'x', '{}', NOW()), "
                    "(:run_id, 'table_a', 2, 'DQ-1', 'y', '{}', NOW())"
                ),
                {"run_id": seed_run},
            )

    resp = client.get(
        "/api/v1/dashboards/data-quality/quarantine",
        params={"rule_violated": "DQ-3"},
        headers={"X-Atlas-Role": "operations_analyst"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["data"][0]["rule_violated"] == "DQ-3"
