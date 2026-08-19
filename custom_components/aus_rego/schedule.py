"""Scheduling maths, kept free of Home Assistant imports so it can be tested."""

from __future__ import annotations

import hashlib
from datetime import date, time, timedelta


def parse_check_time(raw: str | time | None, default: time) -> time:
    """Parse ``HH:MM`` or ``HH:MM:SS`` into a :class:`~datetime.time`."""
    if isinstance(raw, time):
        return raw
    if not raw:
        return default
    parts = str(raw).strip().split(":")
    try:
        numbers = [int(part) for part in parts[:3]]
    except ValueError:
        return default
    while len(numbers) < 3:
        numbers.append(0)
    hour, minute, second = numbers
    if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
        return default
    return time(hour, minute, second)


def should_run_on(anchor: date, today: date, interval_days: int) -> bool:
    """Return True when a check is due today.

    ``interval_days`` of 1 means daily, 7 means weekly counted from ``anchor``.
    Dates before the anchor never run.
    """
    if interval_days <= 1:
        return today >= anchor
    delta = (today - anchor).days
    if delta < 0:
        return False
    return delta % interval_days == 0


def jitter_seconds(seed: str, max_seconds: int) -> int:
    """Return a stable per-vehicle offset within ``max_seconds``.

    Spreading requests keeps several vehicles — and several Home Assistant
    installations — from hitting a government site at the same instant. It is
    derived from the plate so it stays the same across restarts.
    """
    if max_seconds <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % (max_seconds + 1)


def next_run_date(
    anchor: date, today: date, interval_days: int, *, already_ran_today: bool
) -> date:
    """Return the next date a check is due."""
    if interval_days <= 1:
        return today if not already_ran_today and today >= anchor else _add(today, 1)
    if today < anchor:
        return anchor
    delta = (today - anchor).days
    if delta % interval_days == 0 and not already_ran_today:
        return today
    return _add(today, interval_days - (delta % interval_days))


def _add(value: date, days: int) -> date:
    """Return ``value`` shifted forward by ``days``."""
    return value + timedelta(days=days)
