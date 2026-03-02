"""The Solvis Heating integration."""

from __future__ import annotations

from functools import partial
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .client import SolvisClient, SolvisAuthError, SolvisConnectionError, SolvisPayloadError
from .const import (
    CONF_REALM,
    CONF_SCAN_INTERVAL,
    DEFAULT_REALM,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    PLATFORMS,
)
from .coordinator import SolvisDataUpdateCoordinator

logger = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Solvis Heating from a config entry."""
    # Build urllib opener in executor to avoid blocking-loop SSL path loading.
    client = await hass.async_add_executor_job(
        partial(
            SolvisClient,
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            realm=entry.data.get(CONF_REALM, DEFAULT_REALM),
            timeout=DEFAULT_TIMEOUT,
        )
    )

    # Initial fetch to validate connection and extract system_id
    try:
        initial_data = await hass.async_add_executor_job(client.fetch_data)
    except SolvisAuthError as err:
        raise ConfigEntryAuthFailed(
            f"Authentication failed for {entry.data[CONF_HOST]}"
        ) from err
    except SolvisConnectionError as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to {entry.data[CONF_HOST]}"
        ) from err
    except SolvisPayloadError as err:
        raise ConfigEntryNotReady(
            f"Invalid payload from {entry.data[CONF_HOST]}: {err}"
        ) from err

    # Extract stable system identifier from the Solvis payload
    system_raw = initial_data.get("system", {}).get("raw", "")
    system_id = system_raw if system_raw else entry.data[CONF_HOST]

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = SolvisDataUpdateCoordinator(
        hass, client, scan_interval, system_id, entry
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Solvis config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the integration.

    A full reload is required because CGI profile changes may add or
    remove select entities, which requires a complete platform teardown
    and re-setup.
    """
    await hass.config_entries.async_reload(entry.entry_id)
