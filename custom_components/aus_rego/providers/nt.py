"""Northern Territory — MVR registration check.

https://nt.gov.au/driving/rego/existing-nt-registration/rego-check

Like Tasmania, the Northern Territory site is fronted by Cloudflare. The request
is made properly and a challenge is reported as a block rather than parsed.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderParseError
from ..models import RegoResult
from ._forms import find_field_name, find_form
from ._scraper import ScraperProvider
from .base import HttpClient

CHECK_URL = "https://nt.gov.au/driving/rego/existing-nt-registration/rego-check"


class NorthernTerritoryProvider(ScraperProvider):
    """NT MVR registration check."""

    key = "nt"
    name = "Northern Territory"
    check_url = CHECK_URL
    gated = True
    gated_reason = (
        "The Northern Territory site is behind Cloudflare bot protection. It may "
        "work from a home internet connection. If checks keep failing, switch "
        "this vehicle to manual mode."
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Submit the plate to the NT rego check."""
        plate = self.validate_plate(plate)

        page = await self._get(client, CHECK_URL)
        form = find_form(page.text, contains_field="plate") or find_form(
            page.text, action_contains="rego"
        )
        if form is None:
            raise ProviderParseError(
                "Could not find the Northern Territory registration form."
            )

        plate_field = find_field_name(page.text, "plate", "rego") or "plate"
        page_url = page.url or CHECK_URL

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
