"""Shared test fixtures for solvis_remote tests."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture(autouse=True)
def fail_on_ha_deprecation_reports(caplog: pytest.LogCaptureFixture):
    """Fail a test if HA reports deprecated usage by this integration.

    HA logs these reports instead of raising, so a plain test run passes.
    Covers setup and call; import-time reports happen during collection.
    """
    yield
    reports = [
        record.getMessage()
        for when in ("setup", "call")
        for record in caplog.get_records(when)
        if record.levelno >= logging.WARNING
        and "solvis_remote" in record.getMessage()
        and (
            "Detected that custom integration" in record.getMessage()
            or "deprecated" in record.getMessage().lower()
        )
    ]
    assert not reports, f"HA reported deprecated usage: {reports}"


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
