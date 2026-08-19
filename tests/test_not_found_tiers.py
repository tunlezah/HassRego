"""Not-found detection must be tight without becoming deaf.

Tightening this to stop outage pages reading as "not registered" must not stop
a genuine "we have no record of that plate" from being recognised.
"""

from __future__ import annotations

from datetime import date

import pytest
from aus_rego.models import RegoStatus
from aus_rego.providers._parse import (
    looks_like_outage,
    looks_not_found,
    parse_result_page,
)

TODAY = date(2026, 8, 18)


@pytest.mark.parametrize(
    "text",
    [
        "No records were found for the plate number you entered.",
        "No matching vehicle could be found.",
        "We could not find a vehicle with that plate.",
        "Unable to locate the registration details requested.",
        "That plate number is not recognised.",
    ],
)
def test_definitive_phrases_stand_alone(text: str) -> None:
    """Phrases about the search itself need no corroboration."""
    assert looks_not_found(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "We cannot tell you whether a vehicle is not registered right now.",
        "Use this service to find out if a vehicle is not registered.",
        "A vehicle that is not registered cannot legally be driven.",
    ],
)
def test_registration_wording_alone_is_not_an_answer(text: str) -> None:
    """Prose about registration state, with no plate, proves nothing."""
    assert looks_not_found(text, "ABC123") is False


def test_registration_wording_counts_when_the_plate_is_echoed() -> None:
    """The same wording is a real answer once the searched plate appears."""
    assert looks_not_found("ABC123 is not registered.", "ABC123") is True


def test_plate_echo_is_matched_despite_formatting() -> None:
    """Spacing and dashes in the echoed plate do not hide it."""
    assert looks_not_found("Plate ABC-123 is not registered.", "ABC123") is True


@pytest.mark.parametrize(
    "text",
    [
        "This service is currently unavailable. Please try again later.",
        "An error occurred. No records were found.",
        "The system is under maintenance.",
    ],
)
def test_outage_pages_are_never_a_negative(text: str) -> None:
    """An outage page is not an answer, even if it uses not-found wording."""
    assert looks_like_outage(text) is True
    assert looks_not_found(text, "ABC123") is False


def test_outage_page_parses_to_unknown() -> None:
    """End to end: an outage page yields unknown, so nothing can act on it."""
    html = (
        "<html><body><h1>Service unavailable</h1>"
        "<p>No records were found. Please try again later.</p></body></html>"
    )
    result = parse_result_page(
        html, plate="ABC123", jurisdiction="sa", today=TODAY
    )
    assert result.status is RegoStatus.UNKNOWN
    assert result.registered is None


def test_genuine_not_found_still_reports_a_negative() -> None:
    """A real "no record" page is still a definite no."""
    html = (
        "<html><body><p>No records were found for the plate number "
        "you entered.</p></body></html>"
    )
    result = parse_result_page(
        html, plate="ZZZ999", jurisdiction="sa", today=TODAY
    )
    assert result.status is RegoStatus.NOT_FOUND
    assert result.registered is False
