"""DB-backed Stage B tests: SCD2 versioning against the real
upsert_scd2_dimension load path, date-based surrogate key resolution,
reconciliation, and idempotent reruns — against the real (test) OLAP
schema, not mocks.

These construct candidates directly via the transform builders and load
them straight into dim_supplier/dim_warehouse, bypassing a full Stage A
extraction round-trip: what's under test here is the load/resolve layer
(etl/load/dimensions.py, etl/transform/surrogate_keys.py), not
extraction, so there's no need to pay for a real OLTP round-trip to
exercise it. test_pipeline_integration.py already covers Stage A's own
extraction correctness end-to-end.
"""

from datetime import date

from sqlalchemy import text

from etl.load.dimensions import LoadCounts, upsert_scd2_dimension, upsert_type1_dimension
from etl.reconcile import reconcile_fact
from etl.transform.dimensions import build_dim_region_rows, build_scd2_supplier_candidates
from etl.transform.surrogate_keys import resolve_scd2_as_of, resolve_type1

_SCD2_EPOCH = date(2000, 1, 1)


def _supplier_staged(source_id=1, updated_at="2021-01-05T12:00:00", payment_terms_days=30, **overrides):
    row = {
        "source_id": source_id,
        "supplier_code": f"SUP-{source_id}",
        "name": "Acme",
        "contact_email": "a@example.com",
        "contact_phone": None,
        "address_line1": None,
        "city": None,
        "state_province": None,
        "postal_code": None,
        "country": None,
        "payment_terms_days": payment_terms_days,
        "default_lead_time_days": 7,
        "is_active": 1,
        "updated_at": updated_at,
    }
    row.update(overrides)
    return row


def test_scd2_first_version_uses_epoch_sentinel_not_source_updated_at(olap_engine):
    """The real bug found against production-scale data: a dimension's
    very first version can't be dated to source updated_at, because in
    this dataset that column reflects data-generation wall-clock time
    (e.g. 2026), not simulated business time (2021 onward) — dating v1
    to it makes it unresolvable against any earlier fact business date.
    See ADR-016's addendum."""

    candidates = build_scd2_supplier_candidates([_supplier_staged(updated_at="2026-08-08T20:12:30")])

    with olap_engine.connect() as conn:
        with conn.begin():
            counts = upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", ("payment_terms_days", "default_lead_time_days"), candidates
            )
        row = conn.execute(
            text("SELECT effective_from, effective_to, is_current FROM dim_supplier WHERE supplier_id = 1")
        ).one()

    assert counts == LoadCounts(1, 0, 0)
    assert row.effective_from == _SCD2_EPOCH
    assert row.effective_to is None
    assert row.is_current == 1


def test_scd2_genuine_tracked_change_versions_and_resolves_by_business_date(olap_engine):
    tracked = ("payment_terms_days", "default_lead_time_days")

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=30, updated_at="2021-01-05T00:00:00")]),
            )
        with conn.begin():
            counts = upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=45, updated_at="2021-06-01T00:00:00")]),
            )
        versions = conn.execute(
            text(
                "SELECT supplier_key, payment_terms_days, effective_from, effective_to, is_current "
                "FROM dim_supplier WHERE supplier_id = 1 ORDER BY effective_from"
            )
        ).all()

        assert counts == LoadCounts(1, 0, 0)  # a new version, not an update-in-place
        assert len(versions) == 2
        v1, v2 = versions
        assert v1.effective_from == _SCD2_EPOCH
        assert v1.effective_to == date(2021, 6, 1)
        assert v1.is_current == 0
        assert v1.payment_terms_days == 30
        assert v2.effective_from == date(2021, 6, 1)
        assert v2.effective_to is None
        assert v2.is_current == 1
        assert v2.payment_terms_days == 45

        # ADR-021: resolution is as-of the fact's own business date, not
        # unconditionally the current version.
        resolved = resolve_scd2_as_of(
            conn, "dim_supplier", "supplier_id",
            [(101, 1, date(2021, 3, 1)), (102, 1, date(2021, 6, 1)), (103, 1, date(2021, 12, 1))],
        )

    assert resolved[101] == v1.supplier_key  # before the change
    assert resolved[102] == v2.supplier_key  # exactly on the new effective_from
    assert resolved[103] == v2.supplier_key  # well after the change


def test_scd2_same_day_change_coalesces_into_one_version(olap_engine):
    tracked = ("payment_terms_days", "default_lead_time_days")

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=30, updated_at="2021-06-01T08:00:00")]),
            )
        with conn.begin():
            counts_v2 = upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=45, updated_at="2021-06-01T09:00:00")]),
            )
        with conn.begin():
            # A second real change on the SAME calendar day (e.g. Stage B
            # ran twice in one day and both caught a genuine change).
            counts_v3 = upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=60, updated_at="2021-06-01T17:00:00")]),
            )
        rows = conn.execute(
            text(
                "SELECT payment_terms_days, effective_from, is_current FROM dim_supplier "
                "WHERE supplier_id = 1 ORDER BY effective_from"
            )
        ).all()

    assert counts_v2 == LoadCounts(1, 0, 0)  # v1 (epoch) -> v2 (2021-06-01): a real new version
    assert counts_v3 == LoadCounts(0, 1, 0)  # v3 coalesces into v2 in place, not a 3rd version
    assert len(rows) == 2  # v1 stays as closed history; v3 didn't add a row beyond v2
    v1, v2 = rows
    assert v1.payment_terms_days == 30 and v1.effective_from == _SCD2_EPOCH and v1.is_current == 0
    assert v2.payment_terms_days == 60  # latest same-day state wins after coalescing v3 into v2
    assert v2.effective_from == date(2021, 6, 1) and v2.is_current == 1


