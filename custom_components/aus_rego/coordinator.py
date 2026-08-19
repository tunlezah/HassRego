"""Coordinator: runs the check, remembers the answer, fires the events."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_point_in_time, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CHECK_TIME,
    CONF_EXPIRY_WARNING_DAYS,
    CONF_INTERVAL_DAYS,
    CONF_JITTER_SECONDS,
    CONF_JURISDICTION,
    CONF_PLATE,
    CONF_VEHICLE_NAME,
    DEFAULT_CHECK_TIME,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_JITTER_SECONDS,
    DOMAIN,
    EVENT_CHECK_FAILED,
    EVENT_CHECKED,
    EVENT_EXPIRING,
    EVENT_STATUS_CHANGED,
)
from .exceptions import RegoError
from .models import RegoResult, RegoStatus
from .providers import HttpResponse, get_provider
from .providers.base import USER_AGENT
from .schedule import jitter_seconds, parse_check_time, should_run_on

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=45)


class AiohttpClient:
    """Adapt an aiohttp session to the provider protocol."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Store the session used for this check."""
        self._session = session

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | str | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Perform the request and return a provider-friendly response."""
        merged = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-AU,en;q=0.9",
        }
        merged.update(headers or {})

        async with self._session.request(
            method,
            url,
            params=params,
            data=data,
            json=json_body,
            headers=merged,
            allow_redirects=allow_redirects,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            body = await response.text(errors="replace")
            return HttpResponse(
                status=response.status,
                text=body,
                url=str(response.url),
                headers=dict(response.headers),
            )


@dataclass(slots=True)
class CheckFailure:
    """The most recent failure, kept for diagnostics and the problem sensor."""

    reason: str
    message: str
    when: datetime
    count: int = 1


type AusRegoConfigEntry = ConfigEntry["AusRegoCoordinator"]


class AusRegoCoordinator(DataUpdateCoordinator[RegoResult]):
    """Check one vehicle on a schedule and publish the result."""

    config_entry: AusRegoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: AusRegoConfigEntry) -> None:
        """Set up the coordinator for a single vehicle."""
        self.entry = entry
        self.plate: str = entry.data[CONF_PLATE]
        self.jurisdiction: str = entry.data[CONF_JURISDICTION]
        self.vehicle_name: str = entry.data.get(CONF_VEHICLE_NAME) or self.plate
        self.provider = get_provider(self.jurisdiction)
        self.last_failure: CheckFailure | None = None
        self.last_checked: datetime | None = None

        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # Each vehicle gets its own session, and so its own cookie jar. The
        # Queensland and Wicket flows carry session state in cookies across
        # several requests, so two vehicles checking the same state at once
        # must not share one.
        self._session = async_create_clientsession(hass)
        self._unsub_daily: Any = None
        self._unsub_jitter: Any = None
        self._last_run_date: date | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {self.vehicle_name}",
            # Checks are driven by the configured time of day, not by polling.
            update_interval=None,
            config_entry=entry,
        )

    # -- options ------------------------------------------------------------
    @property
    def check_time(self) -> time:
        """Time of day the check runs."""
        return parse_check_time(
            self.entry.options.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME),
            parse_check_time(DEFAULT_CHECK_TIME, time(7, 0)),
        )

    @property
    def interval_days(self) -> int:
        """How many days between checks."""
        return max(1, int(self.entry.options.get(CONF_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS)))

    @property
    def warning_days(self) -> int:
        """How many days before expiry to start warning."""
        return max(
            0,
            int(self.entry.options.get(CONF_EXPIRY_WARNING_DAYS, DEFAULT_EXPIRY_WARNING_DAYS)),
        )

    @property
    def jitter(self) -> int:
        """Maximum random-looking delay applied after the scheduled time."""
        return max(0, int(self.entry.options.get(CONF_JITTER_SECONDS, DEFAULT_JITTER_SECONDS)))

    # -- lifecycle ----------------------------------------------------------
    async def async_prepare(self) -> None:
        """Restore the last known answer and arm the daily timer."""
        stored = await self._store.async_load()
        if stored:
            restored = _result_from_store(stored, self.plate, self.jurisdiction)
            if restored is not None:
                self.data = restored
                self.last_checked = _parse_dt(stored.get("last_checked"))
                self._last_run_date = (
                    self.last_checked.date() if self.last_checked else None
                )
                self.async_set_updated_data(restored)

        check_time = self.check_time
        self._unsub_daily = async_track_time_change(
            self.hass,
            self._async_scheduled_tick,
            hour=check_time.hour,
            minute=check_time.minute,
            second=check_time.second,
        )
        self.entry.async_on_unload(self.async_shutdown_timers)

    @callback
    def async_shutdown_timers(self) -> None:
        """Cancel every timer this coordinator owns."""
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None
        if self._unsub_jitter is not None:
            self._unsub_jitter()
            self._unsub_jitter = None

    @callback
    def _async_scheduled_tick(self, now: datetime) -> None:
        """Fire at the configured time; run today only if the interval says so."""
        today = dt_util.as_local(now).date()
        anchor = _anchor_date(self.entry)
        if not should_run_on(anchor, today, self.interval_days):
            _LOGGER.debug(
                "%s: not due today (every %s days from %s)",
                self.vehicle_name,
                self.interval_days,
                anchor,
            )
            return

        delay = jitter_seconds(f"{self.jurisdiction}:{self.plate}", self.jitter)
        if delay == 0:
            self.hass.async_create_task(self.async_request_refresh())
            return

        _LOGGER.debug("%s: check due, staggered by %ss", self.vehicle_name, delay)
        if self._unsub_jitter is not None:
            self._unsub_jitter()
        self._unsub_jitter = async_track_point_in_time(
            self.hass, self._async_jittered_run, now + timedelta(seconds=delay)
        )

    @callback
    def _async_jittered_run(self, _now: datetime) -> None:
        """Run the staggered check."""
        self._unsub_jitter = None
        self.hass.async_create_task(self.async_request_refresh())

    # -- the check ----------------------------------------------------------
    async def _async_update_data(self) -> RegoResult:
        """Run one registration check.

        On failure this raises so Home Assistant marks the entities
        unavailable. A failed lookup must never be published as
        "not registered".
        """
        previous = self.data
        config = dict(self.entry.data) | dict(self.entry.options)
        client = AiohttpClient(self._session)

        try:
            result = await self.provider.async_check(client, self.plate, config)
        except RegoError as err:
            self._record_failure(err.reason, str(err))
            raise UpdateFailed(str(err)) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            self._record_failure("connection_error", str(err) or type(err).__name__)
            raise UpdateFailed(f"Could not reach {self.provider.name}: {err}") from err

        self.last_failure = None
        self.last_checked = dt_util.utcnow()
        self._last_run_date = dt_util.as_local(self.last_checked).date()
        await self._async_store(result)
        self._fire_events(result, previous)
        return result

    def _record_failure(self, reason: str, message: str) -> None:
        """Remember a failure and tell listeners the check did not answer."""
        count = self.last_failure.count + 1 if self.last_failure else 1
        self.last_failure = CheckFailure(
            reason=reason, message=message, when=dt_util.utcnow(), count=count
        )
        _LOGGER.warning(
            "%s registration check failed (%s): %s", self.vehicle_name, reason, message
        )
        self.hass.bus.async_fire(
            EVENT_CHECK_FAILED,
            {
                "entry_id": self.entry.entry_id,
                "vehicle_name": self.vehicle_name,
                "plate": self.plate,
                "jurisdiction": self.jurisdiction,
                "reason": reason,
                "error": message,
                "consecutive_failures": count,
            },
        )

    def _fire_events(self, result: RegoResult, previous: RegoResult | None) -> None:
        """Publish the outcome for automations to hang off."""
        today = dt_util.as_local(dt_util.utcnow()).date()
        days = result.days_remaining(today)
        payload = {
            "entry_id": self.entry.entry_id,
            "vehicle_name": self.vehicle_name,
            **result.as_dict(),
            "days_remaining": days,
        }
        self.hass.bus.async_fire(EVENT_CHECKED, payload)

        if previous is not None and previous.status != result.status:
            self.hass.bus.async_fire(
                EVENT_STATUS_CHANGED,
                {**payload, "previous_status": str(previous.status)},
            )

        if days is not None and 0 <= days <= self.warning_days:
            self.hass.bus.async_fire(EVENT_EXPIRING, payload)

    # -- persistence --------------------------------------------------------
    async def _async_store(self, result: RegoResult) -> None:
        """Persist the answer so a restart does not lose it."""
        await self._store.async_save(
            {
                "result": result.as_dict(),
                "last_checked": self.last_checked.isoformat()
                if self.last_checked
                else None,
            }
        )

    async def async_remove_storage(self) -> None:
        """Delete this vehicle's stored result."""
        await self._store.async_remove()


