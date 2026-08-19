"""Tasmania — Department of State Growth registration status check.

https://www.transport.tas.gov.au/rego-status/search

The form itself is straightforward, but the site sits behind Cloudflare bot
protection. A request from a home connection may well be served normally, while
one from a datacentre address is usually challenged. The provider therefore
makes the request properly and reports a clear "blocked" result if it is
challenged, rather than reading the challenge page as a registration answer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderParseError
from ..models import RegoResult
from ._forms import find_field_name, find_form
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = "https://www.transport.tas.gov.au/rego-status/search"


class TasmaniaProvider(ScraperProvider):
    """Tasmanian registration status check."""

    key = "tas"
    name = "Tasmania"
    check_url = CHECK_URL
    gated = True
    gated_reason = (
        "The Tasmanian site is behind Cloudflare bot protection. It often works "
        "from a home internet connection, but may be challenged. If checks keep "
        "failing, switch this vehicle to manual mode."
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Submit the plate to the rego status search."""
        plate = self.validate_plate(plate)

        page = await self._get(client, CHECK_URL)
        form = find_form(page.text, contains_field="plate") or find_form(
            page.text, action_contains="rego-status"
        )
        if form is None:
            raise ProviderParseError(
                "Could not find the Tasmanian registration search form."
            )

        plate_field = find_field_name(page.text, "plate", "rego", "search") or "plate"
        page_url = page.url or CHECK_URL

        if form.method == "get":
            response = await self._get(
                client,
                form.absolute_action(page_url),
                params=form.payload(**{plate_field: plate}),
                headers={"Referer": page_url},
            )
        else:
            response = await self._post(
                client,
                form.absolute_action(page_url),
                data=form.payload(**{plate_field: plate}),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": page_url,
                },
            )
        return self.parse(response.text, plate, date.today())
