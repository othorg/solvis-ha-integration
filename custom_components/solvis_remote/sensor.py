"""Sensor platform for the Solvis Heating integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SENSOR_DESCRIPTIONS,
    SolvisSensorEntityDescription,
)
from .coordinator import SolvisDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solvis sensor entities from a config entry."""
    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data

    async_add_entities(
        SolvisSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class SolvisSensor(CoordinatorEntity[SolvisDataUpdateCoordinator], SensorEntity):
    """Representation of a Solvis sensor."""

    _attr_has_entity_name = True
    entity_description: SolvisSensorEntityDescription

    def __init__(
        self,
        coordinator: SolvisDataUpdateCoordinator,
        description: SolvisSensorEntityDescription,
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
    def native_value(self) -> float | int | None:
        """Return the current sensor value."""
        entry = self.coordinator.data.get(self.entity_description.solvis_key)
        if entry is None:
            return None
        return entry.get("value")
