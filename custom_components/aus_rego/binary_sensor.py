"""Binary sensors: the yes/no answer, and whether the check itself is working."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AusRegoConfigEntry, AusRegoCoordinator
from .entity import AusRegoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AusRegoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors for a vehicle."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RegisteredBinarySensor(coordinator),
            ExpiringBinarySensor(coordinator),
            CheckFailingBinarySensor(coordinator),
        ]
    )


class RegisteredBinarySensor(AusRegoEntity, BinarySensorEntity):
    """On when the vehicle is registered.

    Deliberately has no device class: ``problem`` would invert the meaning and
    make automations read backwards.

    When a check fails this entity goes *unavailable* rather than off, so an
    automation can never flash a light because a government website was down.
    """

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "registered")

    @property
    def is_on(self) -> bool | None:
        """Return whether the vehicle is registered."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.registered

    @property
    def available(self) -> bool:
        """Only report a state when the last check actually answered."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.registered is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the detail behind the yes/no."""
        result = self.coordinator.data
        if result is None:
            return {}
        today = dt_util.as_local(dt_util.utcnow()).date()
        return {
            "status": str(result.status),
            "plate": result.plate,
            "jurisdiction": result.jurisdiction,
            "expiry": result.expiry.isoformat() if result.expiry else None,
            "days_remaining": result.days_remaining(today),
            "make": result.make,
            "model": result.model,
            "colour": result.colour,
            "message": result.message,
        }


class ExpiringBinarySensor(AusRegoEntity, BinarySensorEntity):
    """On when registration has expired or is inside the warning window."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "expiring_soon")

    @property
    def is_on(self) -> bool | None:
        """Return whether the expiry is near or past."""
        result = self.coordinator.data
        if result is None or result.expiry is None:
            return None
        days = result.days_remaining(dt_util.as_local(dt_util.utcnow()).date())
        if days is None:
            return None
        return days <= self.coordinator.warning_days

    @property
    def available(self) -> bool:
        """Needs an expiry date to mean anything."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.expiry is not None
        )


class CheckFailingBinarySensor(AusRegoEntity, BinarySensorEntity):
    """On when the last check could not get an answer.

    Stays available even when the check is failing — that is the whole point of
    it — so you can be told the difference between "not registered" and
    "we could not find out".
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "check_failing")

    @property
    def is_on(self) -> bool:
        """Return whether the most recent check failed."""
        return self.coordinator.last_failure is not None

    @property
    def available(self) -> bool:
        """Always available; it reports on the check, not on the vehicle."""
        return True

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Describe the failure so it can be acted on."""
        failure = self.coordinator.last_failure
        if failure is None:
            return {"reason": None, "error": None, "consecutive_failures": 0}
        return {
            "reason": failure.reason,
            "error": failure.message,
            "consecutive_failures": failure.count,
            "since": failure.when.isoformat(),
        }
