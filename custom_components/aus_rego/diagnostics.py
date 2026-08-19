"""Diagnostics, with the plate redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PLATE
from .coordinator import AusRegoConfigEntry

TO_REDACT = {CONF_PLATE, "plate", "rest_url", "rest_headers", "rest_body", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AusRegoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for one vehicle."""
    coordinator = entry.runtime_data
    failure = coordinator.last_failure
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "provider": {
            "key": coordinator.provider.key,
            "name": coordinator.provider.name,
            "gated": coordinator.provider.gated,
            "online": coordinator.provider.online,
        },
        "schedule": {
            "check_time": str(coordinator.check_time),
            "interval_days": coordinator.interval_days,
            "jitter_seconds": coordinator.jitter,
            "warning_days": coordinator.warning_days,
        },
        "state": {
            "last_update_success": coordinator.last_update_success,
            "last_checked": coordinator.last_checked.isoformat()
            if coordinator.last_checked
            else None,
            "result": async_redact_data(
                coordinator.data.as_dict() if coordinator.data else {}, TO_REDACT
            ),
            "last_failure": {
                "reason": failure.reason,
                "error": failure.message,
                "count": failure.count,
                "when": failure.when.isoformat(),
            }
            if failure
            else None,
        },
    }
