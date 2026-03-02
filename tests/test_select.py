"""Tests for the Solvis CGI select platform."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.solvis_remote.const import (
    CONF_CGI_PROFILES,
    CONF_ENABLE_CGI,
    DEFAULT_CGI_PROFILES,
    DOMAIN,
)
from custom_components.solvis_remote.client import SolvisConnectionError


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


class TestSelectEntityCreation:
    """Test that select entities are created/not created based on config."""

    async def test_no_entities_when_cgi_disabled(self, hass: HomeAssistant) -> None:
        """No select entities when enable_cgi_control is False."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: False, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # No select entities should exist
        select_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("select.")
        ]
        assert len(select_entities) == 0

    async def test_entities_created_when_cgi_enabled(self, hass: HomeAssistant) -> None:
        """Select entities are created when enable_cgi_control is True."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: True, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # One select entity for the default heating_mode profile
        select_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("select.")
        ]
        assert len(select_entities) == 1

    async def test_entity_has_correct_options(self, hass: HomeAssistant) -> None:
        """Select entity must have the correct option keys."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: True, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # Find the select entity
        select_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("select.")
        ]
        assert len(select_entities) == 1
        state = select_entities[0]

        options = state.attributes.get("options", [])
        assert "Off" in options
        assert "Auto" in options
        assert "Day" in options
        assert "Night" in options

    async def test_entity_uses_attr_name_not_translation_key(self, hass: HomeAssistant) -> None:
        """Entity name must come from profile['name'], not translation_key."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: True, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        select_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("select.")
        ]
        assert len(select_entities) == 1
        state = select_entities[0]

        # friendly_name should contain "Heating Mode" from the profile
        friendly_name = state.attributes.get("friendly_name", "")
        assert "Heating Mode" in friendly_name


class TestSelectOptionExecution:
    """Test select option execution and optimistic state."""

    async def test_select_option_success_updates_state(self, hass: HomeAssistant) -> None:
        """Successful option selection must update state optimistically."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: True, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # Mock the CGI sequence execution
        coordinator = entry.runtime_data
        with patch.object(
            coordinator, "async_execute_cgi_command", new_callable=AsyncMock
        ):
            await hass.services.async_call(
                "select",
                "select_option",
                {
                    "entity_id": [
                        s.entity_id
                        for s in hass.states.async_all()
                        if s.entity_id.startswith("select.")
                    ][0],
                    "option": "Auto",
                },
                blocking=True,
            )

        select_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("select.")
        ]
        assert select_entities[0].state == "Auto"

    async def test_select_option_failure_keeps_old_state(self, hass: HomeAssistant) -> None:
        """Connection error must NOT update state."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=MOCK_CONFIG_DATA,
            options={CONF_ENABLE_CGI: True, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
        )
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # Mock the CGI sequence to fail
        coordinator = entry.runtime_data
        with patch.object(
            coordinator,
            "async_execute_cgi_command",
            new_callable=AsyncMock,
            side_effect=SolvisConnectionError("timeout"),
        ):
            entity_id = [
                s.entity_id
                for s in hass.states.async_all()
                if s.entity_id.startswith("select.")
            ][0]

            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": entity_id, "option": "Day"},
                    blocking=True,
                )

        # State should NOT have changed to "day"
        state = hass.states.get(entity_id)
        assert state.state != "Day"
