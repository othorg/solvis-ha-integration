"""Tests for the Solvis Heating diagnostics."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.solvis_remote.const import DOMAIN
from custom_components.solvis_remote.diagnostics import (
    async_get_config_entry_diagnostics,
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


def _patch_fetch():
    return patch(
        "custom_components.solvis_remote.client.SolvisClient.fetch_data",
        return_value=MOCK_FETCH_RESULT,
    )


class TestDiagnostics:
    """Test diagnostics output."""

    async def test_credentials_redacted(self, hass: HomeAssistant) -> None:
        """Password and username must be masked in diagnostics."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, entry)

        assert diag["config_entry"]["data"]["password"] == "****"
        assert diag["config_entry"]["data"]["username"] == "****"
        assert diag["config_entry"]["data"]["host"] == "192.168.1.100"

    async def test_coordinator_info_present(self, hass: HomeAssistant) -> None:
        """Diagnostics must include coordinator metadata."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, entry)

        assert diag["coordinator"]["system_id"] == "3412"
        assert diag["coordinator"]["last_update_success"] is True
        assert "data" in diag
