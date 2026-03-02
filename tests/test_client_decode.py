"""Tests for client.py — hex decoding and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from custom_components.solvis_remote.client import (
    SolvisClient,
    SolvisAuthError,
    SolvisConnectionError,
    SolvisPayloadError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client() -> SolvisClient:
    """Create a SolvisClient without making network calls."""
    return SolvisClient(
        host="192.168.1.100",
        username="testuser",
        password="testpass",
    )


def _decode_hex(hex_payload: str) -> dict[str, dict]:
    """Decode a hex payload using SolvisClient internals (no network)."""
    client = _make_client()
    client._raw = hex_payload
    return client._decode()


def _hex_from_xml(xml_path: Path) -> str:
    """Extract the hex payload from a fixture XML file."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    return root.find("data").text


# ---------------------------------------------------------------------------
# Decode tests
# ---------------------------------------------------------------------------

class TestDecode:
    """Test hex-to-value decoding logic."""

    @pytest.fixture(autouse=True)
    def _load_payload(self):
        self.hex_data = _hex_from_xml(FIXTURES_DIR / "solvis_payload_ok.xml")
        self.data = _decode_hex(self.hex_data)

    def test_payload_length(self):
        assert len(self.hex_data) >= SolvisClient.MIN_PAYLOAD_LENGTH

    def test_temperature_s1(self):
        assert self.data["s1"]["value"] == pytest.approx(24.2)

    def test_temperature_s2(self):
        assert self.data["s2"]["value"] == pytest.approx(60.0)

    def test_temperature_s5_solar_flow(self):
        assert self.data["s5"]["value"] == pytest.approx(32.6)

    def test_temperature_s6_solar_return(self):
        assert self.data["s6"]["value"] == pytest.approx(26.4)

    def test_temperature_s8_collector(self):
        assert self.data["s8"]["value"] == pytest.approx(34.6)

    def test_temperature_s10_outdoor(self):
        assert self.data["s10"]["value"] == pytest.approx(8.0)

    def test_temperature_rf1_room(self):
        assert self.data["rf1"]["value"] == pytest.approx(21.0)

    def test_burner_modulation_ao1(self):
        # 128 / 2.55 ≈ 50.2%
        assert self.data["ao1"]["value"] == pytest.approx(50.196, abs=0.01)

    def test_flow_rate_s17(self):
        assert self.data["s17"]["value"] == pytest.approx(30.0)

    def test_flow_rate_s18(self):
        assert self.data["s18"]["value"] == pytest.approx(10.0)

    def test_digital_output_a1_on(self):
        assert self.data["a1"]["value"] == "on"

    def test_digital_output_a2_off(self):
        assert self.data["a2"]["value"] == "off"

    def test_digital_output_a12_burner_on(self):
        assert self.data["a12"]["value"] == "on"

    def test_solar_yield_sev(self):
        assert self.data["sev"]["value"] == 1000

    def test_solar_power_slv(self):
        assert self.data["slv"]["value"] == pytest.approx(20.0)

    def test_system_number_raw(self):
        assert self.data["system"]["raw"] == "3412"


class TestDecodeShortPayload:
    """Test that a too-short payload raises SolvisPayloadError."""

    def test_short_payload_raises(self):
        with pytest.raises(SolvisPayloadError, match="too short"):
            _decode_hex("00000000")


# ---------------------------------------------------------------------------
# Convert tests
# ---------------------------------------------------------------------------

class TestConvert:
    """Test hex-to-int conversion."""

    def setup_method(self):
        self.client = _make_client()

    def test_unsigned(self):
        # "F200" → b'\xf2\x00' LE → 0x00F2 = 242
        assert self.client._convert("F200") == 242

    def test_signed_positive(self):
        assert self.client._convert("F200", limited=True) == 242

    def test_signed_negative(self):
        # "F0FF" → b'\xf0\xff' LE → 0xFFF0 = 65520 → signed: 65520 - 65536 = -16
        assert self.client._convert("F0FF", limited=True) == -16

    def test_unsigned_large(self):
        # "E803" → b'\xe8\x03' LE → 0x03E8 = 1000
        assert self.client._convert("E803") == 1000


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestFetchErrors:
    """Test that fetch_data maps HTTP errors to custom exceptions."""

    def setup_method(self):
        self.client = _make_client()

    def test_auth_error_401(self):
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test", code=401, msg="Unauthorized",
            hdrs=None, fp=None,
        )
        with patch.object(self.client._opener, "open", side_effect=error):
            with pytest.raises(SolvisAuthError, match="401"):
                self.client.fetch_data()

    def test_auth_error_403(self):
        import urllib.error
        error = urllib.error.HTTPError(
            url="http://test", code=403, msg="Forbidden",
            hdrs=None, fp=None,
        )
        with patch.object(self.client._opener, "open", side_effect=error):
            with pytest.raises(SolvisAuthError, match="403"):
                self.client.fetch_data()

    def test_connection_error(self):
        import urllib.error
        error = urllib.error.URLError("Connection refused")
        with patch.object(self.client._opener, "open", side_effect=error):
            with pytest.raises(SolvisConnectionError, match="Cannot connect"):
                self.client.fetch_data()

    def test_timeout_error(self):
        with patch.object(self.client._opener, "open", side_effect=TimeoutError):
            with pytest.raises(SolvisConnectionError, match="Timeout"):
                self.client.fetch_data()

    def test_xml_parse_error(self):
        import io
        bad_response = io.BytesIO(b"not xml at all")
        with patch.object(self.client._opener, "open", return_value=bad_response):
            with pytest.raises(SolvisPayloadError, match="parse"):
                self.client.fetch_data()

    def test_missing_data_element(self):
        import io
        xml_no_data = b'<?xml version="1.0"?><xml><other>test</other></xml>'
        response = io.BytesIO(xml_no_data)
        with patch.object(self.client._opener, "open", return_value=response):
            with pytest.raises(SolvisPayloadError, match="No <data> element"):
                self.client.fetch_data()

    def test_successful_fetch(self):
        import io
        xml_ok = (FIXTURES_DIR / "solvis_payload_ok.xml").read_bytes()
        response = io.BytesIO(xml_ok)
        with patch.object(self.client._opener, "open", return_value=response):
            data = self.client.fetch_data()
            assert data["s1"]["value"] == pytest.approx(24.2)
            assert data["a1"]["value"] == "on"
