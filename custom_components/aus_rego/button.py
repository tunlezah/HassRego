"""A button to run the check immediately."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import AusRegoConfigEntry, AusRegoCoordinator
from .entity import AusRegoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AusRegoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the check-now button."""
    async_add_entities([CheckNowButton(entry.runtime_data)])


class CheckNowButton(AusRegoEntity, ButtonEntity):
    """Run the registration check on demand."""

    def __init__(self, coordinator: AusRegoCoordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "check_now")

    @property
    def available(self) -> bool:
        """Always pressable, including after a failed check."""
        return True

    async def async_press(self) -> None:
        """Check now."""
        await self.coordinator.async_request_refresh()
