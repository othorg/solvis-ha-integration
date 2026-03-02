"""Tests for the Solvis Anlagenschema image platform."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

from PIL import Image
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er

from custom_components.solvis_remote.const import DOMAIN
from custom_components.solvis_remote.image import (
    SolvisAnlagenschema,
)


MOCK_CONFIG_DATA = {
    "host": "192.168.1.100",
    "username": "admin",
    "password": "secret",
    "realm": "SolvisRemote",
}

MOCK_FETCH_RESULT = {
    "system": {"title": "Systemnummer", "value": None, "unit": None, "raw": "3412"},
    "s1": {"title": "Warmwasserpuffer", "value": 44.1, "unit": "C", "raw": "F200"},
    "s2": {"title": "Warmwassertemperatur", "value": 30.5, "unit": "C", "raw": "3300"},
    "s3": {"title": "Speicherreferenz", "value": 31.4, "unit": "C", "raw": "3800"},
    "s4": {"title": "Heizungspuffer oben", "value": 42.3, "unit": "C", "raw": "4500"},
    "s8": {"title": "Kollektortemperatur", "value": 34.6, "unit": "C", "raw": "5600"},
    "s9": {"title": "Heizungspuffer unten", "value": 41.7, "unit": "C", "raw": "4100"},
    "s10": {"title": "Aussentemperatur", "value": 11.8, "unit": "C", "raw": "1800"},
    "s11": {"title": "Zirkulationstemperatur", "value": 22.8, "unit": "C", "raw": "2800"},
    "s12": {"title": "Vorlauftemperatur", "value": 32.6, "unit": "C", "raw": "4601"},
    "s17": {"title": "Durchfluss Solar", "value": 0.0, "unit": "l/h", "raw": "0000"},
    "slv": {"title": "Aktuelle Leistung", "value": 0.0, "unit": "kW", "raw": "0000"},
    "sev": {"title": "Ertrag Solar", "value": 40919, "unit": "kWh", "raw": "9FA7"},
    "a1": {"title": "Solarpumpe", "value": "off", "unit": None, "raw": "00"},
    "a2": {"title": "Warmwasserpumpe", "value": "off", "unit": None, "raw": "00"},
    "a3": {"title": "Heizkreispumpe", "value": "off", "unit": None, "raw": "00"},
    "a5": {"title": "Zirkulationspumpe", "value": "off", "unit": None, "raw": "00"},
    "a12": {"title": "Nachheizung", "value": "on", "unit": None, "raw": "01"},
    "ao1": {"title": "Brennermodulation", "value": 50.2, "unit": None, "raw": "80"},
}


def _patch_fetch(side_effect=None, return_value=None):
    if return_value is None:
        return_value = MOCK_FETCH_RESULT
    return patch(
        "custom_components.solvis_remote.client.SolvisClient.fetch_data",
        side_effect=side_effect,
        return_value=return_value,
    )


class TestImageEntityCreation:
    """Test that the Anlagenschema image entity is created."""

    async def test_entity_created_with_correct_unique_id(
        self, hass: HomeAssistant
    ) -> None:
        """Image entity must be registered with correct unique_id."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED

        # Check entity registry for our unique_id (not hardcoded entity_id)
        ent_reg = er.async_get(hass)
        image_entities = [
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        ]
        assert len(image_entities) == 1
        assert image_entities[0].unique_id == "3412_anlagenschema"

    async def test_entity_has_translation_key(self, hass: HomeAssistant) -> None:
        """Image entity must use translation_key for localized name."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entities = [
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        ]
        assert image_entities[0].translation_key == "anlagenschema"

    async def test_entity_initializes_image_access_token(
        self, hass: HomeAssistant
    ) -> None:
        """ImageEntity base init must provide access_token attributes."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)
        assert entity is not None

        # Regression guard for HA runtime error:
        # AttributeError: object has no attribute 'access_tokens'
        attrs = entity.state_attributes
        assert "access_token" in attrs


class TestImageRendering:
    """Test image rendering with sensor data overlays."""

    async def test_async_image_returns_png_bytes(self, hass: HomeAssistant) -> None:
        """async_image() must return valid PNG bytes."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = entry.runtime_data

        # Get the image entity
        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)
        assert entity is not None

        result = await entity.async_image()
        assert result is not None
        # PNG magic bytes
        assert result[:4] == b"\x89PNG"

    async def test_async_image_returns_none_when_no_data(
        self, hass: HomeAssistant
    ) -> None:
        """async_image() must return None when coordinator has no data."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = entry.runtime_data

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        # Clear coordinator data
        coordinator.data = {}
        result = await entity.async_image()
        assert result is None


