"""New South Wales — Service NSW free registration check.

https://free-rego-check.service.nsw.gov.au/

The check itself is free and needs no account, but the app is a React front end
guarded by reCAPTCHA Enterprise: every lookup carries a token minted by Google's
script after it has assessed the browser. There is no supported way for an
integration to obtain that token, and manufacturing one would mean defeating an
anti-automation control the agency deliberately put in place.

So this provider does not send a request it knows will be rejected. It reports
the block immediately and points at the alternatives, which give the same
sensors and automations:

* ``manual`` — enter the expiry date once and track the countdown locally, or
* ``rest``   — point at an API you are entitled to use.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import ProviderBlockedError
from ..models import RegoResult
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = "https://free-rego-check.service.nsw.gov.au/"


class NewSouthWalesProvider(ScraperProvider):
    """Service NSW free registration check (reCAPTCHA protected)."""

    key = "nsw"
    name = "New South Wales"
    check_url = CHECK_URL
    gated = True
    gated_reason = (
        "Service NSW protects the free rego check with reCAPTCHA Enterprise, so "
        "it cannot be checked automatically. Use manual mode and update the "
        "expiry date after each renewal, or use the REST provider."
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Report the block rather than send a request that must fail."""
        raise ProviderBlockedError(self.gated_reason)
