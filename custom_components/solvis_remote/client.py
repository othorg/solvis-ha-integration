"""Solvis heating controller client.

Connects via HTTP Digest Auth to a Solvis controller's XML API,
retrieves binary sensor data encoded as hex, and decodes it
into human-readable values.

Ported from SolvisRemoteV3/solvis_remote.py for use in the
Home Assistant custom integration. No HA dependencies.
"""

from __future__ import annotations

import logging
import random
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SolvisConnectionError(Exception):
    """Raised when the controller cannot be reached (network/timeout)."""


class SolvisAuthError(Exception):
    """Raised when HTTP Digest Auth fails (401/403)."""


class SolvisPayloadError(Exception):
    """Raised when the XML response cannot be parsed or payload is too short."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class SolvisClient:
    """Client for reading sensor data from a Solvis heating controller.

    Connects via HTTP Digest Auth to the controller's XML API endpoint
    (sc2_val.xml), fetches hex-encoded binary sensor data, and decodes
    it into a dictionary of named values with titles, units, and raw data.
    """

    PROTOCOL: str = "http"
    PATH: str = "sc2_val.xml"

    # Sensor position map: byte offset, size, and unit in the hex data stream.
    POSITIONS: dict[str, dict] = {
        # Header / System
        "header": {"title": "Header", "start": 0, "size": 12, "unit": None},
        "time": {"title": "Uhrzeit", "start": 12, "size": 6, "unit": None},
        "typeofinstallation": {"title": "Anlagentyp", "start": 18, "size": 4, "unit": None},
        "system": {"title": "Systemnummer", "start": 22, "size": 4, "unit": None},
        # Temperatures (S1-S16)
        "s1": {"title": "Warmwasserpuffer", "start": 26, "size": 4, "unit": "C"},
        "s2": {"title": "Warmwassertemperatur", "start": 30, "size": 4, "unit": "C"},
        "s3": {"title": "Speicherreferenz", "start": 34, "size": 4, "unit": "C"},
        "s4": {"title": "Heizungspuffer oben", "start": 38, "size": 4, "unit": "C"},
        "s5": {"title": "Vorlauftemperatur", "start": 42, "size": 4, "unit": "C"},
        "s6": {"title": "Ruecklauftemperatur", "start": 46, "size": 4, "unit": "C"},
        "s7": {"title": "<Unbekannt>", "start": 50, "size": 4, "unit": None},
        "s8": {"title": "Kollektortemperatur", "start": 54, "size": 4, "unit": "C"},
        "s9": {"title": "Heizungspuffer unten", "start": 58, "size": 4, "unit": "C"},
        "s10": {"title": "Aussentemperatur", "start": 62, "size": 4, "unit": "C"},
        "s11": {"title": "Zirkulationstemperatur", "start": 66, "size": 4, "unit": "C"},
        "s12": {"title": "Vorlauftemperatur", "start": 70, "size": 4, "unit": "C"},
        "s13": {"title": "Vorlauftemperatur", "start": 74, "size": 4, "unit": "C"},
        "s14": {"title": "Entstoerung", "start": 78, "size": 4, "unit": None},
        "s15": {"title": "Kollektor-Uebergabe", "start": 82, "size": 4, "unit": None},
        "s16": {"title": "<Unbekannt>", "start": 86, "size": 4, "unit": None},
        # Flow rates
        "s17": {"title": "Durchfluss Solar", "start": 90, "size": 4, "unit": "l/h"},
        "s18": {"title": "Durchfluss Warmwasser", "start": 94, "size": 4, "unit": "l/m"},
        # Analogue inputs
        "ai1": {"title": "<Unbekannt>", "start": 98, "size": 4, "unit": None},
        "ai2": {"title": "<Unbekannt>", "start": 102, "size": 4, "unit": None},
        "ai3": {"title": "<Unbekannt>", "start": 106, "size": 4, "unit": None},
        # Analogue outputs
        "ao1": {"title": "Brennermodulation", "start": 110, "size": 2, "unit": None},
        "ao2": {"title": "<Unbekannt>", "start": 112, "size": 2, "unit": None},
        "ao3": {"title": "<Unbekannt>", "start": 114, "size": 2, "unit": None},
        "ao4": {"title": "<Unbekannt>", "start": 116, "size": 2, "unit": None},
        # Room sensors
        "rf1": {"title": "Raumtemperatur", "start": 118, "size": 4, "unit": "C"},
        "rf2": {"title": "Raumtemperatur", "start": 122, "size": 4, "unit": "C"},
        "rf3": {"title": "Raumtemperatur", "start": 126, "size": 4, "unit": "C"},
        # Digital outputs (pumps, valves)
        "a1": {"title": "Solarpumpe", "start": 130, "size": 2, "unit": None},
        "a2": {"title": "Warmwasserpumpe", "start": 132, "size": 2, "unit": None},
        "a3": {"title": "Heizkreispumpe", "start": 134, "size": 2, "unit": None},
        "a4": {"title": "Heizkreispumpe", "start": 136, "size": 2, "unit": None},
        "a5": {"title": "Zirkulationspumpe", "start": 138, "size": 2, "unit": None},
        "a6": {"title": "Heizkreispumpe", "start": 140, "size": 2, "unit": None},
        "a7": {"title": "<Unbekannt>", "start": 142, "size": 2, "unit": None},
        "a8": {"title": "<Unbekannt>", "start": 144, "size": 2, "unit": None},
        "a9": {"title": "<Unbekannt>", "start": 146, "size": 2, "unit": None},
        "a10": {"title": "<Unbekannt>", "start": 148, "size": 2, "unit": None},
        "a11": {"title": "<Unbekannt>", "start": 150, "size": 2, "unit": None},
        "a12": {"title": "Nachheizung", "start": 152, "size": 2, "unit": None},
        "a13": {"title": "<Unbekannt>", "start": 154, "size": 2, "unit": None},
        "a14": {"title": "<Unbekannt>", "start": 156, "size": 2, "unit": None},
        "a15": {"title": "<Unbekannt>", "start": 158, "size": 16, "unit": None},
        # Solar yield
        "sev": {"title": "Ertrag Solar", "start": 174, "size": 4, "unit": "kWh"},
        # Unused ranges
        "unused1": {"title": "<Unbenutzt>", "start": 178, "size": 10, "unit": None},
        # Analogue output 5
        "ao5": {"title": "<Unbekannt>", "start": 188, "size": 2, "unit": None},
        # Unused ranges
        "unused2": {"title": "<Unbenutzt>", "start": 190, "size": 14, "unit": None},
        # Serie 7 flag
        "serie7": {"title": "Serie 7", "start": 204, "size": 2, "unit": None},
        # Unused
        "unused4": {"title": "<Unbenutzt>", "start": 206, "size": 2, "unit": None},
        "unused5": {"title": "<Unbenutzt>", "start": 208, "size": 2, "unit": None},
        # Solar power
        "slv": {"title": "Aktuelle Leistung", "start": 208, "size": 4, "unit": "kW"},
    }

    DEFAULT_TIMEOUT: int = 10  # seconds

    # Minimum expected hex payload length (highest offset + size in POSITIONS)
    # slv: start=208, size=4 -> need at least 212 hex chars
    MIN_PAYLOAD_LENGTH: int = 212

    # Decoding rules: maps sensor keys to decode type + parameters.
    DECODE_RULES: dict[str, tuple] = {}

    # Temperatures S1-S16: signed, /10
    for _k in [f"s{i}" for i in range(1, 17)]:
        DECODE_RULES[_k] = ("signed_div10",)

    # Flow rates S17-S18: unsigned, /10
    for _k in ["s17", "s18"]:
        DECODE_RULES[_k] = ("unsigned_div10",)

    # Analogue inputs: unsigned, /10
    for _k in ["ai1", "ai2", "ai3"]:
        DECODE_RULES[_k] = ("unsigned_div10",)

    # Analogue outputs: ao1 has special divisor 2.55, others /10
    DECODE_RULES["ao1"] = ("custom", 2.55, False)
    for _k in ["ao2", "ao3", "ao4"]:
        DECODE_RULES[_k] = ("unsigned_div10",)

    # Room sensors: signed, /10
    for _k in ["rf1", "rf2", "rf3"]:
        DECODE_RULES[_k] = ("signed_div10",)

    # a15: only first 4 hex chars / 2 bytes are meaningful
    DECODE_RULES["a15"] = ("signed_div10",)

    # Digital outputs A1-A14: on/off
    for _k in [f"a{i}" for i in range(1, 15)]:
        DECODE_RULES[_k] = ("on_off",)

    # Solar yield / ao5: raw integer
    DECODE_RULES["sev"] = ("raw_int",)
    DECODE_RULES["ao5"] = ("raw_int",)

    # Serie 7 flag
    DECODE_RULES["serie7"] = ("bool_ge192",)

    # Solar power: unsigned, /10
    DECODE_RULES["slv"] = ("unsigned_div10",)

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        realm: str = "SolvisRemote",
        timeout: int | None = None,
    ) -> None:
        self.host = host
        self.username = username
        self.password = password
        self.realm = realm
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        self._raw: str = ""

        # Setup HTTP Digest Authentication
        auth_handler = urllib.request.HTTPDigestAuthHandler()
        auth_handler.add_password(
            self.realm,
            f"{self.PROTOCOL}://{self.host}",
            self.username,
            self.password,
        )
        self._opener = urllib.request.build_opener(auth_handler)

    def _url(self) -> str:
        """Build URL with cache-busting dummy parameter."""
        dummy = random.randint(10000000, 99999999)
        return f"{self.PROTOCOL}://{self.host}/{self.PATH}?dummy={dummy}"

    def fetch_data(self) -> dict[str, dict]:
        """Fetch and return decoded sensor data from the controller.

        Returns:
            Dictionary mapping sensor keys to dicts with
            title, value, unit, and raw data.

        Raises:
            SolvisConnectionError: Network or timeout error.
            SolvisAuthError: HTTP 401/403.
            SolvisPayloadError: XML parse error or payload too short.
        """
        url = self._url()
        try:
            response = self._opener.open(url, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                raise SolvisAuthError(
                    f"Authentication failed for {self.host} (HTTP {err.code})"
                ) from err
            raise SolvisConnectionError(
                f"HTTP error {err.code} from {self.host}"
            ) from err
        except urllib.error.URLError as err:
            raise SolvisConnectionError(
                f"Cannot connect to {self.host}: {err.reason}"
            ) from err
        except TimeoutError as err:
            raise SolvisConnectionError(
                f"Timeout connecting to {self.host}"
            ) from err

        try:
            tree = ET.parse(response)
            root = tree.getroot()
            data_element = root.find("data")
            if data_element is None or data_element.text is None:
                raise SolvisPayloadError(
                    "No <data> element found in XML response"
                )
            self._raw = data_element.text
        except ET.ParseError as err:
            raise SolvisPayloadError(
                f"Failed to parse XML from {self.host}: {err}"
            ) from err

        return self._decode()

    def _convert(self, hexstring: str, limited: bool = False) -> int:
        """Convert hex string to integer (little-endian byte order).

        Args:
            hexstring: Hex-encoded string from the binary data stream.
            limited: If True, interpret as signed 16-bit integer.

        Raises:
            SolvisPayloadError: If hexstring contains invalid hex characters.
        """
        try:
            raw_bytes = bytes.fromhex(hexstring)
        except ValueError as err:
            raise SolvisPayloadError(
                f"Invalid hex data: '{hexstring}'"
            ) from err
        value = int.from_bytes(raw_bytes, byteorder="little", signed=False)

        if limited and value > 32767:
            value -= 65536

        return value

    def _decode(self) -> dict[str, dict]:
        """Decode the raw hex data into a dictionary of sensor values.

        Raises:
            SolvisPayloadError: If the hex payload is too short.
        """
        if len(self._raw) < self.MIN_PAYLOAD_LENGTH:
            raise SolvisPayloadError(
                f"Payload too short: {len(self._raw)} hex chars "
                f"(expected at least {self.MIN_PAYLOAD_LENGTH})"
            )

        values: dict[str, dict] = {}
        for key, pos in self.POSITIONS.items():
            start = pos["start"]
            size = pos["size"]
            values[key] = {
                "title": pos["title"],
                "value": None,
                "unit": pos["unit"],
                "raw": self._raw[start : start + size],
            }

        for key, rule in self.DECODE_RULES.items():
            if key not in values:
                continue
            raw = values[key]["raw"]
            rule_type = rule[0]

            # a15: only first 4 hex chars meaningful
            if key == "a15":
                raw = raw[:4]

            if rule_type == "signed_div10":
                values[key]["value"] = self._convert(raw, limited=True) / 10.0
            elif rule_type == "unsigned_div10":
                values[key]["value"] = self._convert(raw) / 10.0
            elif rule_type == "on_off":
                values[key]["value"] = "on" if self._convert(raw) else "off"
            elif rule_type == "raw_int":
                values[key]["value"] = self._convert(raw)
            elif rule_type == "bool_ge192":
                values[key]["value"] = self._convert(raw) >= 192
            elif rule_type == "custom":
                _, divisor, signed = rule
                values[key]["value"] = self._convert(raw, limited=signed) / divisor

        return values
