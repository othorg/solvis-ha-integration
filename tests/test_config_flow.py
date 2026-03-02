"""Tests for the Solvis Heating config flow."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.solvis_remote.const import (
    CONF_CGI_PROFILES,
    CONF_ENABLE_CGI,
    CONF_REALM,
    CONF_SCAN_INTERVAL,
    DEFAULT_CGI_PROFILES,
    DEFAULT_REALM,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.solvis_remote.client import (
    SolvisAuthError,
    SolvisConnectionError,
    SolvisPayloadError,
)


MOCK_USER_INPUT = {
    "host": "192.168.1.100",
    "username": "admin",
    "password": "secret",
    "realm": DEFAULT_REALM,
    "scan_interval": DEFAULT_SCAN_INTERVAL,
}

MOCK_FETCH_RESULT = {
    "system": {"title": "Systemnummer", "value": None, "unit": None, "raw": "3412"},
    "s1": {"title": "Warmwasserpuffer", "value": 24.2, "unit": "C", "raw": "F200"},
}


def _patch_fetch(side_effect=None, return_value=None):
    """Patch SolvisClient.fetch_data."""
    if return_value is None:
        return_value = MOCK_FETCH_RESULT
    return patch(
        "custom_components.solvis_remote.config_flow.SolvisClient.fetch_data",
        side_effect=side_effect,
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# Config Flow tests
# ---------------------------------------------------------------------------

class TestConfigFlow:
    """Test the initial config flow (user step)."""

    async def test_form_shown(self, hass: HomeAssistant) -> None:
        """Test that the form is shown on first access."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_successful_setup(self, hass: HomeAssistant) -> None:
        """Test successful config flow with valid credentials."""
        with _patch_fetch():
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Solvis (192.168.1.100)"
        assert result["data"]["host"] == "192.168.1.100"
        assert result["data"]["username"] == "admin"
        assert result["data"]["password"] == "secret"
        assert result["options"]["scan_interval"] == DEFAULT_SCAN_INTERVAL

    async def test_auth_error(self, hass: HomeAssistant) -> None:
        """Test config flow with invalid credentials."""
        with _patch_fetch(side_effect=SolvisAuthError("401")):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_connection_error(self, hass: HomeAssistant) -> None:
        """Test config flow with unreachable host."""
        with _patch_fetch(side_effect=SolvisConnectionError("timeout")):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


# ---------------------------------------------------------------------------
# Options Flow tests
# ---------------------------------------------------------------------------

class TestOptionsFlow:
    """Test the options flow for changing settings."""

    async def _create_entry(self, hass: HomeAssistant):
        """Helper: create a config entry via the config flow."""
        with _patch_fetch():
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )
        return result["result"]

    async def test_options_flow_shows_menu(self, hass: HomeAssistant) -> None:
        """Options flow must show a menu with settings and CGI management."""
        entry = await self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.MENU
        assert "settings" in result["menu_options"]
        assert "cgi_menu" in result["menu_options"]

    async def test_settings_change_interval(self, hass: HomeAssistant) -> None:
        """Test changing scan interval via settings step."""
        entry = await self._create_entry(hass)

        # Navigate to menu
        result = await hass.config_entries.options.async_init(entry.entry_id)

        # Select settings
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "settings"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "settings"

        # Submit settings
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL: 120, CONF_ENABLE_CGI: False},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_SCAN_INTERVAL] == 120

    async def test_settings_enable_cgi(self, hass: HomeAssistant) -> None:
        """Test enabling CGI control via settings step."""
        entry = await self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "settings"},
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_ENABLE_CGI: True},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.options[CONF_ENABLE_CGI] is True

    async def test_no_connection_params_in_options(self, hass: HomeAssistant) -> None:
        """Options flow settings must NOT contain host/username/password fields."""
        entry = await self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": "settings"},
        )

        # Check schema keys
        schema_keys = [str(k) for k in result["data_schema"].schema.keys()]
        assert "host" not in schema_keys
        assert "username" not in schema_keys
        assert "password" not in schema_keys


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    """Test duplicate detection by system_id (not just host)."""

    async def test_duplicate_same_system_id_different_host(self, hass: HomeAssistant) -> None:
        """Same system_id via different host must be rejected."""
        # First entry via IP
        with _patch_fetch():
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        # Second entry via DNS name but same system_id "3412"
        dns_input = {**MOCK_USER_INPUT, "host": "solvis.local"}
        with _patch_fetch():
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], dns_input
            )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


# ---------------------------------------------------------------------------
# Payload error tests
# ---------------------------------------------------------------------------

class TestPayloadError:
    """Test SolvisPayloadError handling in config flow."""

    async def test_payload_error_shows_invalid_payload(self, hass: HomeAssistant) -> None:
        """SolvisPayloadError must show invalid_payload error."""
        with _patch_fetch(side_effect=SolvisPayloadError("too short")):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], MOCK_USER_INPUT
            )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_payload"}
