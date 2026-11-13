"""Shared UTC clock for persistence and application services."""
import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
