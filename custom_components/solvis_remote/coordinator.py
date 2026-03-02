"""DataUpdateCoordinator for the Solvis Heating integration."""

from __future__ import annotations

import asyncio
import logging
import time as time_mod
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import SolvisClient, SolvisAuthError, SolvisConnectionError, SolvisPayloadError
from .const import CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES

logger = logging.getLogger(__name__)


class SolvisDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls a Solvis controller and computes derived values."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SolvisClient,
        scan_interval: int,
        system_id: str,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            logger,
            name="Solvis",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.system_id = system_id
        self.config_entry = config_entry
        self._command_lock = asyncio.Lock()
        self._last_command_time: float = 0

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the controller and compute derived values."""
        async with self._command_lock:
            try:
                raw_data = await self.hass.async_add_executor_job(self.client.fetch_data)
            except SolvisAuthError as err:
                raise ConfigEntryAuthFailed(
                    f"Authentication failed: {err}"
                ) from err
            except SolvisConnectionError as err:
                raise UpdateFailed(f"Connection error: {err}") from err
            except SolvisPayloadError as err:
                raise UpdateFailed(f"Invalid payload: {err}") from err

        # Compute derived values
        data: dict[str, Any] = {}
        for key, entry in raw_data.items():
            data[key] = entry

        self._compute_derived(data)
        return data

    async def async_execute_cgi_command(
        self, profile_key: str, option_key: str
    ) -> None:
        """Execute a CGI command sequence for the given profile and option.

        Raises:
            HomeAssistantError: If profile or option is unknown.
            ConfigEntryAuthFailed: If authentication fails (triggers reauth).
            SolvisConnectionError: If a network error occurs.
        """
        profiles = self.config_entry.options.get(
            CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES
        )
        profile = profiles.get(profile_key)
        if profile is None:
            raise HomeAssistantError(f"Unknown CGI profile: {profile_key}")
        option = profile["options"].get(option_key)
        if option is None:
            raise HomeAssistantError(
                f"Unknown option '{option_key}' in profile '{profile_key}'"
            )

        sequence = {
            "wakeup_count": profile["wakeup_count"],
            "wakeup_delay": profile["wakeup_delay"],
            "x": option["x"],
            "y": option["y"],
            "reset_touch": profile.get("reset_touch"),
        }

        async with self._command_lock:
            # Cooldown: at least 500ms since last command
            now = time_mod.monotonic()
            elapsed = now - self._last_command_time
            if elapsed < 0.5:
                await asyncio.sleep(0.5 - elapsed)
            try:
                await self.hass.async_add_executor_job(
                    self.client.execute_cgi_sequence, sequence
                )
            except SolvisAuthError as err:
                raise ConfigEntryAuthFailed(
                    f"CGI auth failed: {err}"
                ) from err
            self._last_command_time = time_mod.monotonic()

    def _compute_derived(self, data: dict[str, Any]) -> None:
        """Add computed sensors (delta_s5s6, brennerleistung) to data dict."""
        s5_val = data.get("s5", {}).get("value")
        s6_val = data.get("s6", {}).get("value")

        if s5_val is not None and s6_val is not None:
            data["delta_s5s6"] = {
                "title": "Delta Vorlauf/Ruecklauf",
                "value": round(s5_val - s6_val, 1),
                "unit": "K",
                "raw": None,
            }
        else:
            data["delta_s5s6"] = {"title": "Delta Vorlauf/Ruecklauf", "value": None, "unit": "K", "raw": None}

        a12_val = data.get("a12", {}).get("value")
        ao1_val = data.get("ao1", {}).get("value")

        if a12_val == "on" and ao1_val is not None:
            data["brennerleistung"] = {
                "title": "Brennerleistung",
                "value": round(5.0 + ao1_val * 15.0 / 100.0, 2),
                "unit": "kW",
                "raw": None,
            }
        else:
            data["brennerleistung"] = {"title": "Brennerleistung", "value": 0.0, "unit": "kW", "raw": None}
