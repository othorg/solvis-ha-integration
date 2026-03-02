"""DataUpdateCoordinator for the Solvis Heating integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import SolvisClient, SolvisAuthError, SolvisConnectionError, SolvisPayloadError

logger = logging.getLogger(__name__)


class SolvisDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls a Solvis controller and computes derived values."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SolvisClient,
        scan_interval: int,
        system_id: str,
    ) -> None:
        super().__init__(
            hass,
            logger,
            name="Solvis",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.system_id = system_id

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the controller and compute derived values."""
        try:
            raw_data = await self.hass.async_add_executor_job(self.client.fetch_data)
        except SolvisAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
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
