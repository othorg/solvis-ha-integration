"""Tests for the Solvis Heating integration setup (__init__.py)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.solvis_remote.const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from custom_components.solvis_remote.client import (
    SolvisAuthError,
    SolvisConnectionError,
    SolvisPayloadError,
)


MOCK_CONFIG_DATA = {
    "host": "192.168.1.100",
    "username": "admin",
    "password": "secret",
    "realm": "SolvisRemote",
}

MOCK_FETCH_RESULT = {
    "system": {"title": "Systemnummer", "value": None, "unit": None, "raw": "3412"},
    "s1": {"title": "Warmwasserpuffer", "value": 24.2, "unit": "C", "raw": "F200"},
    "s5": {"title": "Vorlauftemperatur", "value": 32.6, "unit": "C", "raw": "4601"},
    "s6": {"title": "Ruecklauftemperatur", "value": 26.4, "unit": "C", "raw": "0801"},
    "ao1": {"title": "Brennermodulation", "value": 50.2, "unit": None, "raw": "80"},
    "a12": {"title": "Nachheizung", "value": "on", "unit": None, "raw": "01"},
}


def _patch_fetch(side_effect=None, return_value=None):
    if return_value is None:
        return_value = MOCK_FETCH_RESULT
    return patch(
        "custom_components.solvis_remote.client.SolvisClient.fetch_data",
        side_effect=side_effect,
        return_value=return_value,
    )


class TestSetupEntry:
    """Test async_setup_entry error paths."""

    async def test_setup_auth_error_triggers_reauth(self, hass: HomeAssistant) -> None:
        """SolvisAuthError during setup must trigger reauth (SETUP_ERROR state)."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(side_effect=SolvisAuthError("401")):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # HA catches ConfigEntryAuthFailed and sets SETUP_ERROR + creates reauth flow
        assert entry.state is ConfigEntryState.SETUP_ERROR

    async def test_setup_connection_error(self, hass: HomeAssistant) -> None:
        """SolvisConnectionError during setup must raise ConfigEntryNotReady."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(side_effect=SolvisConnectionError("timeout")):
            await hass.config_entries.async_setup(entry.entry_id)
            assert entry.state is ConfigEntryState.SETUP_RETRY

    async def test_setup_payload_error_retries(self, hass: HomeAssistant) -> None:
        """SolvisPayloadError during setup must trigger retry (ConfigEntryNotReady)."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(side_effect=SolvisPayloadError("too short")):
            await hass.config_entries.async_setup(entry.entry_id)
            assert entry.state is ConfigEntryState.SETUP_RETRY

    async def test_setup_and_unload(self, hass: HomeAssistant) -> None:
        """Test successful setup and clean unload."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data is not None

        # Unload
        with _patch_fetch():
            await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.NOT_LOADED


class TestUpdateListener:
    """Test options update listener."""

    async def test_scan_interval_update(self, hass: HomeAssistant) -> None:
        """Changing scan_interval via options must update coordinator interval."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = entry.runtime_data
        assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

        # Simulate options update
        with _patch_fetch():
            hass.config_entries.async_update_entry(
                entry, options={CONF_SCAN_INTERVAL: 120}
            )
            await hass.async_block_till_done()

        assert coordinator.update_interval == timedelta(seconds=120)

    async def test_connection_params_update(self, hass: HomeAssistant) -> None:
        """Changing host/credentials via data must recreate the client."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = entry.runtime_data
        old_client = coordinator.client
        assert old_client.host == "192.168.1.100"

        # Simulate data + options update (as the options flow does)
        new_data = {**MOCK_CONFIG_DATA, "host": "10.0.0.50"}
        with _patch_fetch():
            hass.config_entries.async_update_entry(
                entry, data=new_data, options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}
            )
            await hass.async_block_till_done()

        # The listener must have replaced the client
        assert coordinator.client is not old_client
        assert coordinator.client.host == "10.0.0.50"
