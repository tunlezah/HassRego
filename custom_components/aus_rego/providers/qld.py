"""Queensland — Transport and Main Roads check registration.

https://www.service.transport.qld.gov.au/checkrego/

A JSF/PrimeFaces application. Reaching the search form means:

1. loading the service, which redirects to a terms-of-use page,
2. submitting ``tAndCForm:confirmButton`` to accept those terms,
3. submitting the plate on ``vehicleSearchForm``.

Because step 2 accepts TMR's terms of use on the user's behalf, the config flow
asks the user to acknowledge them before this provider can be selected.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..exceptions import ProviderParseError
from ..models import RegoResult
from ._forms import find_form
from ._html import extract_pairs, find_value
from ._scraper import ScraperProvider
from .base import HttpClient, ProviderField

BASE = "https://www.service.transport.qld.gov.au/checkrego/application"
SEARCH_URL = f"{BASE}/VehicleSearch.xhtml"
TERMS_URL = "https://www.tmr.qld.gov.au/Help/Terms-of-use"

# "2018 TOYOTA COROLLA SEDAN" -> year, make, model, body
_DESCRIPTION_RE = re.compile(
    r"^\s*(?P<year>\d{4})?\s*(?P<make>[A-Z][A-Z0-9-]*)\s+(?P<rest>.+?)\s*$"
)
_BODY_WORDS = (
    "SEDAN", "HATCHBACK", "WAGON", "UTILITY", "UTE", "COUPE", "CONVERTIBLE",
    "VAN", "BUS", "TRUCK", "TRAILER", "MOTOR CYCLE", "MOTORCYCLE", "SUV",
    "CAB CHASSIS", "PANEL VAN", "TRAY", "CARAVAN",
)


class QueenslandProvider(ScraperProvider):
    """TMR check registration status."""

    key = "qld"
    name = "Queensland"
    check_url = "https://www.service.transport.qld.gov.au/checkrego/"
    extra_fields = (
        ProviderField(
            key="accept_terms",
            label="I accept the Queensland TMR terms of use",
            default=False,
        ),
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Accept the terms, submit the plate, read the result."""
        plate = self.validate_plate(plate)

        # Step 1 — landing on the service redirects to the terms page.
        landing = await self._get(client, SEARCH_URL)
        page_url = landing.url or SEARCH_URL
        html = landing.text

        # Step 2 — accept the terms if we were sent to that page.
        terms_form = find_form(html, form_id="tAndCForm")
        if terms_form is not None and "VehicleSearch" not in page_url:
            accepted = await self._post(
                client,
                terms_form.absolute_action(page_url),
                data=terms_form.payload(**{"tAndCForm:confirmButton": ""}),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": page_url,
                },
            )
            html = accepted.text
            page_url = accepted.url or SEARCH_URL

        # Step 3 — submit the plate.
        search_form = find_form(html, form_id="vehicleSearchForm")
        if search_form is None:
            raise ProviderParseError(
                "Could not reach the Queensland vehicle search form."
            )

        response = await self._post(
            client,
            search_form.absolute_action(page_url),
            data=search_form.payload(
                **{
                    "vehicleSearchForm:plateNumber": plate,
                    "vehicleSearchForm:referenceId": "",
                    "vehicleSearchForm:confirmButton": "",
                }
            ),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": page_url,
            },
        )
        return self.parse(response.text, plate, date.today())

    def parse(self, html: str, plate: str, today: date) -> RegoResult:
        """Read the result, splitting Queensland's combined description field."""
        result = super().parse(html, plate, today)
        description = find_value(extract_pairs(html), "description")
        if description:
            _apply_description(result, description)
        return result


def _apply_description(result: RegoResult, description: str) -> None:
    """Split "2018 TOYOTA COROLLA SEDAN" into make, model and body type."""
    text = description.strip().upper()
    body = None
    for word in _BODY_WORDS:
        if text.endswith(f" {word}"):
            body = word.title()
            text = text[: -len(word) - 1].strip()
            break

    match = _DESCRIPTION_RE.match(text)
    if not match:
        return
    result.make = result.make or match.group("make").title()
    model = match.group("rest").strip()
    result.model = result.model or (model.title() if model else None)
    result.body_type = result.body_type or body
