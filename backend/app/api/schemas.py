"""Shared response shapes across every dashboard endpoint. Per-dashboard
KPI/row shapes live in their own router module (backend/app/api/v1/*.py)
next to the query that produces them — locality over a single giant
schema file, since each dashboard's shape only has one caller.
"""

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageEnvelope(BaseModel, Generic[T]):
    """Standard shape for every paginated drill-down/detail endpoint —
    TanStack Table on the frontend expects this uniformly (per
    docs/phase6-dashboard-proposal.md §3)."""

    data: list[T]
    page: int
    page_size: int
    total: int


class AsOf(BaseModel):
    """Every dashboard/KPI response embeds this so the frontend can show
    "as of ETL run #N" rather than implying live/real-time data — this is
    a batch-analytics system (ATLAS-TDD.md §8)."""

    etl_run_id: int
    date_from: date | None
    date_to: date | None
