"""Parsing helpers for values coming out of etl_extract_staging.payload
— a JSON snapshot, so dates/datetimes/decimals round-trip as strings
(see etl/extract/staging.py's _json_default) and need converting back
to real Python types before use in transform logic or DB writes.
"""

from datetime import date, datetime
from decimal import Decimal


def parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value[:10])


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def parse_decimal(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
