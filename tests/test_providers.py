"""Provider behaviour, driven through a fake HTTP client."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import pytest
from aus_rego.exceptions import (
    InvalidPlateError,
    ProviderBlockedError,
    ProviderNotConfiguredError,
    ProviderParseError,
)
from aus_rego.models import RegoStatus
from aus_rego.providers import (
    FALLBACK_KEYS,
    JURISDICTION_KEYS,
    PROVIDERS,
    get_provider,
    provider_labels,
)
from aus_rego.providers.base import HttpResponse
from aus_rego.providers.manual import ManualProvider
from aus_rego.providers.rest import RestProvider, dig
from aus_rego.providers.sa import SouthAustraliaProvider
from conftest import fixture


class FakeClient:
    """Return canned responses and record what was asked for."""

    def __init__(self, *responses: HttpResponse) -> None:
        """Queue the responses to hand back in order."""
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> HttpResponse:
        """Record the call and pop the next queued response."""
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self._responses:
            raise AssertionError(f"unexpected extra request: {method} {url}")
        return self._responses.pop(0)


def run(coro: Any) -> Any:
    """Run a coroutine in a test."""
    return asyncio.run(coro)


# -- registry ---------------------------------------------------------------
def test_every_state_and_territory_is_covered() -> None:
    """All eight jurisdictions have a provider."""
    assert set(JURISDICTION_KEYS) == {"nsw", "vic", "qld", "sa", "wa", "tas", "nt", "act"}
    for key in JURISDICTION_KEYS:
        assert key in PROVIDERS


def test_fallbacks_are_available_everywhere() -> None:
    """Manual and REST are offered alongside the jurisdictions."""
    assert set(FALLBACK_KEYS) == {"manual", "rest"}
    assert PROVIDERS["manual"].online is False


def test_labels_flag_the_gated_jurisdictions() -> None:
    """The picker warns where automatic checks will not work."""
    labels = provider_labels()
    assert len(labels) == len(JURISDICTION_KEYS) + len(FALLBACK_KEYS)
    for key in ("nsw", "vic", "tas", "nt"):
        assert PROVIDERS[key].gated is True
        assert PROVIDERS[key].gated_reason
    for key in ("qld", "sa", "wa", "act"):
        assert PROVIDERS[key].gated is False


def test_unknown_provider_raises() -> None:
    """An unknown key is rejected rather than silently ignored."""
    with pytest.raises(ValueError):
        get_provider("xx")


# -- plate handling ---------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("abc123", "ABC123"), ("ABC 123", "ABC123"), (" abc-123 ", "ABC123")],
)
def test_plates_are_normalised(raw: str, expected: str) -> None:
    """Case, spaces and dashes are ignored."""
    assert SouthAustraliaProvider().validate_plate(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "TOOMANYCHARS123"])
def test_bad_plates_are_rejected(raw: str) -> None:
    """Obvious rubbish is rejected at setup rather than at 7am."""
    with pytest.raises(InvalidPlateError):
        SouthAustraliaProvider().validate_plate(raw)


# -- South Australia --------------------------------------------------------
def test_sa_posts_the_plate_and_parses_the_result() -> None:
    """SA loads the form, posts the plate, and reads the answer."""
    client = FakeClient(
        HttpResponse(200, "<html><body><form></form></body></html>"),
        HttpResponse(200, fixture("sa_registered.html")),
    )
    result = run(
        SouthAustraliaProvider().async_check(client, "s123abc", {"vehicle_type": "VEHICLE"})
    )

    assert result.status is RegoStatus.REGISTERED
    assert result.expiry == date(2027, 9, 30)
    post = client.calls[1]
    assert post["method"] == "POST"
    assert post["data"] == {"registrationType": "VEHICLE", "plate": "S123ABC"}


def test_sa_geo_block_is_raised_not_parsed() -> None:
    """The "outside Australia" page raises instead of becoming a result."""
    client = FakeClient(HttpResponse(200, fixture("geo_block.html")))
    with pytest.raises(ProviderBlockedError):
        run(SouthAustraliaProvider().async_check(client, "S123ABC", {}))


# -- gated jurisdictions ----------------------------------------------------
@pytest.mark.parametrize("key", ["nsw", "vic"])
def test_recaptcha_jurisdictions_report_the_block_without_requesting(key: str) -> None:
    """No pointless daily request is sent to a service that will refuse it."""
    client = FakeClient()  # any request would raise
    with pytest.raises(ProviderBlockedError):
        run(PROVIDERS[key].async_check(client, "ABC123", {}))
    assert client.calls == []


# -- manual -----------------------------------------------------------------
def test_manual_tracks_a_future_expiry() -> None:
    """A future date means registered."""
    future = date(date.today().year + 1, 1, 1)
    result = run(
        ManualProvider().async_check(None, "ABC123", {"manual_expiry": future.isoformat()})
    )
    assert result.status is RegoStatus.REGISTERED
    assert result.expiry == future


def test_manual_reports_a_past_expiry_as_expired() -> None:
    """A past date means expired."""
    result = run(
        ManualProvider().async_check(None, "ABC123", {"manual_expiry": "2020-01-01"})
    )
    assert result.status is RegoStatus.EXPIRED
    assert result.registered is False


def test_manual_without_a_date_asks_to_be_configured() -> None:
    """A missing date is a configuration problem, not a negative answer."""
    with pytest.raises(ProviderNotConfiguredError):
        run(ManualProvider().async_check(None, "ABC123", {}))


# -- generic REST -----------------------------------------------------------
def test_rest_reads_the_configured_paths() -> None:
    """A JSON API is mapped through the configured dotted paths."""
    client = FakeClient(
        HttpResponse(
            200,
            '{"data": {"registration": {"status": "CURRENT", "expiry": "2027-05-01"}}}',
        )
    )
    result = run(
        RestProvider().async_check(
            client,
            "ABC123",
            {
                "rest_url": "https://example.invalid/rego/{plate}",
                "rest_status_path": "data.registration.status",
                "rest_expiry_path": "data.registration.expiry",
            },
        )
    )
    assert result.status is RegoStatus.REGISTERED
    assert result.expiry == date(2027, 5, 1)
    assert client.calls[0]["url"] == "https://example.invalid/rego/ABC123"


def test_rest_honours_an_explicit_false() -> None:
    """An API saying registered=false is believed."""
    client = FakeClient(HttpResponse(200, '{"isRegistered": false}'))
    result = run(
        RestProvider().async_check(
            client,
            "ABC123",
            {
                "rest_url": "https://example.invalid/{plate}",
                "rest_registered_path": "isRegistered",
            },
        )
    )
    assert result.registered is False


def test_rest_rejects_a_response_that_matches_nothing() -> None:
    """A mismatched mapping is an error, never a silent "not registered"."""
    client = FakeClient(HttpResponse(200, '{"unexpected": true}'))
    with pytest.raises(ProviderParseError):
        run(
            RestProvider().async_check(
                client,
                "ABC123",
                {
                    "rest_url": "https://example.invalid/{plate}",
                    "rest_status_path": "data.status",
                },
            )
        )


def test_rest_rejects_non_json() -> None:
    """An HTML error page from an API is an error, not a result."""
    client = FakeClient(HttpResponse(200, "<html>nope</html>"))
    with pytest.raises(ProviderParseError):
        run(
            RestProvider().async_check(
                client,
                "ABC123",
                {"rest_url": "https://example.invalid/{plate}", "rest_status_path": "s"},
            )
        )


@pytest.mark.parametrize(
    ("payload", "path", "expected"),
    [
        ({"a": {"b": 1}}, "a.b", 1),
        ({"a": [{"b": 2}]}, "a.0.b", 2),
        ({"a": {"b": 1}}, "a.c", None),
        ({"a": {"b": 1}}, "", None),
        ({"a": [1]}, "a.9", None),
        ({"a": 1}, "a.b", None),
    ],
)
def test_dig_resolves_paths_safely(payload: Any, path: str, expected: Any) -> None:
    """Path resolution handles lists, misses and bad shapes without raising."""
    assert dig(payload, path) == expected
