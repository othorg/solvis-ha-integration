"""Tests for the Solvis DataUpdateCoordinator."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.solvis_remote.const import DOMAIN, CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES
from custom_components.solvis_remote.coordinator import SolvisDataUpdateCoordinator
from custom_components.solvis_remote.client import (
    SolvisClient,
    SolvisAuthError,
    SolvisBusyError,
    SolvisConnectionError,
    SolvisPayloadError,
)


def _make_mock_data() -> dict:
    """Return mock data as SolvisClient.fetch_data would return."""
    return {
        "system": {"title": "Systemnummer", "value": None, "unit": None, "raw": "3412"},
        "s1": {"title": "Warmwasserpuffer", "value": 24.2, "unit": "C", "raw": "F200"},
        "s5": {"title": "Vorlauftemperatur", "value": 32.6, "unit": "C", "raw": "4601"},
        "s6": {"title": "Ruecklauftemperatur", "value": 26.4, "unit": "C", "raw": "0801"},
        "ao1": {"title": "Brennermodulation", "value": 50.2, "unit": None, "raw": "80"},
        "a12": {"title": "Nachheizung", "value": "on", "unit": None, "raw": "01"},
    }


def _make_mock_entry():
    """Return a mock config entry with options."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100", "username": "admin", "password": "secret"},
        options={CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
    )


