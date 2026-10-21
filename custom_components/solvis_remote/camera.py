"""Camera platform for the Solvis Heating integration (remote display).

Shows the controller's display like its own remote.html page does. The
frontend polls still images; HA only fetches while someone looks.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
import logging
import time

from PIL import Image

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import (
    SolvisAuthError,
    SolvisBusyError,
    SolvisConnectionError,
    SolvisPayloadError,
)
from .const import DISPLAY_FRAME_MAX_AGE, DOMAIN, MANUFACTURER, MODEL
from .coordinator import SolvisDataUpdateCoordinator

logger = logging.getLogger(__name__)


def bmp_to_png(bmp: bytes) -> bytes:
    """Convert the controller's 4-bit BMP to PNG at its native 240x128."""
    with Image.open(BytesIO(bmp)) as img:
        buf = BytesIO()
        img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solvis display camera."""
    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data
    async_add_entities([SolvisDisplayCamera(coordinator)])


class SolvisDisplayCamera(CoordinatorEntity[SolvisDataUpdateCoordinator], Camera):
    """The controller display as a camera, one fetch shared by all viewers."""

    _attr_has_entity_name = True
    _attr_translation_key = "display"
    _attr_content_type = "image/png"

    def __init__(self, coordinator: SolvisDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{coordinator.system_id}_display"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.system_id)},
            name="Solvis System",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._frame: bytes | None = None
        self._frame_time: float = 0.0
        self._fetch: asyncio.Future[bytes | None] | None = None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the current display as PNG, or None if it cannot be read.

        Viewers asking within DISPLAY_FRAME_MAX_AGE share a frame, and a
        running fetch is awaited instead of starting a second one.
        """
        if self._frame is not None and time.monotonic() - self._frame_time < DISPLAY_FRAME_MAX_AGE:
            return self._frame
        if self._fetch is not None:
            return await asyncio.shield(self._fetch)

        fetch = self._fetch = self.hass.loop.create_future()
        frame: bytes | None = None
        try:
            bmp = await self.hass.async_add_executor_job(
                self.coordinator.client.fetch_display
            )
            frame = await self.hass.async_add_executor_job(bmp_to_png, bmp)
            self._frame, self._frame_time = frame, time.monotonic()
        except (
            SolvisAuthError,
            SolvisBusyError,
            SolvisConnectionError,
            SolvisPayloadError,
            OSError,
        ) as err:
            # The frontend shows the error and retries; keep the log quiet.
            logger.debug("Solvis display not readable: %s", err)
        finally:
            fetch.set_result(frame)
            self._fetch = None
        return frame
