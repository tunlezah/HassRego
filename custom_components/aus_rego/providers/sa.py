"""South Australia — EzyReg check registration.

https://account.ezyreg.sa.gov.au/account/check-registration.htm

A plain POST form: ``registrationType`` (VEHICLE or BOAT) plus ``plate``.
EzyReg only answers requests originating in Australia.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..models import RegoResult
from ._scraper import ScraperProvider
from .base import HttpClient, ProviderField

CHECK_URL = "https://account.ezyreg.sa.gov.au/account/check-registration.htm"


class SouthAustraliaProvider(ScraperProvider):
    """EzyReg registration check."""

    key = "sa"
    name = "South Australia"
    check_url = CHECK_URL
    extra_fields = (
        ProviderField(
            key="vehicle_type",
            label="Registration type",
            options=["VEHICLE", "BOAT"],
            default="VEHICLE",
        ),
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Submit the plate to EzyReg and read the result."""
        plate = self.validate_plate(plate)
        registration_type = (config.get("vehicle_type") or "VEHICLE").upper()

        # Load the form first so the session cookie EzyReg sets is present.
        await self._get(client, CHECK_URL)

        response = await self._post(
            client,
            CHECK_URL,
            data={"registrationType": registration_type, "plate": plate},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": CHECK_URL,
            },
        )
        return self.parse(response.text, plate, date.today())
