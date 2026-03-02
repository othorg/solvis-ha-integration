"""Tests for the Solvis DataUpdateCoordinator."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.solvis_remote.coordinator import SolvisDataUpdateCoordinator
from custom_components.solvis_remote.client import (
    SolvisClient,
    SolvisAuthError,
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


class TestCoordinatorDerivedValues:
    """Test computed values (delta_s5s6, brennerleistung)."""

    async def test_delta_s5s6(self, hass: HomeAssistant) -> None:
        """Test that delta_s5s6 = s5 - s6."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
        data = await coordinator._async_update_data()

        assert "delta_s5s6" in data
        # 32.6 - 26.4 = 6.2
        assert data["delta_s5s6"]["value"] == pytest.approx(6.2, abs=0.1)

    async def test_brennerleistung_on(self, hass: HomeAssistant) -> None:
        """Test brennerleistung when burner is on."""
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.return_value = _make_mock_data()

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
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

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
        data = await coordinator._async_update_data()

        assert data["brennerleistung"]["value"] == 0.0


class TestCoordinatorErrors:
    """Test that client errors are mapped to UpdateFailed."""

    async def test_auth_error(self, hass: HomeAssistant) -> None:
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisAuthError("401")

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
        with pytest.raises(UpdateFailed, match="Authentication"):
            await coordinator._async_update_data()

    async def test_connection_error(self, hass: HomeAssistant) -> None:
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisConnectionError("timeout")

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
        with pytest.raises(UpdateFailed, match="Connection"):
            await coordinator._async_update_data()

    async def test_payload_error(self, hass: HomeAssistant) -> None:
        client = MagicMock(spec=SolvisClient)
        client.fetch_data.side_effect = SolvisPayloadError("too short")

        coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412")
        with pytest.raises(UpdateFailed, match="payload"):
            await coordinator._async_update_data()
