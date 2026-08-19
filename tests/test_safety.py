"""The invariant that matters: a failed check is never a "no".

If a government site is down, blocked, or restyled, the integration must say
"unknown" and go unavailable. It must never tell an automation the vehicle is
unregistered, because that automation might flash a light or send a warning at
7am about a car that is perfectly legal.
"""

from __future__ import annotations

from datetime import date

import pytest
from aus_rego.exceptions import (
    ProviderBlockedError,
    ProviderGeoBlockedError,
    ProviderParseError,
)
from aus_rego.models import NEGATIVE_STATUSES, RegoResult, RegoStatus
from aus_rego.providers.base import guard_response
from aus_rego.providers.sa import SouthAustraliaProvider
from conftest import fixture

TODAY = date(2026, 8, 18)


def test_cloudflare_challenge_is_blocked_not_parsed() -> None:
    """A bot-protection interstitial raises rather than being read."""
    with pytest.raises(ProviderBlockedError):
        guard_response(fixture("cloudflare_challenge.html"), 403)


def test_geo_block_is_reported_distinctly() -> None:
    """An "outside Australia" page raises the geo-block error."""
    with pytest.raises(ProviderGeoBlockedError):
        guard_response(fixture("geo_block.html"), 200)


def test_http_403_is_blocked() -> None:
    """A bare 403 is treated as a block, not as a negative answer."""
    with pytest.raises(ProviderBlockedError):
        guard_response("<html><body>Forbidden</body></html>", 403)


def test_normal_page_passes_the_guard() -> None:
    """A real result page is not mistaken for a block."""
    guard_response(fixture("sa_registered.html"), 200)


def test_unknown_result_is_not_a_negative() -> None:
    """``registered`` is None — not False — when nothing was learned."""
    result = RegoResult.unknown("ABC123", "sa", "temporary_error")

    assert result.status is RegoStatus.UNKNOWN
    assert result.registered is None
    assert result.registered is not False
    assert result.is_conclusive is False


@pytest.mark.parametrize("status", list(RegoStatus))
def test_only_conclusive_statuses_answer_the_question(status: RegoStatus) -> None:
    """Every status is either a clear yes, a clear no, or explicitly unknown."""
    result = RegoResult(status=status, plate="ABC123", jurisdiction="sa")

    if status is RegoStatus.REGISTERED:
        assert result.registered is True
    elif status is RegoStatus.UNKNOWN:
        assert result.registered is None
    else:
        assert status in NEGATIVE_STATUSES
        assert result.registered is False


def test_blocked_page_never_reaches_the_parser() -> None:
    """A provider raises on a challenge page instead of returning a result."""
    provider = SouthAustraliaProvider()
    with pytest.raises(ProviderBlockedError):
        guard_response(fixture("cloudflare_challenge.html"), 200)
    # And a page that loads but has no fields is a parse error, not a "no".
    with pytest.raises(ProviderParseError):
        provider.parse("<html><body>Maintenance</body></html>", "ABC123", TODAY)


def test_error_page_with_negative_words_still_needs_real_fields() -> None:
    """An outage page mentioning "not registered" must not become a negative."""
    html = (
        "<html><body><h1>Service unavailable</h1>"
        "<p>We cannot tell you whether a vehicle is not registered right now.</p>"
        "</body></html>"
    )
    provider = SouthAustraliaProvider()
    with pytest.raises(ProviderParseError):
        provider.parse(html, "ABC123", TODAY)
