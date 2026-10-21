"""The Solvis Heating integration."""

from __future__ import annotations

from functools import partial
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType

from .client import (
    SolvisClient,
    SolvisAuthError,
    SolvisBusyError,
    SolvisConnectionError,
    SolvisPayloadError,
)
from .const import (
    BUTTONS,
    CONF_ENABLE_CGI,
    CONF_REALM,
    CONF_SCAN_INTERVAL,
    DEFAULT_REALM,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DOMAIN,
    PLATFORMS,
    SERVICE_PRESS_BUTTON,
    SERVICE_TOUCH,
    SERVICE_TOUCH_DOWN,
    SERVICE_TOUCH_UP,
    TOUCH_MAX_HOLD,
    TOUCH_MIN_HOLD,
    TOUCH_SCALE,
)
from .coordinator import SolvisDataUpdateCoordinator

logger = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Services target the display camera; it identifies the controller.
_TARGET = {vol.Required(ATTR_ENTITY_ID): vol.All(cv.entity_ids, vol.Length(min=1, max=1))}
_X = vol.All(vol.Coerce(int), vol.Range(min=0, max=DISPLAY_WIDTH * TOUCH_SCALE - 1))
_Y = vol.All(vol.Coerce(int), vol.Range(min=0, max=DISPLAY_HEIGHT * TOUCH_SCALE - 1))
TOUCH_SCHEMA = vol.Schema(
    {
        **_TARGET,
        vol.Required("x"): _X,
        vol.Required("y"): _Y,
        vol.Optional("duration", default=TOUCH_MIN_HOLD): vol.All(
            vol.Coerce(float), vol.Range(min=TOUCH_MIN_HOLD, max=TOUCH_MAX_HOLD)
        ),
    }
)
# A frontend passes the same gesture_id to touch_down and touch_up, so a
# release can only end the touch it belongs to.
_GESTURE_ID = {vol.Optional("gesture_id"): vol.All(cv.string, vol.Length(max=64))}
TOUCH_DOWN_SCHEMA = vol.Schema(
    {**_TARGET, **_GESTURE_ID, vol.Required("x"): _X, vol.Required("y"): _Y}
)
TOUCH_UP_SCHEMA = vol.Schema({**_TARGET, **_GESTURE_ID})
PRESS_BUTTON_SCHEMA = vol.Schema({**_TARGET, vol.Required("button"): vol.In(BUTTONS)})


@callback
def _coordinator_for(hass: HomeAssistant, call: ServiceCall) -> SolvisDataUpdateCoordinator:
    """Resolve the targeted display camera to its loaded, CGI-enabled entry."""
    entity_id = call.data[ATTR_ENTITY_ID][0]
    reg_entry = er.async_get(hass).async_get(entity_id)
    if reg_entry is None or reg_entry.platform != DOMAIN or reg_entry.domain != "camera":
        raise ServiceValidationError(f"{entity_id} is not a Solvis display")
    entry = hass.config_entries.async_get_entry(reg_entry.config_entry_id or "")
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(f"The Solvis entry of {entity_id} is not loaded")
    if not entry.options.get(CONF_ENABLE_CGI, False):
        raise ServiceValidationError(
            "CGI control is disabled in the Solvis options; enable it to operate the display"
        )
    return entry.runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the remote display services (admin only)."""

    async def _touch(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_touch(
            call.data["x"], call.data["y"], call.data["duration"]
        )

    async def _touch_down(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_touch_down(
            call.data["x"], call.data["y"], call.data.get("gesture_id")
        )

    async def _touch_up(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_touch_up(call.data.get("gesture_id"))

    async def _press_button(call: ServiceCall) -> None:
        await _coordinator_for(hass, call).async_press_button(call.data["button"])

    for name, handler, schema in (
        (SERVICE_TOUCH, _touch, TOUCH_SCHEMA),
        (SERVICE_TOUCH_DOWN, _touch_down, TOUCH_DOWN_SCHEMA),
        (SERVICE_TOUCH_UP, _touch_up, TOUCH_UP_SCHEMA),
        (SERVICE_PRESS_BUTTON, _press_button, PRESS_BUTTON_SCHEMA),
    ):
        async_register_admin_service(hass, DOMAIN, name, handler, schema)
    return True


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
    except SolvisBusyError as err:
        # Single-session controller busy with another client -> retry later,
        # this is not a credentials problem.
        raise ConfigEntryNotReady(
            f"{entry.data[CONF_HOST]} is busy with another session"
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
