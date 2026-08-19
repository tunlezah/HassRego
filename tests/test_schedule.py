"""Scheduling: "7am every day" and every variation of it."""

from __future__ import annotations

from datetime import date, time

import pytest
from aus_rego.schedule import (
    jitter_seconds,
    next_run_date,
    parse_check_time,
    should_run_on,
)

ANCHOR = date(2026, 8, 18)


def test_default_is_seven_am() -> None:
    """The shipped default is 07:00 local time."""
    assert parse_check_time("07:00:00", time(7)) == time(7, 0, 0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("07:00", time(7, 0)),
        ("7:30", time(7, 30)),
        ("23:59:59", time(23, 59, 59)),
        ("00:00:00", time(0, 0)),
        (time(6, 15), time(6, 15)),
    ],
)
def test_valid_times(raw: str | time, expected: time) -> None:
    """Times are accepted with or without seconds."""
    assert parse_check_time(raw, time(7)) == expected


@pytest.mark.parametrize("raw", ["", None, "nonsense", "25:00", "12:61", "-1:00"])
def test_invalid_times_fall_back(raw: str | None) -> None:
    """Bad input falls back to the default rather than crashing the timer."""
    assert parse_check_time(raw, time(7)) == time(7)


def test_daily_runs_every_day() -> None:
    """An interval of one day runs every day from the anchor onwards."""
    assert should_run_on(ANCHOR, ANCHOR, 1) is True
    assert should_run_on(ANCHOR, date(2026, 8, 19), 1) is True
    assert should_run_on(ANCHOR, date(2026, 12, 25), 1) is True


def test_dates_before_the_anchor_never_run() -> None:
    """A clock skewed into the past does not trigger a check."""
    assert should_run_on(ANCHOR, date(2026, 8, 17), 1) is False
    assert should_run_on(ANCHOR, date(2026, 8, 17), 7) is False


def test_weekly_runs_only_on_the_anchor_weekday() -> None:
    """An interval of seven days runs weekly, counted from the anchor."""
    assert should_run_on(ANCHOR, ANCHOR, 7) is True
    assert should_run_on(ANCHOR, date(2026, 8, 24), 7) is False
    assert should_run_on(ANCHOR, date(2026, 8, 25), 7) is True
    assert should_run_on(ANCHOR, date(2026, 9, 1), 7) is True


def test_interval_survives_a_month_boundary() -> None:
    """Every 30 days keeps counting across months."""
    assert should_run_on(ANCHOR, date(2026, 9, 17), 30) is True
    assert should_run_on(ANCHOR, date(2026, 9, 18), 30) is False


def test_jitter_is_stable_and_bounded() -> None:
    """The stagger is the same every day for a vehicle, and within range."""
    first = jitter_seconds("qld:ABC123", 300)
    assert first == jitter_seconds("qld:ABC123", 300)
    assert 0 <= first <= 300


def test_jitter_differs_between_vehicles() -> None:
    """Two vehicles do not hit the site at the same instant."""
    plates = [f"qld:ABC{n:03d}" for n in range(40)]
    offsets = {jitter_seconds(p, 300) for p in plates}
    assert len(offsets) > 25


def test_jitter_can_be_disabled() -> None:
    """Setting the spread to zero checks exactly on the hour."""
    assert jitter_seconds("qld:ABC123", 0) == 0


def test_next_run_date_daily() -> None:
    """Once today's check has run, the next one is tomorrow."""
    assert next_run_date(ANCHOR, ANCHOR, 1, already_ran_today=False) == ANCHOR
    assert next_run_date(ANCHOR, ANCHOR, 1, already_ran_today=True) == date(2026, 8, 19)


def test_next_run_date_weekly() -> None:
    """A weekly schedule reports the next due date."""
    assert next_run_date(ANCHOR, date(2026, 8, 19), 7, already_ran_today=False) == date(
        2026, 8, 25
    )
