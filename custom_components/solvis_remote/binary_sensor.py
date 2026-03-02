"""Binary sensor platform for the Solvis Heating integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    BINARY_SENSOR_DESCRIPTIONS,
    SolvisBinarySensorEntityDescription,
)
from .coordinator import SolvisDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solvis binary sensor entities from a config entry."""
    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data

    async_add_entities(
        SolvisBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class SolvisBinarySensor(CoordinatorEntity[SolvisDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a Solvis binary sensor (pump/burner state)."""

    _attr_has_entity_name = True
    entity_description: SolvisBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: SolvisDataUpdateCoordinator,
        description: SolvisBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        system_id = coordinator.system_id
        self._attr_unique_id = f"{system_id}_{description.solvis_key}"
        self._attr_translation_key = description.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{system_id}_{description.device_group}")},
            name=f"Solvis {description.device_group}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        entry = self.coordinator.data.get(self.entity_description.solvis_key)
        if entry is None:
            return None
        value = entry.get("value")
        if value is None:
            return None
        return "on" in str(value)
