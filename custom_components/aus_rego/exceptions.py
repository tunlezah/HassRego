"""Errors raised by registration providers."""

from __future__ import annotations


class RegoError(Exception):
    """Base class for all provider errors."""

    #: Short machine-readable reason, surfaced in events and diagnostics.
    reason = "unknown_error"


class ProviderTemporaryError(RegoError):
    """A transient failure: timeout, 5xx, connection reset.

    The check should simply be retried at the next scheduled run.
    """

    reason = "temporary_error"


class ProviderBlockedError(RegoError):
    """The service refused the request rather than answering it.

    Raised for bot-protection interstitials, CAPTCHA challenges and geo-blocks.
    Home Assistant surfaces a repair issue explaining the options instead of
    pretending the vehicle is unregistered.
    """

    reason = "blocked"


class ProviderGeoBlockedError(ProviderBlockedError):
    """The service is only reachable from inside Australia."""

    reason = "geo_blocked"


class ProviderParseError(RegoError):
    """The page loaded but no longer looks the way the provider expects.

    Almost always means the government site changed its markup.
    """

    reason = "parse_error"


class InvalidPlateError(RegoError):
    """The plate is not valid for this jurisdiction."""

    reason = "invalid_plate"


class ProviderNotConfiguredError(RegoError):
    """The provider needs configuration the user has not supplied."""

    reason = "not_configured"
