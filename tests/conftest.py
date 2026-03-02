"""Shared test fixtures for solvis_remote tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture
def payload_ok_xml() -> str:
    """Return the content of the well-formed XML fixture."""
    return (FIXTURES_DIR / "solvis_payload_ok.xml").read_text()


@pytest.fixture
def payload_short_xml() -> str:
    """Return the content of the too-short XML fixture."""
    return (FIXTURES_DIR / "solvis_payload_short.xml").read_text()


@pytest.fixture
def payload_ok_hex() -> str:
    """Return the hex payload string from the well-formed fixture."""
    return (
        "00000000000000000000003412"
        "F20058021E010A024601080100005A01B4005000C800E600"
        "000000001E0100002C016400000000000000"
        "80000000"
        "D2000000000001000100010000000000000100000000000000000000"
        "E803000000000000000000000000000000C800"
    )