def test_scd2_non_tracked_change_updates_in_place_no_new_version(olap_engine):
    tracked = ("payment_terms_days", "default_lead_time_days")

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(updated_at="2021-01-05T00:00:00")]),
            )
        with conn.begin():
            counts = upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates(
                    [_supplier_staged(updated_at="2021-06-01T00:00:00", contact_email="new@example.com")]
                ),
            )
        rows = conn.execute(
            text("SELECT contact_email, effective_from, is_current FROM dim_supplier WHERE supplier_id = 1")
        ).all()

    assert counts == LoadCounts(0, 1, 0)
    assert len(rows) == 1  # no new version — a non-tracked attribute isn't a real SCD2 event
    assert rows[0].contact_email == "new@example.com"
    assert rows[0].effective_from == _SCD2_EPOCH  # unchanged
    assert rows[0].is_current == 1


def test_scd2_unchanged_candidate_is_a_true_noop(olap_engine):
    tracked = ("payment_terms_days", "default_lead_time_days")
    candidates = build_scd2_supplier_candidates([_supplier_staged(updated_at="2021-01-05T00:00:00")])

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_scd2_dimension(conn, "dim_supplier", "supplier_id", tracked, candidates)
        with conn.begin():
            counts = upsert_scd2_dimension(conn, "dim_supplier", "supplier_id", tracked, candidates)
        row_count = conn.execute(text("SELECT COUNT(*) FROM dim_supplier")).scalar_one()

    assert counts == LoadCounts(0, 0, 1)
    assert row_count == 1


def test_resolve_type1_maps_natural_id_to_surrogate_key(olap_engine):
    staged = [
        {"source_id": 1, "code": "NA", "name": "North America", "updated_at": "2021-01-01T00:00:00"},
        {"source_id": 2, "code": "EU", "name": "Europe", "updated_at": "2021-01-01T00:00:00"},
    ]

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_type1_dimension(conn, "dim_region", "region_id", build_dim_region_rows(staged))
        resolved = resolve_type1(conn, "dim_region", "region_id")

    assert set(resolved.keys()) == {1, 2}
    assert isinstance(resolved[1], int) and isinstance(resolved[2], int)
    assert resolved[1] != resolved[2]


def test_reconcile_fact_flags_row_count_mismatch(olap_engine):
    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_type1_dimension(
                conn, "dim_region", "region_id",
                build_dim_region_rows([{"source_id": 1, "code": "NA", "name": "NA", "updated_at": "2021-01-01T00:00:00"}]),
            )
        matching = reconcile_fact(conn, "dim_region", ("region_id",), expected_count=1)
        mismatched = reconcile_fact(conn, "dim_region", ("region_id",), expected_count=99)

    assert matching.row_count_matches is True
    assert matching.grain_violations == 0
    assert mismatched.row_count_matches is False
    assert mismatched.row_count == 1
    assert mismatched.expected_count == 99


def test_reconcile_fact_detects_grain_violation_via_group_by(olap_engine):
    """dim_supplier's real DB-level UNIQUE constraint is on
    (supplier_id, effective_from), not supplier_id alone — so two
    genuinely valid SCD2 versions of the same supplier (different
    effective_from, both legally inserted through the normal load path)
    legitimately share a supplier_id. Calling reconcile_fact with just
    ("supplier_id",) as the grain — the wrong grain for this table, but
    exactly the kind of transform bug ADR-... reconcile_fact's grain
    check exists to catch — lets this test exercise the real GROUP BY/
    HAVING logic against real, validly-inserted rows, without needing to
    bypass any constraint."""

    tracked = ("payment_terms_days", "default_lead_time_days")
    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=30, updated_at="2021-01-05T00:00:00")]),
            )
        with conn.begin():
            upsert_scd2_dimension(
                conn, "dim_supplier", "supplier_id", tracked,
                build_scd2_supplier_candidates([_supplier_staged(payment_terms_days=45, updated_at="2021-06-01T00:00:00")]),
            )
        result = reconcile_fact(conn, "dim_supplier", ("supplier_id",), expected_count=2)

    assert result.row_count == 2
    assert result.grain_violations == 1


def test_idempotent_rerun_of_scd2_and_type1_loads_produces_no_new_rows(olap_engine):
    region_staged = [{"source_id": 1, "code": "NA", "name": "NA", "updated_at": "2021-01-01T00:00:00"}]
    supplier_candidates = build_scd2_supplier_candidates([_supplier_staged(updated_at="2021-01-05T00:00:00")])
    tracked = ("payment_terms_days", "default_lead_time_days")

    with olap_engine.connect() as conn:
        with conn.begin():
            upsert_type1_dimension(conn, "dim_region", "region_id", build_dim_region_rows(region_staged))
            upsert_scd2_dimension(conn, "dim_supplier", "supplier_id", tracked, supplier_candidates)

        with conn.begin():
            region_counts = upsert_type1_dimension(conn, "dim_region", "region_id", build_dim_region_rows(region_staged))
            supplier_counts = upsert_scd2_dimension(conn, "dim_supplier", "supplier_id", tracked, supplier_candidates)

        region_rows = conn.execute(text("SELECT COUNT(*) FROM dim_region")).scalar_one()
        supplier_rows = conn.execute(text("SELECT COUNT(*) FROM dim_supplier")).scalar_one()

    assert region_counts == LoadCounts(0, 0, 1)
    assert supplier_counts == LoadCounts(0, 0, 1)
    assert region_rows == 1
    assert supplier_rows == 1
