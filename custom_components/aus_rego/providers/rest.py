"""Generic REST provider — use any registration API you have access to.

Point it at a URL, say where the answer lives in the JSON, and it behaves like
any other provider. Useful for a commercial data service, a fleet system, or
your own script sitting in front of a state site.

``{plate}`` in the URL, headers or body is replaced with the plate.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from ..exceptions import ProviderParseError, ProviderTemporaryError
from ..models import RegoResult, RegoStatus, derive_status
from ._html import parse_date
from .base import HttpClient, ProviderField, RegoProvider, guard_response

TRUTHY = {"true", "yes", "y", "1", "current", "registered", "active", "valid", "ok"}
FALSY = {"false", "no", "n", "0", "expired", "unregistered", "cancelled", "suspended"}


class RestProvider(RegoProvider):
    """Query a user-supplied JSON API."""

    key = "rest"
    name = "Custom REST API"
    plate_pattern = r"^[A-Z0-9]{1,10}$"
    extra_fields = (
        ProviderField(key="rest_url", label="Request URL (use {plate})"),
        ProviderField(key="rest_method", label="HTTP method", default="GET"),
        ProviderField(key="rest_headers", label="Headers (JSON)", required=False),
        ProviderField(key="rest_body", label="Request body", required=False),
        ProviderField(
            key="rest_status_path", label="JSON path to status", required=False
        ),
        ProviderField(
            key="rest_expiry_path", label="JSON path to expiry date", required=False
        ),
        ProviderField(
            key="rest_registered_path",
            label="JSON path to a registered true/false",
            required=False,
        ),
    )

    async def async_check(
        self, client: HttpClient, plate: str, config: dict[str, Any]
    ) -> RegoResult:
        """Call the configured endpoint and map its response."""
        plate = self.validate_plate(plate)

        url = str(config.get("rest_url") or "")
        if not url:
            raise ProviderParseError("No request URL is configured.")

        headers = _load_headers(config.get("rest_headers"))
        body = config.get("rest_body")
        method = str(config.get("rest_method") or "GET").upper()

        response = await client.request(
            method,
            _substitute(url, plate),
            data=_substitute(str(body), plate) if body else None,
            headers={k: _substitute(v, plate) for k, v in headers.items()},
        )
        if response.status >= 500:
            raise ProviderTemporaryError(f"The API returned HTTP {response.status}.")
        guard_response(response.text, response.status)

        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as err:
            raise ProviderParseError(f"The API did not return JSON: {err}") from err

        return self._map(payload, plate, config, date.today())

    def _map(
        self, payload: Any, plate: str, config: dict[str, Any], today: date
    ) -> RegoResult:
        """Turn the API payload into a result using the configured paths."""
        raw_status = _stringify(
            dig(payload, config.get("rest_status_path")) if config.get("rest_status_path") else None
        )
        expiry = parse_date(
            _stringify(dig(payload, config.get("rest_expiry_path")))
            if config.get("rest_expiry_path")
            else None
        )
        registered = (
            _to_bool(dig(payload, config.get("rest_registered_path")))
            if config.get("rest_registered_path")
            else None
        )

        if raw_status is None and expiry is None and registered is None:
            raise ProviderParseError(
                "None of the configured JSON paths matched the API response."
            )

        if raw_status or expiry is not None:
            status = derive_status(
                raw_status=raw_status,
                expiry=expiry,
                today=today,
                default_registered=registered is not False,
            )
        else:
            status = RegoStatus.REGISTERED if registered else RegoStatus.UNREGISTERED

        # An explicit boolean from the API wins over inference.
        if registered is False and status is RegoStatus.REGISTERED:
            status = RegoStatus.UNREGISTERED
        elif registered is True and status is RegoStatus.UNKNOWN:
            status = RegoStatus.REGISTERED

        return RegoResult(
            status=status,
            plate=plate,
            jurisdiction=config.get("source_jurisdiction") or self.key,
            expiry=expiry,
            message=raw_status,
        )


def dig(payload: Any, path: str | None) -> Any:
    """Resolve a dotted path such as ``data.vehicle.status``.

    Numeric segments index into lists, so ``results.0.expiry`` works too.
    """
    if not path:
        return None
    current = payload
    for part in str(path).split("."):
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _substitute(text: str, plate: str) -> str:
    """Replace the ``{plate}`` placeholder."""
    return text.replace("{plate}", plate)


def _load_headers(raw: Any) -> dict[str, str]:
    """Accept headers as a mapping or a JSON object string."""
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as err:
            raise ProviderParseError(f"Headers are not valid JSON: {err}") from err
        if not isinstance(parsed, dict):
            raise ProviderParseError("Headers must be a JSON object.")
        return {str(k): str(v) for k, v in parsed.items()}
    return {}


def _stringify(value: Any) -> str | None:
    """Render a JSON scalar as text."""
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)


def _to_bool(value: Any) -> bool | None:
    """Interpret an API's idea of true/false, returning None if unclear."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUTHY:
            return True
        if lowered in FALSY:
            return False
    return None
