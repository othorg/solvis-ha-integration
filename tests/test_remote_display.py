"""Tests for the remote display: client fetch, camera, touch gestures, services."""

from __future__ import annotations

import asyncio
from io import BytesIO
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solvis_remote import coordinator as coordinator_module
from custom_components.solvis_remote.camera import SolvisDisplayCamera, bmp_to_jpeg
from custom_components.solvis_remote.client import (
    SolvisBusyError,
    SolvisClient,
    SolvisConnectionError,
    SolvisPayloadError,
)
from custom_components.solvis_remote.const import (
    CONF_CGI_PROFILES,
    CONF_ENABLE_CGI,
    DEFAULT_CGI_PROFILES,
    DOMAIN,
    TOUCH_RELEASE,
)
from custom_components.solvis_remote.coordinator import SolvisDataUpdateCoordinator

MOCK_CONFIG_DATA = {
    "host": "192.168.1.100",
    "username": "admin",
    "password": "secret",
    "realm": "SolvisRemote",
}
MOCK_FETCH_RESULT = {
    "system": {"title": "Systemnummer", "value": None, "unit": None, "raw": "3412"},
}
RELEASE = (TOUCH_RELEASE["x"], TOUCH_RELEASE["y"])


def _bmp(width: int = 240, height: int = 128) -> bytes:
    """An indexed BMP like the controller's display.bmp (Pillow cannot
    write 4-bit BMPs; the real 4-bit format was checked against a capture)."""
    img = Image.new("L", (width, height), 0)
    buf = BytesIO()
    img.save(buf, format="BMP")
    return buf.getvalue()


def _entry(cgi: bool = True) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_CONFIG_DATA,
        options={CONF_ENABLE_CGI: cgi, CONF_CGI_PROFILES: DEFAULT_CGI_PROFILES},
    )


