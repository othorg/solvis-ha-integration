"""Select platform for the Solvis Heating integration (CGI control)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import SolvisConnectionError
from .const import (
    CONF_CGI_PROFILES,
    CONF_ENABLE_CGI,
    DEFAULT_CGI_PROFILES,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import SolvisDataUpdateCoordinator

logger = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solvis CGI select entities from a config entry."""
    if not entry.options.get(CONF_ENABLE_CGI, False):
        return

    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data
    profiles = entry.options.get(CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES)

    async_add_entities(
        SolvisCgiSelect(coordinator, profile_key, profile)
        for profile_key, profile in profiles.items()
    )


class SolvisCgiSelect(
    CoordinatorEntity[SolvisDataUpdateCoordinator],
    SelectEntity,
    RestoreEntity,
):
    """Representation of a Solvis CGI command select entity.

    Optimistic entity — no feedback from the device. The state is set
    only after a successful CGI command execution.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolvisDataUpdateCoordinator,
        profile_key: str,
        profile: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._profile_key = profile_key
        self._profile = profile

        system_id = coordinator.system_id
        self._attr_unique_id = f"{system_id}_cgi_{profile_key}"
        self._attr_name = profile["name"]
        self._attr_icon = profile.get("icon")

        # Use labels for display, map back to keys internally
        self._key_to_label: dict[str, str] = {
            k: opt.get("label", k) for k, opt in profile["options"].items()
        }
        self._label_to_key: dict[str, str] = {
            v: k for k, v in self._key_to_label.items()
        }
        self._attr_options = list(self._key_to_label.values())
        self._attr_current_option = None

        device_group = profile.get("device_group", "CGI Control")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{system_id}_{device_group}")},
            name=f"Solvis {device_group}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous state after HA restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state

    async def async_select_option(self, option: str) -> None:
        """Execute CGI command sequence for the selected option.

        The option parameter is the label shown in the UI.
        We map it back to the internal key for the coordinator.

        Sets state optimistically only on success.
        SolvisAuthError is handled by the coordinator
        (raised as ConfigEntryAuthFailed → triggers reauth).
        """
        # Map label back to internal key
        option_key = self._label_to_key.get(option, option)
        try:
            await self.coordinator.async_execute_cgi_command(
                self._profile_key, option_key
            )
        except SolvisConnectionError as err:
            raise HomeAssistantError(
                f"CGI command failed: {err}"
            ) from err
        # Only set state on success (using the label for display)
        self._attr_current_option = option
        self.async_write_ha_state()
