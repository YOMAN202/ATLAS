"""Shared date/time helpers used across generators."""

from datetime import date, datetime


def as_datetime(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)
