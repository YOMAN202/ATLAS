"""Dashboard query cache, keyed to the current ETL run (§3 of
docs/phase6-dashboard-proposal.md). No TTL: correctness doesn't come
from an expiry timer, it comes from the cache key itself including the
current etl_run_id — once a new ETL run completes, every subsequent
request naturally misses the cache (a new key), and a stale run's
entries simply age out of the bounded LRU rather than needing explicit
invalidation. This is what makes NFR-10's 500ms cached-response target
achievable without ever serving data from an ETL run that's no longer
current.
"""

from typing import Any

from cachetools import LRUCache

_cache: LRUCache = LRUCache(maxsize=512)


def cache_key(route: str, etl_run_id: int, **params: Any) -> tuple:
    return (route, etl_run_id, tuple(sorted(params.items())))


def get_cached(key: tuple) -> Any | None:
    return _cache.get(key)


def set_cached(key: tuple, value: Any) -> None:
    _cache[key] = value
