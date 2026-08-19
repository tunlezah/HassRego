"""The Australian Vehicle Registration integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CHECK_ON_START,
    CONF_JURISDICTION,
    CONF_PLATE,
    DEFAULT_CHECK_ON_START,
    DOMAIN,
    SERVICE_CHECK_NOW,
    SERVICE_CHECK_PLATE,
    STARTUP_CHECK_DELAY,
)
from .coordinator import AiohttpClient, AusRegoConfigEntry, AusRegoCoordinator
from .exceptions import RegoError
from .providers import JURISDICTION_KEYS, PROVIDERS, get_provider

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

CHECK_NOW_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
    }
)

CHECK_PLATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JURISDICTION): vol.In(list(PROVIDERS)),
        vol.Required(CONF_PLATE): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: AusRegoConfigEntry) -> bool:
    """Set up one vehicle."""
    coordinator = AusRegoCoordinator(hass, entry)
    await coordinator.async_prepare()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if entry.options.get(CONF_CHECK_ON_START, DEFAULT_CHECK_ON_START):
        # Delayed so a restart storm does not become an upstream request storm.
        async def _initial_check(_now) -> None:
            await coordinator.async_refresh()

        entry.async_on_unload(
            async_call_later(hass, timedelta(seconds=STARTUP_CHECK_DELAY), _initial_check)
        )

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AusRegoConfigEntry) -> bool:
    """Unload one vehicle."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored result when a vehicle is removed."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_reload_entry(hass: HomeAssistant, entry: AusRegoConfigEntry) -> None:
    """Reload when the options change, so a new schedule takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the integration's services once."""
    if hass.services.has_service(DOMAIN, SERVICE_CHECK_PLATE):
        return

    async def _async_check_plate(call: ServiceCall) -> ServiceResponse:
        """Look a plate up on demand without adding a vehicle."""
        jurisdiction = call.data[CONF_JURISDICTION]
        plate = call.data[CONF_PLATE]
        provider = get_provider(jurisdiction)
        client = AiohttpClient(async_create_clientsession(hass))
        try:
            result = await provider.async_check(client, plate, dict(call.data))
        except RegoError as err:
            raise ServiceValidationError(str(err)) from err
        return result.as_dict()

    async def _async_check_now(call: ServiceCall) -> None:
        """Re-check one, several, or all configured vehicles now."""
        entry_ids = set(call.data.get("entry_id") or [])
        device_ids = set(call.data.get("device_id") or [])

        if device_ids:
            registry = dr.async_get(hass)
            for device_id in device_ids:
                device = registry.async_get(device_id)
                if device:
                    entry_ids.update(device.config_entries)

        entries = [
            entry
            for entry in hass.config_entries.async_loaded_entries(DOMAIN)
            if not entry_ids or entry.entry_id in entry_ids
        ]
        if not entries:
            raise ServiceValidationError("No matching vehicles are set up.")

        for entry in entries:
            await entry.runtime_data.async_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_NOW,
        _async_check_now,
        schema=CHECK_NOW_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHECK_PLATE,
        _async_check_plate,
        schema=CHECK_PLATE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.debug("Registered %s services for %s", DOMAIN, ", ".join(JURISDICTION_KEYS))
