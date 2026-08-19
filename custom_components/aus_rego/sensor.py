"""Sensors: status, expiry date, days remaining and when we last checked."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AusRegoConfigEntry, AusRegoCoordinator
from .entity import AusRegoEntity
from .models import RegoStatus


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AusRegoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors for a vehicle."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            StatusSensor(coordinator),
            ExpirySensor(coordinator),
            DaysRemainingSensor(coordinator),
            LastCheckedSensor(coordinator),
        ]
    )


class StatusSensor(AusRegoEntity, SensorEntity):
    """The registration status as a word."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [str(status) for status in RegoStatus]

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str:
        """Return the status, falling back to unknown."""
        if self.coordinator.data is None:
            return str(RegoStatus.UNKNOWN)
        return str(self.coordinator.data.status)

    @property
    def available(self) -> bool:
        """Stay available so the unknown state itself is visible."""
        return True

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose the vehicle details the service returned."""
        result = self.coordinator.data
        if result is None:
            return {}
        return {
            "plate": result.plate,
            "jurisdiction": result.jurisdiction,
            "make": result.make,
            "model": result.model,
            "colour": result.colour,
            "body_type": result.body_type,
            "vehicle_class": result.vehicle_class,
            "ctp_insurer": result.ctp_insurer,
            "restrictions": result.restrictions,
            "message": result.message,
        }


class ExpirySensor(AusRegoEntity, SensorEntity):
    """When the registration expires."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "expiry")

    @property
    def native_value(self) -> datetime | None:
        """Return the expiry as a timezone-aware timestamp."""
        result = self.coordinator.data
        if result is None or result.expiry is None:
            return None
        # Registration lapses at the end of the expiry day, local time.
        return dt_util.start_of_local_day(result.expiry)


class DaysRemainingSensor(AusRegoEntity, SensorEntity):
    """Days until expiry; negative once expired."""

    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "days_remaining")

    @property
    def native_value(self) -> int | None:
        """Return the day count."""
        result = self.coordinator.data
        if result is None:
            return None
        return result.days_remaining(dt_util.as_local(dt_util.utcnow()).date())


class LastCheckedSensor(AusRegoEntity, SensorEntity):
    """When the last successful check ran."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "last_checked")

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last answer."""
        return self.coordinator.last_checked

    @property
    def available(self) -> bool:
        """Always available so you can see a check has gone stale."""
        return True
