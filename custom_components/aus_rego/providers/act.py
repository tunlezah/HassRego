"""Australian Capital Territory — Access Canberra registration check.

https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage

Another Wicket wizard. The first step takes the plate and a privacy
acknowledgement checkbox; the session id is embedded in the form action.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderParseError
from ..models import RegoResult
from ._forms import find_field_name, find_form
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = "https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage"


class AustralianCapitalTerritoryProvider(ScraperProvider):
    """Access Canberra registration check."""

    key = "act"
    name = "Australian Capital Territory"
    check_url = CHECK_URL

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Drive the Wicket wizard and read the result page."""
        plate = self.validate_plate(plate)

        page = await self._get(client, CHECK_URL)
        form = find_form(page.text, contains_field="view:plateNumber") or find_form(
            page.text, action_contains="wizard-form"
        )
        if form is None:
            raise ProviderParseError(
                "Could not find the ACT registration form on the page."
            )

        plate_field = find_field_name(page.text, "platenumber", "plate")
        privacy_field = find_field_name(page.text, "privacycheck", "privacy")
        if plate_field is None:
            raise ProviderParseError("Could not find the ACT plate field.")

        payload = form.payload(**{plate_field: plate, "buttons:next": "Next >"})
        if privacy_field:
            # Ticking the privacy acknowledgement is what a user does on this
            # page before the service will answer.
            payload[privacy_field] = "on"

        response = await self._post(
            client,
            form.absolute_action(page.url or CHECK_URL),
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page.url or CHECK_URL,
            },
        )
        return self.parse(response.text, plate, date.today())
