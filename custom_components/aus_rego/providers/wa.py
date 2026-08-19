"""Western Australia — Department of Transport vehicle licence expiry enquiry.

https://online.transport.wa.gov.au/webExternal/registration/

An Apache Wicket application: the form action carries the page version and the
session lives in a cookie, so the form has to be read off the page each time.
WA reports the licence expiry date rather than a status word, so an expiry in
the future is what "registered" means here.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderParseError
from ..models import RegoResult
from ._forms import find_field_name, find_form
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = "https://online.transport.wa.gov.au/webExternal/registration/"


class WesternAustraliaProvider(ScraperProvider):
    """DoT WA vehicle licence expiry enquiry."""

    key = "wa"
    name = "Western Australia"
    check_url = CHECK_URL

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Drive the Wicket form and read the licence expiry date."""
        plate = self.validate_plate(plate)

        page = await self._get(client, CHECK_URL)
        form = find_form(page.text, name="registrationRequestForm") or find_form(
            page.text, contains_field="plateField"
        )
        if form is None:
            raise ProviderParseError(
                "Could not find the WA plate enquiry form on the page."
            )

        plate_field = find_field_name(page.text, "platefield", "plate") or "plateField"
        action = form.absolute_action(page.url or CHECK_URL)

        response = await self._post(
            client,
            action,
            data=form.payload(**{plate_field: plate, "searchButton": "Send"}),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page.url or CHECK_URL,
            },
        )
        return self.parse(response.text, plate, date.today())
