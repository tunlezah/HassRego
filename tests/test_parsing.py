"""Result-page parsing for each jurisdiction."""

from __future__ import annotations

from datetime import date

import pytest
from aus_rego.models import RegoStatus
from aus_rego.providers._parse import parse_result_page
from aus_rego.providers.qld import QueenslandProvider
from conftest import fixture

TODAY = date(2026, 8, 18)


def test_queensland_real_layout() -> None:
    """The captured Queensland page parses into a registered result."""
    result = QueenslandProvider().parse(fixture("qld_registered.html"), "ABC123", TODAY)

    assert result.status is RegoStatus.REGISTERED
    assert result.registered is True
    assert result.expiry == date(2027, 2, 17)
    assert result.days_remaining(TODAY) == 183
    # Queensland gives one combined description; it should be split out.
    assert result.make == "Toyota"
    assert result.model == "Corolla"
    assert result.body_type == "Sedan"


@pytest.mark.parametrize(
    ("name", "jurisdiction", "status", "expiry"),
    [
        ("sa_registered.html", "sa", RegoStatus.REGISTERED, date(2027, 9, 30)),
        ("wa_registered.html", "wa", RegoStatus.REGISTERED, date(2027, 3, 14)),
        ("act_expired.html", "act", RegoStatus.EXPIRED, date(2025, 3, 1)),
        ("suspended.html", "sa", RegoStatus.SUSPENDED, date(2027, 12, 31)),
    ],
)
def test_jurisdiction_layouts(
    name: str, jurisdiction: str, status: RegoStatus, expiry: date
) -> None:
    """Each jurisdiction's layout yields the right status and expiry."""
    result = parse_result_page(
        fixture(name), plate="ABC123", jurisdiction=jurisdiction, today=TODAY
    )
    assert result.status is status
    assert result.expiry == expiry


def test_suspended_outranks_a_future_expiry() -> None:
    """A suspended registration is not registered, even if it expires later."""
    result = parse_result_page(
        fixture("suspended.html"), plate="ABC123", jurisdiction="sa", today=TODAY
    )
    assert result.expiry is not None and result.expiry > TODAY
    assert result.registered is False


def test_not_found_page() -> None:
    """A "no records" page is a real negative answer, not an error."""
    result = parse_result_page(
        fixture("not_found.html"), plate="ZZZ999", jurisdiction="sa", today=TODAY
    )
    assert result.status is RegoStatus.NOT_FOUND
    assert result.registered is False


def test_empty_page_is_unknown_not_negative() -> None:
    """A page with no details must not be read as "not registered"."""
    result = parse_result_page(
        "<html><body><p>Welcome</p></body></html>",
        plate="ABC123",
        jurisdiction="sa",
        today=TODAY,
    )
    assert result.status is RegoStatus.UNKNOWN
    assert result.registered is None


def test_script_content_is_ignored() -> None:
    """Text inside <script> must never be mistaken for a result."""
    html = (
        "<html><body><script>var msg = 'Status: cancelled';</script>"
        "<table><tr><th>Status</th><td>Registered</td></tr>"
        "<tr><th>Expiry</th><td>01/01/2027</td></tr></table></body></html>"
    )
    result = parse_result_page(
        html, plate="ABC123", jurisdiction="sa", today=TODAY
    )
    assert result.status is RegoStatus.REGISTERED
