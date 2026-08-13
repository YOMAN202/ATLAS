"""Proves the Executive dashboard's arithmetic against known, hand-seeded
warehouse data — the same reconciliation property
docs/phase5-validation.md proved by hand against the real dataset,
proved here as an automated, repeatable test.
"""

from sqlalchemy import text

from app.core.security import ADMINISTRATOR, EXECUTIVE, OPERATIONS_ANALYST


def _seed(olap_engine) -> None:
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_region "
                    "(region_id, region_code, region_name, source_updated_at) "
                    "VALUES (1, 'NA', 'North America', NOW())"
                )
            )
            region_key = conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = 1")
            ).scalar_one()

            conn.execute(
                text(
                    "INSERT INTO dim_product (product_id, sku, product_name, unit_of_measure, "
                    "current_unit_cost, current_unit_price, is_active, source_updated_at) "
                    "VALUES (1, 'SKU-1', 'Widget', 'EA', 10.00, 20.00, 1, NOW())"
                )
            )
            product_key = conn.execute(
                text("SELECT product_key FROM dim_product WHERE product_id = 1")
            ).scalar_one()

            conn.execute(
                text(
                    "INSERT INTO dim_customer "
                    "(customer_id, customer_code, customer_name, region_key, source_updated_at) "
                    "VALUES (1, 'CUST-1', 'Acme', :region_key, NOW())"
                ),
                {"region_key": region_key},
            )
            customer_key = conn.execute(
                text("SELECT customer_key FROM dim_customer WHERE customer_id = 1")
            ).scalar_one()

            conn.execute(
                text(
                    "INSERT INTO summary_daily_revenue_by_region "
                    "(region_key, date_key, total_orders, total_order_lines, "
                    "total_revenue, total_gross_margin) "
                    "VALUES (:rk, 20210101, 2, 3, 300.00, 100.00), "
                    "(:rk, 20210102, 1, 1, 150.00, 50.00)"
                ),
                {"rk": region_key},
            )

            conn.execute(
                text(
                    "INSERT INTO fact_orders "
                    "(source_order_line_id, order_number, order_line_number, "
                    "order_date_key, product_key, customer_key, ordered_quantity, "
                    "allocated_quantity, backordered_quantity, unit_price, unit_cost, "
                    "extended_revenue, extended_cost, gross_margin) "
                    "VALUES "
                    "(1, 'ORD-1', 1, 20210101, :pk, :ck, 10, 10, 0, 20.00, 10.00, "
                    "200.00, 100.00, 100.00), "
                    "(2, 'ORD-2', 1, 20210102, :pk, :ck, 10, 5, 5, 20.00, 10.00, "
                    "100.00, 50.00, 50.00)"
                ),
                {"pk": product_key, "ck": customer_key},
            )


def test_executive_summary_reconciles_to_seeded_totals(client, olap_engine, seed_run):
    _seed(olap_engine)

    resp = client.get("/api/v1/dashboards/executive", headers={"X-Atlas-Role": "executive"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_revenue"] == 450.00  # 300.00 + 150.00, from summary table
    assert body["total_gross_margin"] == 150.00  # 100.00 + 50.00
    assert body["total_orders"] == 3
    assert body["total_order_lines"] == 4
    assert (
        body["order_fulfillment_rate"] == 0.75
    )  # (10 + 5) allocated / (10 + 10) ordered, from fact_orders
    assert body["cost_to_serve"] is None  # never computed — no invented formula
    assert body["as_of"]["etl_run_id"] == seed_run
    assert len(body["daily_trend"]) == 2


def test_executive_summary_region_filter_isolates_one_regions_totals(client, olap_engine, seed_run):
    _seed(olap_engine)
    with olap_engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text(
                    "INSERT INTO dim_region "
                    "(region_id, region_code, region_name, source_updated_at) "
                    "VALUES (2, 'EU', 'Europe', NOW())"
                )
            )
            other_region_key = conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = 2")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO summary_daily_revenue_by_region "
                    "(region_key, date_key, total_orders, total_order_lines, "
                    "total_revenue, total_gross_margin) "
                    "VALUES (:rk, 20210101, 99, 99, 9999.00, 9999.00)"
                ),
                {"rk": other_region_key},
            )
            na_region_key = conn.execute(
                text("SELECT region_key FROM dim_region WHERE region_id = 1")
            ).scalar_one()

    resp = client.get(
        "/api/v1/dashboards/executive",
        params={"region_key": na_region_key},
        headers={"X-Atlas-Role": "executive"},
    )

    assert resp.status_code == 200
    assert resp.json()["total_revenue"] == 450.00  # unaffected by the EU region's seeded data


def test_executive_dashboard_rejects_disallowed_role(client, seed_run):
    resp = client.get("/api/v1/dashboards/executive", headers={"X-Atlas-Role": OPERATIONS_ANALYST})
    assert resp.status_code == 403


def test_executive_dashboard_allows_administrator(client, seed_run):
    resp = client.get("/api/v1/dashboards/executive", headers={"X-Atlas-Role": ADMINISTRATOR})
    assert resp.status_code == 200


def test_executive_dashboard_requires_role_header(client, seed_run):
    resp = client.get("/api/v1/dashboards/executive")
    assert resp.status_code == 422  # FastAPI's own required-header validation


def test_executive_dashboard_503s_with_no_successful_run(client):
    resp = client.get("/api/v1/dashboards/executive", headers={"X-Atlas-Role": EXECUTIVE})
    assert resp.status_code == 503
