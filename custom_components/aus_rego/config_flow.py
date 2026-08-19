"""Config and options flow."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_CHECK_ON_START,
    CONF_CHECK_TIME,
    CONF_EXPIRY_WARNING_DAYS,
    CONF_INTERVAL_DAYS,
    CONF_JITTER_SECONDS,
    CONF_JURISDICTION,
    CONF_MANUAL_EXPIRY,
    CONF_PLATE,
    CONF_REST_BODY,
    CONF_REST_EXPIRY_PATH,
    CONF_REST_HEADERS,
    CONF_REST_METHOD,
    CONF_REST_REGISTERED_PATH,
    CONF_REST_STATUS_PATH,
    CONF_REST_URL,
    CONF_VEHICLE_NAME,
    CONF_VEHICLE_TYPE,
    DEFAULT_CHECK_ON_START,
    DEFAULT_CHECK_TIME,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_JITTER_SECONDS,
    DOMAIN,
)
from .coordinator import AiohttpClient, AusRegoConfigEntry
from .exceptions import (
    InvalidPlateError,
    ProviderBlockedError,
    ProviderNotConfiguredError,
    RegoError,
)
from .models import RegoStatus
from .providers import FALLBACK_KEYS, JURISDICTION_KEYS, PROVIDERS, get_provider

_LOGGER = logging.getLogger(__name__)


def _jurisdiction_selector() -> selector.SelectSelector:
    """Build the state/territory picker."""
    options = [
        selector.SelectOptionDict(
            value=key,
            label=(
                f"{PROVIDERS[key].name}"
                + (" — automatic checks blocked" if PROVIDERS[key].gated else "")
            ),
        )
        for key in JURISDICTION_KEYS
    ]
    options += [
        selector.SelectOptionDict(value=key, label=PROVIDERS[key].name)
        for key in FALLBACK_KEYS
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN
        )
    )


VEHICLE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JURISDICTION): _jurisdiction_selector(),
        vol.Required(CONF_PLATE): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Optional(CONF_VEHICLE_NAME): selector.TextSelector(),
    }
)


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the schedule options schema, pre-filled with current values."""
    return vol.Schema(
        {
            vol.Required(
                CONF_CHECK_TIME,
                default=current.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME),
            ): selector.TimeSelector(),
            vol.Required(
                CONF_INTERVAL_DAYS,
                default=current.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=90, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_EXPIRY_WARNING_DAYS,
                default=current.get(
                    CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=180, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_CHECK_ON_START,
                default=current.get(CONF_CHECK_ON_START, DEFAULT_CHECK_ON_START),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_JITTER_SECONDS,
                default=current.get(CONF_JITTER_SECONDS, DEFAULT_JITTER_SECONDS),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=3600, step=30, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


def _provider_schema(key: str, current: dict[str, Any]) -> vol.Schema | None:
    """Build the extra-details schema a provider needs, if any."""
    fields: dict[Any, Any] = {}

    if key == "sa":
        fields[
            vol.Required(
                CONF_VEHICLE_TYPE, default=current.get(CONF_VEHICLE_TYPE, "VEHICLE")
            )
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value="VEHICLE", label="Vehicle"),
                    selector.SelectOptionDict(value="BOAT", label="Boat"),
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    elif key == "qld":
        fields[vol.Required("accept_terms", default=False)] = (
            selector.BooleanSelector()
        )
    elif key == "manual":
        fields[
            vol.Required(CONF_MANUAL_EXPIRY, default=current.get(CONF_MANUAL_EXPIRY))
        ] = selector.DateSelector()
    elif key == "rest":
        fields[vol.Required(CONF_REST_URL, default=current.get(CONF_REST_URL, ""))] = (
            selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
            )
        )
        fields[
            vol.Required(CONF_REST_METHOD, default=current.get(CONF_REST_METHOD, "GET"))
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["GET", "POST"], mode=selector.SelectSelectorMode.DROPDOWN
            )
        )
        for conf_key in (
            CONF_REST_HEADERS,
            CONF_REST_BODY,
            CONF_REST_STATUS_PATH,
            CONF_REST_EXPIRY_PATH,
            CONF_REST_REGISTERED_PATH,
        ):
            fields[vol.Optional(conf_key, default=current.get(conf_key, ""))] = (
                selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT, multiline=True
                    )
                )
            )

    return vol.Schema(fields) if fields else None


class AusRegoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one vehicle at a time. Add the integration again for more vehicles."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with an empty vehicle."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the state and plate."""
        errors: dict[str, str] = {}

        if user_input is not None:
            jurisdiction = user_input[CONF_JURISDICTION]
            provider = get_provider(jurisdiction)
            try:
                plate = provider.validate_plate(user_input[CONF_PLATE])
            except InvalidPlateError:
                errors[CONF_PLATE] = "invalid_plate"
            else:
                await self.async_set_unique_id(f"{jurisdiction}_{plate}")
                self._abort_if_unique_id_configured()

                self._data = {
                    CONF_JURISDICTION: jurisdiction,
                    CONF_PLATE: plate,
                    CONF_VEHICLE_NAME: (
                        user_input.get(CONF_VEHICLE_NAME) or plate
                    ).strip(),
                }
                if _provider_schema(jurisdiction, {}) is not None:
                    return await self.async_step_details()
                return await self.async_step_verify()

        return self.async_show_form(
            step_id="user",
            data_schema=VEHICLE_SCHEMA,
            errors=errors,
            description_placeholders={"note": "Add the integration again for more vehicles."},
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect whatever else the chosen provider needs."""
        jurisdiction = self._data[CONF_JURISDICTION]
        errors: dict[str, str] = {}

        if user_input is not None:
            if jurisdiction == "qld" and not user_input.get("accept_terms"):
                errors["accept_terms"] = "terms_required"
            else:
                cleaned = dict(user_input)
                expiry = cleaned.get(CONF_MANUAL_EXPIRY)
                if isinstance(expiry, date):
                    cleaned[CONF_MANUAL_EXPIRY] = expiry.isoformat()
                self._data.update(cleaned)
                return await self.async_step_verify()

        schema = _provider_schema(jurisdiction, self._data)
        assert schema is not None
        return self.async_show_form(
            step_id="details",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "jurisdiction": PROVIDERS[jurisdiction].name,
                "check_url": PROVIDERS[jurisdiction].check_url or "",
            },
        )

    async def async_step_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Try the check once so setup problems surface now, not at 7am."""
        jurisdiction = self._data[CONF_JURISDICTION]
        provider = get_provider(jurisdiction)

        if provider.gated:
            # No point making a request that is going to be refused.
            return await self.async_step_confirm_gated()

        client = AiohttpClient(async_create_clientsession(self.hass))
        try:
            result = await provider.async_check(
                client, self._data[CONF_PLATE], self._data
            )
        except ProviderNotConfiguredError as err:
            return self.async_abort(
                reason="not_configured", description_placeholders={"error": str(err)}
            )
        except ProviderBlockedError as err:
            self._data["_setup_error"] = str(err)
            return await self.async_step_confirm_gated()
        except RegoError as err:
            _LOGGER.debug("Setup check for %s failed: %s", self._data[CONF_PLATE], err)
            self._data["_setup_error"] = str(err)
            return await self.async_step_confirm_gated()

        if result.status is RegoStatus.NOT_FOUND:
            # Almost always a typo, so make the user confirm rather than
            # silently creating a vehicle that alarms every morning.
            return await self.async_step_confirm_not_found()

        return self._create()

    async def async_step_confirm_not_found(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a vehicle whose plate the registry does not know."""
        if user_input is not None:
            return self._create()
        return self.async_show_form(
            step_id="confirm_not_found",
            data_schema=vol.Schema({}),
            description_placeholders={
                "plate": self._data[CONF_PLATE],
                "jurisdiction": PROVIDERS[self._data[CONF_JURISDICTION]].name,
            },
        )

    async def async_step_confirm_gated(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain that automatic checks will not work, and offer to continue."""
        jurisdiction = self._data[CONF_JURISDICTION]
        provider = PROVIDERS[jurisdiction]
        if user_input is not None:
            return self._create()
        return self.async_show_form(
            step_id="confirm_gated",
            data_schema=vol.Schema({}),
            description_placeholders={
                "jurisdiction": provider.name,
                "reason": self._data.get("_setup_error") or provider.gated_reason,
                "check_url": provider.check_url,
            },
        )

    def _create(self) -> ConfigFlowResult:
        """Create the entry with the default 7am daily schedule."""
        data = {k: v for k, v in self._data.items() if not k.startswith("_")}
        return self.async_create_entry(
            title=data[CONF_VEHICLE_NAME],
            data=data,
            options={
                CONF_CHECK_TIME: DEFAULT_CHECK_TIME,
                CONF_INTERVAL_DAYS: DEFAULT_INTERVAL_DAYS,
                CONF_EXPIRY_WARNING_DAYS: DEFAULT_EXPIRY_WARNING_DAYS,
                CONF_CHECK_ON_START: DEFAULT_CHECK_ON_START,
                CONF_JITTER_SECONDS: DEFAULT_JITTER_SECONDS,
                "anchor_date": date.today().isoformat(),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: AusRegoConfigEntry) -> AusRegoOptionsFlow:
        """Return the options flow."""
        return AusRegoOptionsFlow()


class AusRegoOptionsFlow(OptionsFlow):
    """Change the schedule, the warning window, and provider details."""

    def __init__(self) -> None:
        """Hold the schedule options while the details step runs."""
        self._pending: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the schedule options."""
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(
                {
                    CONF_CHECK_TIME: user_input[CONF_CHECK_TIME],
                    CONF_INTERVAL_DAYS: int(user_input[CONF_INTERVAL_DAYS]),
                    CONF_EXPIRY_WARNING_DAYS: int(user_input[CONF_EXPIRY_WARNING_DAYS]),
                    CONF_CHECK_ON_START: user_input[CONF_CHECK_ON_START],
                    CONF_JITTER_SECONDS: int(user_input[CONF_JITTER_SECONDS]),
                }
            )
            jurisdiction = self.config_entry.data[CONF_JURISDICTION]
            if _provider_schema(jurisdiction, {}) is not None:
                self._pending = options
                return await self.async_step_details()
            return self.async_create_entry(data=options)

        current = {**self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(current)
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the provider-specific details, such as a manual expiry date."""
        jurisdiction = self.config_entry.data[CONF_JURISDICTION]

        if user_input is not None:
            cleaned = dict(user_input)
            expiry = cleaned.get(CONF_MANUAL_EXPIRY)
            if isinstance(expiry, date):
                cleaned[CONF_MANUAL_EXPIRY] = expiry.isoformat()
            return self.async_create_entry(data={**self._pending, **cleaned})

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = _provider_schema(jurisdiction, current)
        assert schema is not None
        return self.async_show_form(step_id="details", data_schema=schema)
