"""Provider interface.

Providers are split into two halves on purpose:

* an ``async_check`` coroutine that performs HTTP, and
* pure ``parse_*`` functions that turn a response body into a
  :class:`~custom_components.aus_rego.models.RegoResult`.

Only the first half needs a network, so the parsing — the part that breaks when
a government site is restyled — is directly unit testable.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..exceptions import InvalidPlateError, ProviderBlockedError, ProviderGeoBlockedError
from ..models import RegoResult

# A browser-ish user agent. Several of these sites reject the default aiohttp
# agent outright; this is about being served the normal public page, not about
# hiding that a script is asking.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30


@dataclass(slots=True)
class HttpResponse:
    """Minimal response shape, so tests can supply canned pages."""

    status: int
    text: str
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        """Parse the body as JSON."""
        return json.loads(self.text)


class HttpClient(Protocol):
    """The subset of an HTTP session the providers need."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | str | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Perform an HTTP request."""
        ...


# Markers that mean "a bot wall answered", not "the vehicle is unregistered".
_BLOCK_MARKERS = (
    "just a moment",
    "enable javascript and cookies to continue",
    "checking your browser",
    "cf-browser-verification",
    "attention required! | cloudflare",
    "access denied",
    "request unsuccessful",
    "incapsula incident id",
    "px-captcha",
    "unusual traffic",
)

_GEO_MARKERS = (
    "unavailable from outside australia",
    "only available within australia",
    "not available in your country",
    "overseas? contact us for help",
)


def guard_response(body: str, status: int) -> None:
    """Raise if the body is a bot wall or geo-block rather than a real answer.

    Called before parsing so that an interstitial can never be misread as a
    negative registration result.
    """
    lowered = body[:20000].lower()

    for marker in _GEO_MARKERS:
        if marker in lowered:
            raise ProviderGeoBlockedError(
                "This service only answers requests from an Australian IP address."
            )

    for marker in _BLOCK_MARKERS:
        if marker in lowered:
            raise ProviderBlockedError(
                f"The service returned a bot-protection page (HTTP {status})."
            )

    if status == 403:
        raise ProviderBlockedError(
            "The service refused the request (HTTP 403). This is usually bot "
            "protection or a geo-block rather than a problem with the plate."
        )


def normalise_plate(plate: str) -> str:
    """Upper-case a plate and strip spacing and punctuation."""
    return re.sub(r"[^A-Z0-9]", "", plate.upper())


@dataclass(slots=True)
class ProviderField:
    """An extra config field a provider needs beyond the plate."""

    key: str
    label: str
    options: list[str] | None = None
    default: Any = None
    required: bool = True


class RegoProvider(ABC):
    """Base class for a jurisdiction's registration check."""

    #: Short key used in config entries, e.g. ``"nsw"``.
    key: str
    #: Human readable jurisdiction name.
    name: str
    #: Public page a user can open to do the check by hand.
    check_url: str = ""
    #: True when the provider talks to a government service over the network.
    online: bool = True
    #: Extra config fields this provider needs.
    extra_fields: tuple[ProviderField, ...] = ()
    #: Set when the upstream service is known to sit behind bot protection or a
    #: login, so the UI and docs can say so up front.
    gated: bool = False
    #: Explains ``gated`` to the user.
    gated_reason: str = ""
    #: Plate validation pattern.
    plate_pattern: str = r"^[A-Z0-9]{1,8}$"

    @abstractmethod
    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Look the plate up and return a normalised result."""

    def validate_plate(self, plate: str) -> str:
        """Normalise and validate a plate, raising on obvious rubbish."""
        cleaned = normalise_plate(plate)
        if not cleaned:
            raise InvalidPlateError("A plate number is required.")
        if not re.match(self.plate_pattern, cleaned):
            raise InvalidPlateError(
                f"{cleaned!r} does not look like a valid {self.name} plate."
            )
        return cleaned