def _anchor_date(entry: ConfigEntry) -> date:
    """Return the date the every-N-days count starts from."""
    raw = entry.options.get("anchor_date")
    if raw:
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            pass
    return dt_util.as_local(dt_util.utcnow()).date()


def _parse_dt(raw: Any) -> datetime | None:
    """Parse a stored ISO timestamp."""
    if not raw:
        return None
    return dt_util.parse_datetime(str(raw))


def _result_from_store(
    stored: dict[str, Any], plate: str, jurisdiction: str
) -> RegoResult | None:
    """Rebuild a result from storage."""
    raw = stored.get("result")
    if not isinstance(raw, dict):
        return None
    expiry_raw = raw.get("expiry")
    expiry: date | None = None
    if expiry_raw:
        try:
            expiry = date.fromisoformat(str(expiry_raw))
        except ValueError:
            expiry = None
    try:
        status = RegoStatus(raw.get("status", "unknown"))
    except ValueError:
        status = RegoStatus.UNKNOWN
    return RegoResult(
        status=status,
        plate=raw.get("plate") or plate,
        jurisdiction=raw.get("jurisdiction") or jurisdiction,
        expiry=expiry,
        make=raw.get("make"),
        model=raw.get("model"),
        colour=raw.get("colour"),
        body_type=raw.get("body_type"),
        vehicle_class=raw.get("vehicle_class"),
        ctp_insurer=raw.get("ctp_insurer"),
        restrictions=list(raw.get("restrictions") or []),
        message=raw.get("message"),
    )
