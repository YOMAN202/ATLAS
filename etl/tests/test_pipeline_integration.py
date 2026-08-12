"""End-to-end Stage A pipeline tests: extraction through staging/
quarantine/watermark/audit, against the real (test) OLTP and OLAP
schemas — not mocks.

products.unit_cost is used for the genuine bad-data (DQ-5) case because
it is one of the few columns atlas_oltp does not already constrain at
the DB level (no CHECK on unit_cost) — see test_dq_rules_unit.py's
module docstring for why most other rules can't be exercised this way.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from etl import pipeline
from etl.extract.registry import REGISTRY


def test_happy_path_extracts_and_stages_valid_rows(oltp_engine, olap_engine, master_data):
    etl_run_id = pipeline.run()

    with olap_engine.connect() as conn:
        staged = conn.execute(
            text(
                "SELECT source_table, source_id FROM etl_extract_staging "
                "WHERE source_table = 'products'"
            )
        ).all()
        run_status = conn.execute(
            text("SELECT status FROM etl_run_log WHERE id = :id"), {"id": etl_run_id}
        ).scalar_one()

    assert run_status == "SUCCEEDED"
    assert (master_data["product"].id,) in [(s[1],) for s in staged]


def test_negative_unit_cost_is_quarantined_end_to_end(oltp_engine, olap_engine, master_data):
    with oltp_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO products (sku, name, unit_of_measure, unit_cost, unit_price, "
                    "is_active) VALUES ('SKU-BAD', 'Bad Product', 'EA', -5.00, 10.00, 1)"
                )
            )
            bad_product_id = result.lastrowid

    pipeline.run()

    with olap_engine.connect() as conn:
        quarantine_rows = conn.execute(
            text(
                "SELECT rule_violated, rule_detail FROM dq_quarantine "
                "WHERE source_table = 'products' AND source_id = :id"
            ),
            {"id": bad_product_id},
        ).all()
        staged = conn.execute(
            text(
                "SELECT 1 FROM etl_extract_staging "
                "WHERE source_table = 'products' AND source_id = :id"
            ),
            {"id": bad_product_id},
        ).all()

    assert any(rule == "DQ-5" for rule, _ in quarantine_rows)
    assert staged == []  # a quarantined row must never also be staged


def test_no_change_rerun_extracts_zero_additional_rows(oltp_engine, olap_engine, master_data):
    first_run_id = pipeline.run()
    second_run_id = pipeline.run()

    with olap_engine.connect() as conn:
        second_run_extracted = conn.execute(
            text(
                "SELECT COALESCE(SUM(extracted_count), 0) FROM etl_run_table_metrics "
                "WHERE etl_run_id = :id"
            ),
            {"id": second_run_id},
        ).scalar_one()
        first_run_extracted = conn.execute(
            text(
                "SELECT COALESCE(SUM(extracted_count), 0) FROM etl_run_table_metrics "
                "WHERE etl_run_id = :id"
            ),
            {"id": first_run_id},
        ).scalar_one()

    assert first_run_extracted > 0  # sanity: the first run actually extracted the seed data
    assert second_run_extracted == 0  # ADR-017: nothing new, watermark already reflects everything


def test_watermark_advances_to_max_updated_at_of_seeded_data(oltp_engine, olap_engine, master_data):
    pipeline.run()

    with oltp_engine.connect() as conn:
        max_product_updated_at = conn.execute(
            text("SELECT MAX(updated_at) FROM products")
        ).scalar_one()

    with olap_engine.connect() as conn:
        watermark = conn.execute(
            text("SELECT last_extracted_at FROM etl_watermark WHERE source_table = 'products'")
        ).scalar_one()

    assert watermark == max_product_updated_at


def test_quarantine_revalidation_is_idempotent_not_duplicated(
    oltp_engine, olap_engine, master_data
):
    with oltp_engine.connect() as conn:
        with conn.begin():
            result = conn.execute(
                text(
                    "INSERT INTO products (sku, name, unit_of_measure, unit_cost, unit_price, "
                    "is_active) VALUES ('SKU-BAD2', 'Bad Product 2', 'EA', -1.00, 10.00, 1)"
                )
            )
            bad_id = result.lastrowid

    pipeline.run()

    # Simulate the same underlying problem surfacing again on a later day
    # (source row touched again, bumping updated_at past the watermark)
    # so it is genuinely re-extracted and re-validated, not just re-read
    # from a cache.
    with oltp_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text("UPDATE products SET updated_at = :ts WHERE id = :id"),
                {"ts": datetime.now(UTC) + timedelta(seconds=5), "id": bad_id},
            )

    pipeline.run()

    with olap_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM dq_quarantine "
                "WHERE source_table = 'products' AND source_id = :id AND rule_violated = 'DQ-5'"
            ),
            {"id": bad_id},
        ).scalar_one()

    assert count == 1  # upserted, not duplicated


def test_registry_covers_every_table_without_error(oltp_engine, olap_engine, master_data):
    """Sanity check that every registered table extracts/validates
    without raising, including tables with zero rows (e.g. shipments,
    returns) — an empty batch must be a clean no-op, not an error."""

    etl_run_id = pipeline.run()

    with olap_engine.connect() as conn:
        tables_with_metrics = {
            row[0]
            for row in conn.execute(
                text("SELECT source_table FROM etl_run_table_metrics WHERE etl_run_id = :id"),
                {"id": etl_run_id},
            ).all()
        }

    assert tables_with_metrics == {spec.name for spec in REGISTRY}