@pytest.fixture
def fast_touch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink hold times so gesture tests run fast."""
    monkeypatch.setattr(coordinator_module, "TOUCH_MIN_HOLD", 0.01)
    monkeypatch.setattr(coordinator_module, "TOUCH_MAX_HOLD", 0.2)


def _coordinator(hass: HomeAssistant) -> tuple[SolvisDataUpdateCoordinator, MagicMock]:
    client = MagicMock(spec=SolvisClient)
    entry = _entry()
    entry.add_to_hass(hass)
    coordinator = SolvisDataUpdateCoordinator(hass, client, 60, "3412", entry)
    coordinator._last_command_time = -10.0  # no cooldown wait in tests
    return coordinator, client


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class TestClientDisplay:
    def _client(self) -> SolvisClient:
        return SolvisClient("192.168.1.100", "admin", "secret")

    def test_fetch_display_returns_bmp(self) -> None:
        client = self._client()
        with patch.object(client._opener, "open", return_value=BytesIO(_bmp())) as opened:
            assert client.fetch_display().startswith(b"BM")
        assert "/display.bmp?" in opened.call_args[0][0]

    def test_fetch_display_rejects_non_bmp(self) -> None:
        client = self._client()
        with patch.object(client._opener, "open", return_value=BytesIO(b"<html>")):
            with pytest.raises(SolvisPayloadError, match="not a BMP"):
                client.fetch_display()

    def test_requests_are_serialized(self) -> None:
        """Display polling must not overlap data polls or commands."""
        client = self._client()
        active = 0
        overlap = False
        guard = threading.Lock()

        def slow_open(url, timeout=None):
            nonlocal active, overlap
            with guard:
                active += 1
                overlap = overlap or active > 1
            time.sleep(0.05)
            with guard:
                active -= 1
            return BytesIO(_bmp())

        with patch.object(client._opener, "open", side_effect=slow_open):
            threads = [threading.Thread(target=client.fetch_display) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        assert not overlap


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


class TestDisplayCamera:
    def test_bmp_to_jpeg_doubles_the_display(self) -> None:
        with Image.open(BytesIO(bmp_to_jpeg(_bmp()))) as img:
            assert img.format == "JPEG"
            assert img.size == (480, 256)

    async def test_header_matches_the_frames(self, hass: HomeAssistant) -> None:
        """HA sends content_type as the HTTP header and in the MJPEG stream parts."""
        coordinator, client = _coordinator(hass)
        client.fetch_display.return_value = _bmp()
        camera = SolvisDisplayCamera(coordinator)
        camera.hass = hass
        frame = await camera.async_camera_image()
        assert camera.content_type == "image/jpeg"
        assert frame is not None and frame.startswith(b"\xff\xd8")

    async def test_viewers_share_one_fetch(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        calls = 0

        def fetch() -> bytes:
            nonlocal calls
            calls += 1
            time.sleep(0.05)
            return _bmp()

        client.fetch_display.side_effect = fetch
        camera = SolvisDisplayCamera(coordinator)
        camera.hass = hass
        frames = await asyncio.gather(*(camera.async_camera_image() for _ in range(3)))
        assert calls == 1
        assert all(frame and frame.startswith(b"\xff\xd8") for frame in frames)
        # A frame younger than the max age is reused, too.
        await camera.async_camera_image()
        assert calls == 1

    async def test_unreadable_display_returns_none(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        client.fetch_display.side_effect = SolvisBusyError("403")
        camera = SolvisDisplayCamera(coordinator)
        camera.hass = hass
        assert await camera.async_camera_image() is None
        # The failed fetch is not cached: the next call tries again.
        client.fetch_display.side_effect = None
        client.fetch_display.return_value = _bmp()
        assert await camera.async_camera_image() is not None


# ---------------------------------------------------------------------------
# Touch gestures
# ---------------------------------------------------------------------------


def _touches(client: MagicMock) -> list[tuple[int, int]]:
    return [c.args for c in client.send_touch.call_args_list]


@pytest.mark.usefixtures("fast_touch")
class TestTouchGestures:
    async def test_tap_presses_and_releases(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch(120, 218, 0.01)
        assert _touches(client) == [(120, 218), RELEASE]
        assert coordinator._gesture is None
        assert not coordinator._command_lock.locked()

    async def test_tap_releases_when_press_fails(self, hass: HomeAssistant) -> None:
        """A press whose response got lost may have landed: release anyway."""
        coordinator, client = _coordinator(hass)
        client.send_touch.side_effect = [SolvisConnectionError("timeout"), None]
        with pytest.raises(HomeAssistantError):
            await coordinator.async_touch(120, 218)
        assert _touches(client) == [(120, 218), RELEASE]
        assert not coordinator._command_lock.locked()

    async def test_release_keeps_minimum_hold_after_failed_press(
        self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(coordinator_module, "TOUCH_MIN_HOLD", 0.1)
        coordinator, client = _coordinator(hass)
        times: list[float] = []

        def touch(x: int, y: int) -> None:
            times.append(time.monotonic())
            if len(times) == 1:
                raise SolvisConnectionError("response lost")

        client.send_touch.side_effect = touch
        with pytest.raises(HomeAssistantError):
            await coordinator.async_touch_down(300, 100)
        await hass.async_block_till_done()
        assert len(times) == 2
        assert times[1] - times[0] >= 0.09

    async def test_hold_and_release(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch_down(300, 100)
        assert _touches(client) == [(300, 100)]
        assert coordinator._command_lock.locked()
        await coordinator.async_touch_up()
        assert _touches(client) == [(300, 100), RELEASE]
        assert not coordinator._command_lock.locked()

    async def test_profile_command_waits_for_held_touch(self, hass: HomeAssistant) -> None:
        """A CGI profile sequence must not land between press and release."""
        coordinator, client = _coordinator(hass)
        order: list[str] = []
        client.send_touch.side_effect = lambda x, y: order.append(f"touch {x}/{y}")
        client.execute_cgi_sequence.side_effect = lambda seq: order.append("sequence")

        await coordinator.async_touch_down(300, 100)
        command = hass.async_create_task(
            coordinator.async_execute_cgi_command("heating_mode", "night")
        )
        await asyncio.sleep(0.05)
        assert "sequence" not in order
        await coordinator.async_touch_up()
        await command
        assert order == ["touch 300/100", "touch 510/510", "sequence"]

    async def test_cancelled_release_call_still_releases(self, hass: HomeAssistant) -> None:
        """A dropped frontend connection must not leave the touch held."""
        coordinator, client = _coordinator(hass)
        order: list[str] = []
        client.send_touch.side_effect = lambda x, y: order.append(f"touch {x}/{y}")
        client.execute_cgi_sequence.side_effect = lambda seq: order.append("sequence")

        await coordinator.async_touch_down(300, 100)
        gesture_task = coordinator._gesture.task
        up = hass.async_create_task(coordinator.async_touch_up())
        command = hass.async_create_task(
            coordinator.async_execute_cgi_command("heating_mode", "night")
        )
        await asyncio.sleep(0)
        up.cancel()
        await gesture_task
        await command
        assert order == ["touch 300/100", "touch 510/510", "sequence"]

    async def test_watchdog_releases_forgotten_touch(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch_down(300, 100)
        await asyncio.sleep(0.4)  # TOUCH_MAX_HOLD is 0.2 s here
        await hass.async_block_till_done()
        assert _touches(client) == [(300, 100), RELEASE]
        assert not coordinator._command_lock.locked()
        # A late touch_up from the frontend changes nothing.
        await coordinator.async_touch_up()
        assert _touches(client) == [(300, 100), RELEASE]

    async def test_second_viewer_is_refused_while_held(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch_down(300, 100, "viewer-1")
        with pytest.raises(HomeAssistantError, match="being operated"):
            await coordinator.async_touch_down(10, 10, "viewer-2")
        with pytest.raises(HomeAssistantError, match="being operated"):
            await coordinator.async_press_button("links")
        # The refused viewer's release must not end viewer 1's touch.
        await coordinator.async_touch_up("viewer-2")
        assert _touches(client) == [(300, 100)]
        await coordinator.async_touch_up("viewer-1")
        assert _touches(client) == [(300, 100), RELEASE]

    async def test_release_requested_while_press_pending(self, hass: HomeAssistant) -> None:
        """touch_up arriving before the press went out releases right after it."""
        coordinator, client = _coordinator(hass)
        await coordinator._command_lock.acquire()  # something else is running
        down = hass.async_create_task(coordinator.async_touch_down(300, 100))
        await asyncio.sleep(0.01)
        up = hass.async_create_task(coordinator.async_touch_up())
        await asyncio.sleep(0.01)
        client.send_touch.assert_not_called()
        coordinator._command_lock.release()
        await down
        await up
        assert _touches(client) == [(300, 100), RELEASE]
        assert coordinator._gesture is None
        assert not coordinator._command_lock.locked()

    async def test_failed_press_frees_the_display(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        client.send_touch.side_effect = [SolvisBusyError("403"), None]
        with pytest.raises(HomeAssistantError):
            await coordinator.async_touch_down(300, 100)
        await hass.async_block_till_done()
        assert coordinator._gesture is None
        assert not coordinator._command_lock.locked()

    async def test_touch_up_without_gesture_does_nothing(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch_up()
        client.send_touch.assert_not_called()

    async def test_shutdown_releases_held_touch(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_touch_down(300, 100)
        await coordinator.async_shutdown()
        assert _touches(client) == [(300, 100), RELEASE]
        with pytest.raises(HomeAssistantError, match="unloading"):
            await coordinator.async_touch(1, 1)

    async def test_shutdown_drains_pending_press(self, hass: HomeAssistant) -> None:
        """Nothing may reach the controller after shutdown returned."""
        coordinator, client = _coordinator(hass)
        await coordinator._command_lock.acquire()
        hass.async_create_task(coordinator.async_touch_down(300, 100))
        await asyncio.sleep(0.01)
        shutdown = hass.async_create_task(coordinator.async_shutdown())
        await asyncio.sleep(0.01)
        coordinator._command_lock.release()
        await shutdown
        calls_at_shutdown = list(_touches(client))
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()
        assert _touches(client) == calls_at_shutdown == [(300, 100), RELEASE]

    async def test_press_button(self, hass: HomeAssistant) -> None:
        coordinator, client = _coordinator(hass)
        await coordinator.async_press_button("rechts")
        client.send_button_press.assert_called_once_with("rechts")


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


async def _setup(hass: HomeAssistant, cgi: bool = True) -> str:
    entry = _entry(cgi)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.solvis_remote.client.SolvisClient.fetch_data",
        return_value=MOCK_FETCH_RESULT,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("camera", DOMAIN, "3412_display")
    assert entity_id
    return entity_id


class TestServices:
    async def test_touch_calls_coordinator(self, hass: HomeAssistant) -> None:
        entity_id = await _setup(hass)
        with patch.object(SolvisDataUpdateCoordinator, "async_touch", AsyncMock()) as touch:
            await hass.services.async_call(
                DOMAIN, "touch", {"entity_id": entity_id, "x": 120, "y": 218}, blocking=True
            )
        touch.assert_awaited_once_with(120, 218, 0.5)

    async def test_down_up_and_button(self, hass: HomeAssistant) -> None:
        entity_id = await _setup(hass)
        with (
            patch.object(SolvisDataUpdateCoordinator, "async_touch_down", AsyncMock()) as down,
            patch.object(SolvisDataUpdateCoordinator, "async_touch_up", AsyncMock()) as up,
            patch.object(SolvisDataUpdateCoordinator, "async_press_button", AsyncMock()) as button,
        ):
            await hass.services.async_call(
                DOMAIN,
                "touch_down",
                {"entity_id": entity_id, "x": 1, "y": 2, "gesture_id": "g1"},
                blocking=True,
            )
            await hass.services.async_call(
                DOMAIN, "touch_up", {"entity_id": entity_id, "gesture_id": "g1"}, blocking=True
            )
            await hass.services.async_call(
                DOMAIN, "press_button", {"entity_id": entity_id, "button": "links"}, blocking=True
            )
        down.assert_awaited_once_with(1, 2, "g1")
        up.assert_awaited_once_with("g1")
        button.assert_awaited_once_with("links")

    async def test_coordinates_are_bounded(self, hass: HomeAssistant) -> None:
        import voluptuous as vol

        entity_id = await _setup(hass)
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN, "touch", {"entity_id": entity_id, "x": 480, "y": 0}, blocking=True
            )

    async def test_refused_when_cgi_disabled(self, hass: HomeAssistant) -> None:
        entity_id = await _setup(hass, cgi=False)
        with pytest.raises(ServiceValidationError, match="CGI control is disabled"):
            await hass.services.async_call(
                DOMAIN, "press_button", {"entity_id": entity_id, "button": "links"}, blocking=True
            )

    async def test_refused_for_other_entities(self, hass: HomeAssistant) -> None:
        await _setup(hass)
        with pytest.raises(ServiceValidationError, match="not a Solvis display"):
            await hass.services.async_call(
                DOMAIN, "touch_up", {"entity_id": "camera.something_else"}, blocking=True
            )

    async def test_admin_only(self, hass: HomeAssistant, hass_read_only_user) -> None:
        from homeassistant.core import Context

        entity_id = await _setup(hass)
        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                DOMAIN,
                "touch_up",
                {"entity_id": entity_id},
                blocking=True,
                context=Context(user_id=hass_read_only_user.id),
            )
