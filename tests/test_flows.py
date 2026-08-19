"""Multi-step request flows.

The markup here mirrors the structure captured from each live service; the
parsers were checked against the real pages, and these lock in the request
sequence so a refactor cannot quietly break it.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from aus_rego.models import RegoStatus
from aus_rego.providers.act import AustralianCapitalTerritoryProvider
from aus_rego.providers.base import HttpResponse
from aus_rego.providers.qld import QueenslandProvider
from aus_rego.providers.wa import WesternAustraliaProvider
from conftest import fixture

QLD_TERMS_PAGE = """
<html><body>
<form id="tAndCForm" name="tAndCForm" method="post"
      action="/checkrego/application/TermAndConditions.xhtml?dswid=1234">
  <input type="hidden" name="tAndCForm_SUBMIT" value="1" />
  <input type="hidden" name="javax.faces.ViewState" value="VIEWSTATE-1" />
  <input type="hidden" name="javax.faces.ClientWindow" value="1234" />
  <button id="tAndCForm:confirmButton" name="tAndCForm:confirmButton" type="submit">Accept</button>
</form>
</body></html>
"""

QLD_SEARCH_PAGE = """
<html><body>
<form id="vehicleSearchForm" name="vehicleSearchForm" method="post"
      action="/checkrego/application/VehicleSearch.xhtml?dswid=1234">
  <input id="vehicleSearchForm:plateNumber" name="vehicleSearchForm:plateNumber" type="text" />
  <input id="vehicleSearchForm:referenceId" name="vehicleSearchForm:referenceId" type="text" />
  <input type="hidden" name="vehicleSearchForm_SUBMIT" value="1" />
  <input type="hidden" name="javax.faces.ViewState" value="VIEWSTATE-2" />
  <input type="hidden" name="javax.faces.ClientWindow" value="1234" />
  <button name="vehicleSearchForm:confirmButton" type="submit">Continue</button>
</form>
</body></html>
"""

WA_FORM_PAGE = """
<html><body>
<form name="registrationRequestForm" id="id3" method="post"
      action="./?0-1.IFormSubmitListener-layout-layout_body-registrationRequestForm">
  <input type="hidden" name="id3_hf_0" id="id3_hf_0" />
  <input type="text" maxlength="15" name="plateField" value="" id="id1" />
  <input class="licensing-button-short" type="submit" value="Send" name="searchButton" id="id4" />
</form>
</body></html>
"""

ACT_FORM_PAGE = """
<html><body>
<form novalidate="" id="id2" method="post"
      action="./FindRegistrationPage;jsessionid=SESSION?0-1.-contentPanel-wizard-form">
  <input type="text" id="plateNumber" value="" name="view:plateNumber"/>
  <input id="privacyCheck" name="privacy:privacyCheck" type="checkbox"/>
  <input type="submit" value="Next &gt;" name="buttons:next" id="id3"/>
</form>
</body></html>
"""


class RecordingClient:
    """Hand back queued responses and remember every request."""

    def __init__(self, *responses: HttpResponse) -> None:
        """Queue the responses."""
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> HttpResponse:
        """Record and respond."""
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


def run(coro: Any) -> Any:
    """Run a coroutine in a test."""
    return asyncio.run(coro)


def test_queensland_accepts_terms_then_searches() -> None:
    """Queensland needs three requests: land, accept terms, search."""
    client = RecordingClient(
        HttpResponse(
            200,
            QLD_TERMS_PAGE,
            url="https://www.service.transport.qld.gov.au/checkrego/application/TermAndConditions.xhtml?dswid=1234",
        ),
        HttpResponse(
            200,
            QLD_SEARCH_PAGE,
            url="https://www.service.transport.qld.gov.au/checkrego/application/VehicleSearch.xhtml?dswid=1234",
        ),
        HttpResponse(200, fixture("qld_registered.html")),
    )

    result = run(QueenslandProvider().async_check(client, "ABC123", {"accept_terms": True}))

    assert result.status is RegoStatus.REGISTERED
    assert result.expiry == date(2027, 2, 17)
    assert len(client.calls) == 3

    # The JSF view state must be carried through both posts, or the server
    # rejects them.
    accept = client.calls[1]
    assert accept["data"]["javax.faces.ViewState"] == "VIEWSTATE-1"
    assert "tAndCForm:confirmButton" in accept["data"]

    search = client.calls[2]
    assert search["data"]["javax.faces.ViewState"] == "VIEWSTATE-2"
    assert search["data"]["vehicleSearchForm:plateNumber"] == "ABC123"


def test_western_australia_carries_wicket_hidden_fields() -> None:
    """WA's Wicket form state must survive into the POST."""
    client = RecordingClient(
        HttpResponse(200, WA_FORM_PAGE, url="https://online.transport.wa.gov.au/webExternal/registration/"),
        HttpResponse(200, fixture("wa_registered.html")),
    )

    result = run(WesternAustraliaProvider().async_check(client, "1ABC123", {}))

    assert result.status is RegoStatus.REGISTERED
    assert result.expiry == date(2027, 3, 14)

    post = client.calls[1]
    assert post["data"]["plateField"] == "1ABC123"
    assert "id3_hf_0" in post["data"]
    # The relative Wicket action resolves against the page it came from.
    assert post["url"].startswith("https://online.transport.wa.gov.au/webExternal/registration/")


def test_act_ticks_the_privacy_box() -> None:
    """ACT will not answer unless the privacy acknowledgement is submitted."""
    client = RecordingClient(
        HttpResponse(200, ACT_FORM_PAGE, url="https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage"),
        HttpResponse(200, fixture("act_expired.html")),
    )

    result = run(AustralianCapitalTerritoryProvider().async_check(client, "YAA00A", {}))

    assert result.status is RegoStatus.EXPIRED
    assert result.registered is False

    post = client.calls[1]
    assert post["data"]["view:plateNumber"] == "YAA00A"
    assert post["data"]["privacy:privacyCheck"] == "on"
    assert post["data"]["buttons:next"] == "Next >"
    assert "jsessionid=SESSION" in post["url"]
