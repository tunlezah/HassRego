"""Manual expiry tracking — works in every jurisdiction.

You enter the expiry date once, from your renewal notice or an official check,
and Home Assistant counts down from it. There is no network call, so this works
for the states whose sites cannot be checked automatically while still giving
exactly the same sensors, events and automations.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..exceptions import ProviderNotConfiguredError
from ..models import RegoResult, RegoStatus
from ._html import parse_date
from .base import HttpClient, ProviderField, RegoProvider


class ManualProvider(RegoProvider):
    """Track a user-supplied expiry date."""

    key = "manual"
    name = "Manual (enter expiry date yourself)"
    online = False
    plate_pattern = r"^[A-Z0-9]{1,10}$"
    extra_fields = (
        ProviderField(key="manual_expiry", label="Registration expiry date"),
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Compare today against the stored expiry date."""
        raw = config.get("manual_expiry")
        expiry = raw if isinstance(raw, date) else parse_date(str(raw or "") or None)
        if expiry is None:
            raise ProviderNotConfiguredError(
                "Set the registration expiry date in the integration options."
            )

        today = date.today()
        return RegoResult(
            status=RegoStatus.REGISTERED if expiry >= today else RegoStatus.EXPIRED,
            plate=plate,
            jurisdiction=config.get("source_jurisdiction") or self.key,
            expiry=expiry,
            message="Tracked from the expiry date you entered.",
        )
