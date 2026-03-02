"""Image platform for the Solvis Heating integration (Anlagenschema)."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    ANLAGENSCHEMA_FONT_SIZE,
    ANLAGENSCHEMA_OVERLAYS,
    ANLAGENSCHEMA_STATUS_OVERLAY,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import SolvisDataUpdateCoordinator

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).parent / "assets"
_BASE_IMAGE_CANDIDATES = (
    _ASSETS_DIR / "anlagenschema_base.jpg",
    _ASSETS_DIR / "anlagenschema_base.jpeg",
    _ASSETS_DIR / "anlagenschema.jpg",
    _ASSETS_DIR / "anlagenschema_base.png",
)
_FONT_PATH = _ASSETS_DIR / "DejaVuSans.ttf"


def _load_base_image() -> Image.Image | None:
    """Load and fully decode the base diagram image from disk."""
    for image_path in _BASE_IMAGE_CANDIDATES:
        if not image_path.exists():
            continue
        try:
            base_image = Image.open(image_path)
            # Force full load into memory so file handle is released.
            base_image.load()
            logger.info("Loaded anlagenschema base image: %s", image_path.name)
            return base_image
        except (FileNotFoundError, OSError) as err:
            logger.warning("Failed to load anlagenschema base image %s (%s)", image_path, err)

    logger.error(
        "No anlagenschema base image found. Tried: %s",
        ", ".join(str(p.name) for p in _BASE_IMAGE_CANDIDATES),
    )
    return None


def _load_font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load configured font with fallback to Pillow default font."""
    try:
        return ImageFont.truetype(str(_FONT_PATH), ANLAGENSCHEMA_FONT_SIZE)
    except (FileNotFoundError, OSError):
        # Fallback font is intentional for minimal deployments without bundled TTF.
        logger.debug("Anlagenschema font not found at %s, using default", _FONT_PATH)
        return ImageFont.load_default()


def _load_assets() -> tuple[Image.Image | None, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    """Load all on-disk assets in one blocking function (executor only)."""
    return _load_base_image(), _load_font()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Solvis Anlagenschema image entity."""
    coordinator: SolvisDataUpdateCoordinator = entry.runtime_data
    # Disk/font access must happen off the event loop.
    base_image, font = await hass.async_add_executor_job(_load_assets)
    async_add_entities([SolvisAnlagenschema(coordinator, base_image, font)])


class SolvisAnlagenschema(
    CoordinatorEntity[SolvisDataUpdateCoordinator],
    ImageEntity,
):
    """Dynamic system diagram image with live sensor overlays."""

    _attr_content_type = "image/png"
    _attr_has_entity_name = True
    _attr_translation_key = "anlagenschema"

    def __init__(
        self,
        coordinator: SolvisDataUpdateCoordinator,
        base_image: Image.Image | None,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        # Both base classes need explicit init:
        # - ImageEntity initializes access_tokens/client
        # - CoordinatorEntity wires coordinator updates
        ImageEntity.__init__(self, coordinator.hass)
        CoordinatorEntity.__init__(self, coordinator)
        self._attr_unique_id = f"{coordinator.system_id}_anlagenschema"
        self._attr_image_last_updated = dt_util.utcnow()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.system_id)},
            name="Solvis System",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

        # Assets are loaded in async_setup_entry via executor.
        self._base_image = base_image
        self._font = font

        # Render cache
        self._render_signature: tuple | None = None
        self._cached_png: bytes | None = None

    @property
    def available(self) -> bool:
        """Entity is unavailable when base image is missing."""
        return self._base_image is not None and self.coordinator.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        """Signal frontend to refetch image on data update."""
        self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return PNG bytes of the system diagram with sensor overlays."""
        data = self.coordinator.data
        if not data or self._base_image is None:
            return None

        # Build immutable snapshot for the executor (avoid race with poll update)
        snapshot = self._build_snapshot(data)
        signature = self._build_signature(snapshot)

        if signature == self._render_signature and self._cached_png is not None:
            return self._cached_png

        png_bytes = await self.hass.async_add_executor_job(
            self._render_image, snapshot
        )
        self._render_signature = signature
        self._cached_png = png_bytes
        return png_bytes

    @staticmethod
    def _build_snapshot(data: dict[str, Any]) -> dict[str, dict]:
        """Create an immutable snapshot of sensor data needed for rendering."""
        snapshot: dict[str, dict] = {}
        for overlay in ANLAGENSCHEMA_OVERLAYS:
            entry = data.get(overlay["key"])
            snapshot[overlay["key"]] = dict(entry) if entry else {}
        a12 = data.get(ANLAGENSCHEMA_STATUS_OVERLAY["key"])
        snapshot[ANLAGENSCHEMA_STATUS_OVERLAY["key"]] = dict(a12) if a12 else {}
        return snapshot

    @staticmethod
    def _build_signature(snapshot: dict[str, dict]) -> tuple:
        """Build a normalized signature to detect data changes.

        Floats are rounded to 1 decimal to avoid re-renders from jitter.
        """
        values: list = []
        for overlay in ANLAGENSCHEMA_OVERLAYS:
            val = snapshot.get(overlay["key"], {}).get("value")
            if isinstance(val, float):
                val = round(val, 1)
            values.append(val)
        values.append(
            snapshot.get(ANLAGENSCHEMA_STATUS_OVERLAY["key"], {}).get("value")
        )
        return tuple(values)

    def _render_image(self, snapshot: dict[str, dict]) -> bytes:
        """Render the diagram with sensor overlays (runs in executor)."""
        img = self._base_image.copy()  # type: ignore[union-attr]
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size

        # Draw sensor value overlays
        for overlay in ANLAGENSCHEMA_OVERLAYS:
            entry = snapshot.get(overlay["key"], {})
            value = entry.get("value")
            rel_x, rel_y = overlay["rel_pos"]
            pixel_pos = (int(rel_x * w), int(rel_y * h))

            text = "--" if value is None else f"{overlay['format'].format(v=value)}"
            bbox = draw.textbbox(pixel_pos, text, font=self._font)
            pad_x = 6
            pad_y = 3
            bg_box = (
                bbox[0] - pad_x,
                bbox[1] - pad_y,
                bbox[2] + pad_x,
                bbox[3] + pad_y,
            )
            draw.rectangle(bg_box, fill=(255, 255, 255, 190), outline=(90, 90, 90, 120), width=1)
            draw.text(pixel_pos, text, fill=(20, 20, 20, 255), font=self._font)

        # Draw status indicator (a12 burner)
        status = ANLAGENSCHEMA_STATUS_OVERLAY
        a12_entry = snapshot.get(status["key"], {})
        a12_val = a12_entry.get("value")
        rel_x, rel_y = status["rel_pos"]
        pixel_pos = (int(rel_x * w), int(rel_y * h))
        color = status["color_on"] if a12_val == "on" else status["color_off"]
        status_text = status["text"]
        status_bbox = draw.textbbox(pixel_pos, status_text, font=self._font)
        status_bg = (
            status_bbox[0] - 6,
            status_bbox[1] - 3,
            status_bbox[2] + 6,
            status_bbox[3] + 3,
        )
        draw.rectangle(status_bg, fill=(255, 255, 255, 185), outline=(90, 90, 90, 120), width=1)
        draw.text(pixel_pos, status_text, fill=color, font=self._font)

        buf = BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
