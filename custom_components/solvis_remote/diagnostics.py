"""Diagnostics support for the Solvis Heating integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_CGI_PROFILES, CONF_ENABLE_CGI
from .coordinator import SolvisDataUpdateCoordinator

REDACT = "****"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data

    # Redact sensitive fields from entry data
    redacted_data = {**entry.data}
    for key in (CONF_PASSWORD, CONF_USERNAME):
        if key in redacted_data:
            redacted_data[key] = REDACT

    # Serialize coordinator data (last successful poll)
    coordinator_data = {}
    if coordinator.data:
        for key, value in coordinator.data.items():
            coordinator_data[key] = {
                "value": value.get("value"),
                "unit": value.get("unit"),
            }

    return {
        "config_entry": {
            "data": redacted_data,
            "options": dict(entry.options),
        },
        "coordinator": {
            "system_id": coordinator.system_id,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
        },
        "cgi_control": {
            "enabled": entry.options.get(CONF_ENABLE_CGI, False),
            "profiles": entry.options.get(CONF_CGI_PROFILES, {}),
        },
        "data": coordinator_data,
    }
