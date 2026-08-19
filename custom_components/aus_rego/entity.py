"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import AusRegoCoordinator
from .providers import get_provider


class AusRegoEntity(CoordinatorEntity[AusRegoCoordinator]):
    """Base entity: one device per vehicle."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AusRegoCoordinator, key: str) -> None:
        """Attach the entity to its vehicle device."""
        super().__init__(coordinator)
        provider = get_provider(coordinator.jurisdiction)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.vehicle_name,
            manufacturer=MANUFACTURER,
            model=provider.name,
            serial_number=coordinator.plate,
            configuration_url=provider.check_url or None,
        )