class TestImageCaching:
    """Test signature-based render caching."""

    async def test_same_data_uses_cache(self, hass: HomeAssistant) -> None:
        """Same sensor data must not trigger a re-render."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        # First call renders
        result1 = await entity.async_image()
        assert result1 is not None

        # Patch _render_image to track calls
        with patch.object(entity, "_render_image", wraps=entity._render_image) as mock_render:
            result2 = await entity.async_image()
            # Should return cached bytes without calling _render_image
            mock_render.assert_not_called()
            assert result2 == result1

    async def test_changed_data_triggers_rerender(self, hass: HomeAssistant) -> None:
        """Changed sensor data must trigger a new render."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        # First render
        result1 = await entity.async_image()

        # Change data
        coordinator = entry.runtime_data
        coordinator.data["s1"] = {**coordinator.data["s1"], "value": 99.9}

        # Second render should produce different bytes
        result2 = await entity.async_image()
        assert result2 is not None
        assert result2 != result1

    async def test_float_jitter_uses_cache(self, hass: HomeAssistant) -> None:
        """Float jitter (e.g. 44.1000001 vs 44.1) must not trigger re-render."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        # First render
        await entity.async_image()

        # Introduce float jitter (44.1 → 44.1000001)
        coordinator = entry.runtime_data
        coordinator.data["s1"] = {**coordinator.data["s1"], "value": 44.1000001}

        with patch.object(entity, "_render_image", wraps=entity._render_image) as mock_render:
            await entity.async_image()
            # Jitter should be normalized away — no re-render
            mock_render.assert_not_called()


class TestStatusIndicator:
    """Test a12 status indicator behavior."""

    async def test_a12_on_renders(self, hass: HomeAssistant) -> None:
        """a12='on' must render without error."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        result = await entity.async_image()
        assert result is not None
        assert result[:4] == b"\x89PNG"

    async def test_a12_off_renders_gray(self, hass: HomeAssistant) -> None:
        """a12='off' must render without error."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        fetch_data = {**MOCK_FETCH_RESULT, "a12": {**MOCK_FETCH_RESULT["a12"], "value": "off"}}

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(return_value=fetch_data):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        result = await entity.async_image()
        assert result is not None
        assert result[:4] == b"\x89PNG"

    async def test_a12_change_triggers_rerender(self, hass: HomeAssistant) -> None:
        """Changing a12 from 'on' to 'off' must trigger re-render."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        result_on = await entity.async_image()

        # Change a12 to "off"
        coordinator = entry.runtime_data
        coordinator.data["a12"] = {**coordinator.data["a12"], "value": "off"}

        result_off = await entity.async_image()
        assert result_off is not None
        assert result_on != result_off

    async def test_binary_indicator_change_triggers_rerender(
        self, hass: HomeAssistant
    ) -> None:
        """Changing other binary indicators must affect rendered image."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch():
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        result_before = await entity.async_image()

        # Toggle solar and heating-circuit indicators to "on"
        coordinator = entry.runtime_data
        coordinator.data["a1"] = {**coordinator.data["a1"], "value": "on"}
        coordinator.data["a3"] = {**coordinator.data["a3"], "value": "on"}

        result_after = await entity.async_image()
        assert result_after is not None
        assert result_before != result_after



class TestErrorPaths:
    """Test error handling for missing assets."""

    async def test_missing_base_image_makes_unavailable(
        self, hass: HomeAssistant
    ) -> None:
        """Missing base PNG must set available=False and log error."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(), patch(
            "custom_components.solvis_remote.image._BASE_IMAGE_CANDIDATES",
            (Path("/nonexistent/image.jpg"), Path("/nonexistent/image.png")),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        assert entity.available is False
        result = await entity.async_image()
        assert result is None

    async def test_missing_font_uses_fallback(self, hass: HomeAssistant) -> None:
        """Missing font file must fall back to default font and still render."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG_DATA)
        entry.add_to_hass(hass)

        with _patch_fetch(), patch(
            "custom_components.solvis_remote.image._FONT_PATH",
            Path("/nonexistent/font.ttf"),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ent_reg = er.async_get(hass)
        image_entry = next(
            e
            for e in ent_reg.entities.values()
            if e.domain == "image" and e.platform == DOMAIN
        )
        entity = hass.data["image"].get_entity(image_entry.entity_id)

        # Should still render with fallback font
        assert entity.available is True
        result = await entity.async_image()
        assert result is not None
        assert result[:4] == b"\x89PNG"


class TestCoordinateScaling:
    """Test that relative coordinates scale correctly."""

    def test_build_signature_normalizes_floats(self) -> None:
        """Float jitter must be normalized in signature."""
        data_a = {
            "s10": {"value": 11.8},
            "s1": {"value": 44.10000001},
            "s4": {"value": 42.3},
            "s9": {"value": 41.7},
            "s3": {"value": 31.4},
            "slv": {"value": 0.0},
            "sev": {"value": 40919},
            "s17": {"value": 0.0},
            "s8": {"value": 34.6},
            "s2": {"value": 30.5},
            "s11": {"value": 22.8},
            "s12": {"value": 32.6},
            "a12": {"value": "on"},
        }
        data_b = {
            "s10": {"value": 11.8},
            "s1": {"value": 44.1},
            "s4": {"value": 42.3},
            "s9": {"value": 41.7},
            "s3": {"value": 31.4},
            "slv": {"value": 0.0},
            "sev": {"value": 40919},
            "s17": {"value": 0.0},
            "s8": {"value": 34.6},
            "s2": {"value": 30.5},
            "s11": {"value": 22.8},
            "s12": {"value": 32.6},
            "a12": {"value": "on"},
        }

        sig_a = SolvisAnlagenschema._build_signature(data_a)
        sig_b = SolvisAnlagenschema._build_signature(data_b)
        assert sig_a == sig_b