def _make_mock_entry_with_profiles(profiles: dict):
    """Return a mock config entry with custom CGI profiles."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.168.1.100", "username": "admin", "password": "secret"},
        options={CONF_CGI_PROFILES: profiles},
    )


class TestCoordinatorDerivedValues:
    """Test computed values (delta_s5s6, brennerleistung)."""

    async def test_delta_s5s6(self, hass: HomeAssistant) -> None:
        """Test that delta_s5s6 = s5 - s6."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        data = await coordinator._async_update_data()

        assert "delta_s5s6" in data
        # 32.6 - 26.4 = 6.2
        assert data["delta_s5s6"]["value"] == pytest.approx(6.2, abs=0.1)

    async def test_brennerleistung_on(self, hass: HomeAssistant) -> None:
        """Test brennerleistung when burner is on."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        data = await coordinator._async_update_data()

        assert "brennerleistung" in data
        # 5.0 + 50.2 * 15.0 / 100.0 = 5.0 + 7.53 = 12.53
        assert data["brennerleistung"]["value"] == pytest.approx(12.53, abs=0.01)

    async def test_brennerleistung_off(self, hass: HomeAssistant) -> None:
        """Test brennerleistung when burner is off."""
        client = MagicMock(spec=SolvisClient)
        mock_data = _make_mock_data()
        mock_data["a12"]["value"] = "off"
        client.fetch_data.return_value = mock_data
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        data = await coordinator._async_update_data()

        assert data["brennerleistung"]["value"] == 0.0


class TestCoordinatorErrors:
    """Test that client errors are mapped correctly."""

    async def test_auth_error_triggers_reauth(self, hass: HomeAssistant) -> None:
        """SolvisAuthError must raise ConfigEntryAuthFailed to trigger reauth."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisAuthError("401")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(ConfigEntryAuthFailed, match="Authentication"):
            await coordinator._async_update_data()

    async def test_busy_403_fails_fast_without_reauth(
        self, hass: HomeAssistant
    ) -> None:
        """Polling: 403 -> UpdateFailed on the spot, never ConfigEntryAuthFailed.

        Escalating it to reauth is what forced manual re-entry of credentials
        that were correct all along (seen live on 2026-09-19). No retry here:
        the next poll is one scan_interval away, and retrying would only add
        contention for the controller's single session.
        """
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisBusyError("403")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(UpdateFailed, match="busy"):
            await coordinator._async_update_data()
        assert client.fetch_data.call_count == 1

    async def test_cgi_busy_403_retries_then_succeeds(
        self, hass: HomeAssistant
    ) -> None:
        """A CGI command must survive the session being briefly taken."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        client.execute_cgi_sequence.side_effect = [SolvisBusyError("403"), None]
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with patch("custom_components.solvis_remote.coordinator._busy_delay", return_value=0):
            await coordinator.async_execute_cgi_command("heating_mode", "auto")

        assert client.execute_cgi_sequence.call_count == 2

    async def test_cgi_busy_403_never_triggers_reauth(
        self, hass: HomeAssistant
    ) -> None:
        """Persistent 403 on a command must not force a reauth either."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        client.execute_cgi_sequence.side_effect = SolvisBusyError("403")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with patch("custom_components.solvis_remote.coordinator._busy_delay", return_value=0):
            with pytest.raises(HomeAssistantError, match="busy"):
                await coordinator.async_execute_cgi_command("heating_mode", "auto")
        assert client.execute_cgi_sequence.call_count == 3

    async def test_cgi_lost_response_is_not_retried(
        self, hass: HomeAssistant
    ) -> None:
        """A request may take effect and still fail while reading the response.

        That surfaces as SolvisConnectionError, not 403, and must escape the
        retry loop -- retrying could re-apply a touch that already landed.
        """
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        client.execute_cgi_sequence.side_effect = SolvisConnectionError(
            "timed out reading response"
        )
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with patch(
            "custom_components.solvis_remote.coordinator._busy_delay",
            return_value=0,
        ):
            with pytest.raises(SolvisConnectionError):
                await coordinator.async_execute_cgi_command("heating_mode", "auto")

        assert client.execute_cgi_sequence.call_count == 1

    async def test_cgi_busy_then_timeout_stops(self, hass: HomeAssistant) -> None:
        """403 then a transport error: retry once, then give up. No third try."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        client.execute_cgi_sequence.side_effect = [
            SolvisBusyError("403"),
            SolvisConnectionError("timed out"),
        ]
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with patch(
            "custom_components.solvis_remote.coordinator._busy_delay",
            return_value=0,
        ):
            with pytest.raises(SolvisConnectionError):
                await coordinator.async_execute_cgi_command("heating_mode", "auto")

        assert client.execute_cgi_sequence.call_count == 2

    async def test_cgi_partial_sequence_is_not_replayed(
        self, hass: HomeAssistant
    ) -> None:
        """A 403 mid-sequence must abort, not replay the touches.

        The touch that changes the value may already have reached the panel.
        For a momentary action (e.g. "Warmwasser aktiv nachheizen") replaying
        it would trigger it a second time.
        """
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        client.execute_cgi_sequence.side_effect = SolvisBusyError(
            "403", partial=True
        )
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with patch(
            "custom_components.solvis_remote.coordinator._busy_delay",
            return_value=0,
        ):
            with pytest.raises(HomeAssistantError, match="mid-sequence"):
                await coordinator.async_execute_cgi_command("heating_mode", "auto")

        # exactly one attempt, no replay
        assert client.execute_cgi_sequence.call_count == 1

    async def test_connection_error(self, hass: HomeAssistant) -> None:
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisConnectionError("timeout")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(UpdateFailed, match="Connection"):
            await coordinator._async_update_data()

    async def test_payload_error(self, hass: HomeAssistant) -> None:
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisPayloadError("too short")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(UpdateFailed, match="payload"):
            await coordinator._async_update_data()


class TestCoordinatorCgiCommand:
    """Test CGI command execution."""

    async def test_execute_cgi_command_success(self, hass: HomeAssistant) -> None:
        """Test successful CGI command execution."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        await coordinator.async_execute_cgi_command("heating_mode", "auto")

        client.execute_cgi_sequence.assert_called_once()
        call_args = client.execute_cgi_sequence.call_args[0][0]
        assert call_args["x"] == 120
        assert call_args["y"] == 218
        assert call_args["wakeup_count"] == 4

    async def test_execute_cgi_command_unknown_profile(self, hass: HomeAssistant) -> None:
        """Unknown profile must raise HomeAssistantError."""
        client = MagicMock(spec=SolvisClient)
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(HomeAssistantError, match="Unknown CGI profile"):
            await coordinator.async_execute_cgi_command("nonexistent", "auto")

    async def test_execute_cgi_command_unknown_option(self, hass: HomeAssistant) -> None:
        """Unknown option must raise HomeAssistantError."""
        client = MagicMock(spec=SolvisClient)
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(HomeAssistantError, match="Unknown option"):
            await coordinator.async_execute_cgi_command("heating_mode", "nonexistent")

    async def test_execute_cgi_command_includes_section(self, hass: HomeAssistant) -> None:
        """Test that section_touch is resolved from CGI_SECTIONS."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        await coordinator.async_execute_cgi_command("heating_mode", "auto")

        call_args = client.execute_cgi_sequence.call_args[0][0]
        # DEFAULT_CGI_PROFILES["heating_mode"] has section="heizung"
        assert call_args["section_touch"] is not None
        assert call_args["section_touch"]["x"] == 43
        assert call_args["section_touch"]["y"] == 25

    async def test_execute_cgi_command_invalid_section_raises_error(self, hass: HomeAssistant) -> None:
        """Invalid section key must raise HomeAssistantError."""
        client = MagicMock(spec=SolvisClient)
        profiles = {
            "test_profile": {
                "name": "Test",
                "section": "nonexistent_section",
                "wakeup_count": 2,
                "wakeup_delay": 1.0,
                "reset_touch": {"x": 510, "y": 510},
                "options": {"opt1": {"label": "Opt1", "x": 100, "y": 100}},
            }
        }
        entry = _make_mock_entry_with_profiles(profiles)
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(HomeAssistantError, match="Invalid CGI section"):
            await coordinator.async_execute_cgi_command("test_profile", "opt1")

    async def test_execute_cgi_command_no_section_legacy(self, hass: HomeAssistant) -> None:
        """Profile without section must work (no section_touch in sequence)."""
        client = MagicMock(spec=SolvisClient)
        profiles = {
            "legacy_profile": {
                "name": "Legacy",
                "wakeup_count": 2,
                "wakeup_delay": 1.0,
                "reset_touch": {"x": 510, "y": 510},
                "options": {"opt1": {"label": "Opt1", "x": 100, "y": 100}},
            }
        }
        entry = _make_mock_entry_with_profiles(profiles)
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        await coordinator.async_execute_cgi_command("legacy_profile", "opt1")

        call_args = client.execute_cgi_sequence.call_args[0][0]
        assert call_args["section_touch"] is None

    async def test_execute_cgi_auth_error_triggers_reauth(self, hass: HomeAssistant) -> None:
        """Auth error during CGI must raise ConfigEntryAuthFailed."""
        client = MagicMock(spec=SolvisClient)
        client.execute_cgi_sequence.side_effect = SolvisAuthError("401")
        entry = _make_mock_entry()
        entry.add_to_hass(hass)

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
        with pytest.raises(ConfigEntryAuthFailed, match="CGI auth failed"):
            await coordinator.async_execute_cgi_command("heating_mode", "auto")
