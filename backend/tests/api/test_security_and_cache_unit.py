"""Direct unit tests for require_role and the cache key function — pure
logic, no DB, no FastAPI app needed.
"""

import pytest
from fastapi import HTTPException

from app.api.cache import cache_key, get_cached, set_cached
from app.core.security import ADMINISTRATOR, EXECUTIVE, require_role


def test_require_role_accepts_an_allowed_role():
    dependency = require_role(EXECUTIVE, ADMINISTRATOR)
    assert dependency(x_atlas_role="executive") == "executive"


def test_require_role_is_case_insensitive():
    dependency = require_role(EXECUTIVE)
    assert dependency(x_atlas_role="Executive") == "executive"


def test_require_role_rejects_a_role_not_in_the_allowed_list():
    dependency = require_role(EXECUTIVE)
    with pytest.raises(HTTPException) as exc_info:
        dependency(x_atlas_role="supply_planner")
    assert exc_info.value.status_code == 403


def test_require_role_rejects_an_unknown_role_string():
    dependency = require_role(EXECUTIVE)
    with pytest.raises(HTTPException) as exc_info:
        dependency(x_atlas_role="not_a_real_role")
    assert exc_info.value.status_code == 401


def test_cache_key_changes_when_etl_run_id_changes():
    key_a = cache_key("executive", 1, region_key=None)
    key_b = cache_key("executive", 2, region_key=None)
    assert key_a != key_b


def test_cache_key_is_stable_regardless_of_kwarg_order():
    key_a = cache_key("executive", 1, region_key=5, date_from=None)
    key_b = cache_key("executive", 1, date_from=None, region_key=5)
    assert key_a == key_b


def test_cache_get_set_roundtrip():
    key = cache_key("test_route", 1)
    assert get_cached(key) is None
    set_cached(key, {"value": 42})
    assert get_cached(key) == {"value": 42}
