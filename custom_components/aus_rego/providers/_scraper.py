"""Base class for providers that drive a public web form."""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderParseError, ProviderTemporaryError
from ..models import RegoResult
from ._parse import parse_result_page
from .base import HttpClient, HttpResponse, RegoProvider, guard_response


class ScraperProvider(RegoProvider):
    """Fetch a public check page, submit the plate, read the answer."""

    #: Whether a returned record implies the vehicle is currently registered.
    result_implies_registered: bool = True

    async def _get(self, client: HttpClient, url: str, **kwargs: Any) -> HttpResponse:
        """GET a page and reject bot walls before anything reads the body."""
        response = await self._request(client, "GET", url, **kwargs)
        guard_response(response.text, response.status)
        return response

    async def _post(self, client: HttpClient, url: str, **kwargs: Any) -> HttpResponse:
        """POST a form and reject bot walls before anything reads the body."""
        response = await self._request(client, "POST", url, **kwargs)
        guard_response(response.text, response.status)
        return response

    async def _request(
        self, client: HttpClient, method: str, url: str, **kwargs: Any
    ) -> HttpResponse:
        response = await client.request(method, url, **kwargs)
        if response.status >= 500:
            raise ProviderTemporaryError(
                f"{self.name} returned HTTP {response.status}."
            )
        return response

    def parse(self, html: str, plate: str, today: date) -> RegoResult:
        """Interpret the result page."""
        result = parse_result_page(
            html,
            plate=plate,
            jurisdiction=self.key,
            today=today,
            default_registered=self.result_implies_registered,
        )
        if result.error == "no_result_fields":
            raise ProviderParseError(
                f"The {self.name} result page did not contain any registration "
                "details. The site has most likely changed."
            )
        return result
