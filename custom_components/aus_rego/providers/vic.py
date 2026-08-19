"""Victoria — Service Victoria registration check.

https://service.vic.gov.au/find-services/transport-and-driving/registration/check-registration/vehicle

Service Victoria took the check over from VicRoads and guards it with reCAPTCHA,
exactly as New South Wales does. See :mod:`.nsw` for why this provider reports
the block instead of trying to work around it.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import ProviderBlockedError
from ..models import RegoResult
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = (
    "https://service.vic.gov.au/find-services/transport-and-driving/"
    "registration/check-registration/vehicle"
)


class VictoriaProvider(ScraperProvider):
    """Service Victoria registration check (reCAPTCHA protected)."""

    key = "vic"
    name = "Victoria"
    check_url = CHECK_URL
    gated = True
    gated_reason = (
        "Service Victoria protects the registration check with reCAPTCHA, so it "
        "cannot be checked automatically. Use manual mode and update the expiry "
        "date after each renewal, or use the REST provider."
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Report the block rather than send a request that must fail."""
        raise ProviderBlockedError(self.gated_reason)
