"""DataUpdateCoordinator for the Solvis Heating integration."""

from __future__ import annotations

import asyncio
import logging
import random
import time as time_mod
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    SolvisClient,
    SolvisAuthError,
    SolvisBusyError,
    SolvisConnectionError,
    SolvisPayloadError,
)
from .const import (
    BUSY_RETRY_ATTEMPTS,
    BUSY_RETRY_DELAY,
    CGI_SECTIONS,
    CONF_CGI_PROFILES,
    DEFAULT_CGI_PROFILES,
    TOUCH_MAX_HOLD,
    TOUCH_MIN_HOLD,
    TOUCH_RELEASE,
)

logger = logging.getLogger(__name__)


def _busy_delay() -> float:
    """Return the retry delay with jitter.

    Both this integration and the other program polling the controller run on
    fixed intervals. A fixed retry delay would keep them phase-locked on the
    single session the controller offers, so spread the retries out.
    """
    return BUSY_RETRY_DELAY * random.uniform(0.5, 1.5)


@dataclass
class _Gesture:
    """A touch held on the display between touch_down and touch_up.

    While it is held the gesture owns the command lock, so no CGI profile
    sequence or other command can land between press and release.
    """

    locked: bool = False
    started: float = 0.0
    release_requested: bool = False
    watchdog: asyncio.TimerHandle | None = None


class SolvisDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls a Solvis controller and computes derived values."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SolvisClient,
        scan_interval: int,
        system_id: str,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name="Solvis",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.system_id = system_id
        self._command_lock = asyncio.Lock()
        self._last_command_time: float = 0
        self._gesture: _Gesture | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the controller and compute derived values."""
        async with self._command_lock:
            try:
                raw_data = await self.hass.async_add_executor_job(
                    self.client.fetch_data
                )
            except SolvisBusyError as err:
                # Another client holds the controller's single session. Not a
                # credentials problem, and not worth retrying here: the next
                # poll is only scan_interval away, and hammering the box while
                # the other client works would just add contention.
                raise UpdateFailed(f"Controller busy: {err}") from err
            except SolvisAuthError as err:
                raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
            except SolvisConnectionError as err:
                raise UpdateFailed(f"Connection error: {err}") from err
            except SolvisPayloadError as err:
                raise UpdateFailed(f"Invalid payload: {err}") from err

        # Compute derived values
        data: dict[str, Any] = {}
        for key, entry in raw_data.items():
            data[key] = entry

        self._compute_derived(data)
        return data

    async def async_execute_cgi_command(
        self, profile_key: str, option_key: str
    ) -> None:
        """Execute a CGI command sequence for the given profile and option.

        Raises:
            HomeAssistantError: If profile or option is unknown.
            ConfigEntryAuthFailed: If authentication fails (triggers reauth).
            SolvisConnectionError: If a network error occurs.
        """
        profiles = self.config_entry.options.get(
            CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES
        )
        profile = profiles.get(profile_key)
        if profile is None:
            raise HomeAssistantError(f"Unknown CGI profile: {profile_key}")
        option = profile["options"].get(option_key)
        if option is None:
            raise HomeAssistantError(
                f"Unknown option '{option_key}' in profile '{profile_key}'"
            )

        section_key = profile.get("section")
        section_touch = None
        if section_key:
            section_touch = CGI_SECTIONS.get(section_key)
            if section_touch is None:
                raise HomeAssistantError(
                    f"Invalid CGI section '{section_key}' in profile '{profile_key}'"
                )

        sequence = {
            "wakeup_count": profile["wakeup_count"],
            "wakeup_delay": profile["wakeup_delay"],
            "section_touch": section_touch,
            "x": option["x"],
            "y": option["y"],
            "reset_touch": profile.get("reset_touch"),
        }

        async with self._command_lock:
            # Cooldown: at least 500ms since last command
            now = time_mod.monotonic()
            elapsed = now - self._last_command_time
            if elapsed < 0.5:
                await asyncio.sleep(0.5 - elapsed)
            for attempt in range(1, BUSY_RETRY_ATTEMPTS + 1):
                try:
                    await self.hass.async_add_executor_job(
                        self.client.execute_cgi_sequence, sequence
                    )
                    break
                except SolvisBusyError as err:
                    if err.partial:
                        # An earlier step of the touch sequence completed, so
                        # the touch that changes the value may already have
                        # been applied. Replaying it would apply it twice,
                        # which for a momentary action means triggering it
                        # a second time.
                        raise HomeAssistantError(
                            "Controller became busy mid-sequence; command may "
                            f"have been applied partially, not retrying: {err}"
                        ) from err
                    if attempt == BUSY_RETRY_ATTEMPTS:
                        raise HomeAssistantError(
                            f"Controller busy, command refused after "
                            f"{BUSY_RETRY_ATTEMPTS} attempts: {err}"
                        ) from err
                    # Only 403 is retried. A request that took effect but
                    # whose response was lost surfaces as
                    # SolvisConnectionError and deliberately escapes here.
                    await asyncio.sleep(_busy_delay())
                except SolvisAuthError as err:
                    raise ConfigEntryAuthFailed(
                        f"CGI auth failed: {err}"
                    ) from err
            self._last_command_time = time_mod.monotonic()

    # ------------------------------------------------------------------
    # Remote display: touch and buttons (like the controller's remote.html)
    # ------------------------------------------------------------------

    def _raise_if_operated(self) -> None:
        """Refuse a command while someone holds a touch on the display."""
        if self._gesture is not None:
            raise HomeAssistantError("The Solvis display is being operated")

    async def _async_wait_cooldown(self) -> None:
        """Keep at least 500 ms between two commands."""
        elapsed = time_mod.monotonic() - self._last_command_time
        if elapsed < 0.5:
            await asyncio.sleep(0.5 - elapsed)

    async def _async_send(self, func: Any, *args: Any) -> None:
        """Run one client command in the executor, mapped to HA errors.

        Not retried: a touch that is sent twice is tapped twice.
        """
        try:
            await self.hass.async_add_executor_job(func, *args)
        except SolvisAuthError as err:
            raise ConfigEntryAuthFailed(f"CGI auth failed: {err}") from err
        except (SolvisBusyError, SolvisConnectionError) as err:
            raise HomeAssistantError(f"Solvis command failed: {err}") from err

    async def _async_release_touch(self) -> None:
        """Release the touch, retrying once; a failure can only be logged."""
        for attempt in (1, 2):
            try:
                await self.hass.async_add_executor_job(
                    self.client.send_touch, TOUCH_RELEASE["x"], TOUCH_RELEASE["y"]
                )
                return
            except (SolvisAuthError, SolvisBusyError, SolvisConnectionError) as err:
                if attempt == 2:
                    logger.warning("Could not release the Solvis display touch: %s", err)
                    return
                await asyncio.sleep(TOUCH_MIN_HOLD)

    async def async_touch(self, x: int, y: int, duration: float = TOUCH_MIN_HOLD) -> None:
        """Tap the display: press, hold for `duration`, release."""
        self._raise_if_operated()
        async with self._command_lock:
            await self._async_wait_cooldown()
            try:
                await self._async_send(self.client.send_touch, x, y)
                await asyncio.sleep(max(duration, TOUCH_MIN_HOLD))
            finally:
                await asyncio.shield(self._async_release_touch())
                self._last_command_time = time_mod.monotonic()

    async def async_touch_down(self, x: int, y: int) -> None:
        """Press the display and hold until async_touch_up or the watchdog."""
        self._raise_if_operated()
        gesture = self._gesture = _Gesture()
        try:
            await self._command_lock.acquire()
        except asyncio.CancelledError:
            self._gesture = None
            raise
        gesture.locked = True
        try:
            await self._async_wait_cooldown()
            await self._async_send(self.client.send_touch, x, y)
        except BaseException:
            # The press may have reached the controller (lost response).
            await asyncio.shield(self._async_release_touch())
            self._gesture = None
            self._last_command_time = time_mod.monotonic()
            self._command_lock.release()
            raise
        gesture.started = time_mod.monotonic()
        if gesture.release_requested:
            await self._async_finish_gesture(gesture)
            return
        gesture.watchdog = self.hass.loop.call_later(
            TOUCH_MAX_HOLD,
            lambda: self.hass.async_create_task(self._async_finish_gesture(gesture)),
        )

    async def async_touch_up(self) -> None:
        """Release the held touch; without one this does nothing."""
        gesture = self._gesture
        if gesture is None:
            return
        if not gesture.started:
            # The press is still on its way; touch_down releases right after.
            gesture.release_requested = True
            return
        await self._async_finish_gesture(gesture)

    async def _async_finish_gesture(self, gesture: _Gesture) -> None:
        """Release a pressed gesture once: keep the minimum hold, free the lock."""
        if self._gesture is not gesture:
            return
        self._gesture = None
        if gesture.watchdog is not None:
            gesture.watchdog.cancel()
        try:
            remaining = TOUCH_MIN_HOLD - (time_mod.monotonic() - gesture.started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            await asyncio.shield(self._async_release_touch())
        finally:
            self._last_command_time = time_mod.monotonic()
            self._command_lock.release()

    async def async_press_button(self, button: str) -> None:
        """Press one of the two hardware buttons next to the display."""
        self._raise_if_operated()
        async with self._command_lock:
            await self._async_wait_cooldown()
            try:
                await self._async_send(self.client.send_button_press, button)
            finally:
                self._last_command_time = time_mod.monotonic()

    async def async_shutdown(self) -> None:
        """Release a touch that is still held when the entry unloads."""
        gesture = self._gesture
        if gesture is not None:
            if gesture.started:
                await self._async_finish_gesture(gesture)
            else:
                gesture.release_requested = True
        await super().async_shutdown()

    def _compute_derived(self, data: dict[str, Any]) -> None:
        """Add computed sensors (delta_s5s6, brennerleistung) to data dict."""
        s5_val = data.get("s5", {}).get("value")
        s6_val = data.get("s6", {}).get("value")

        if s5_val is not None and s6_val is not None:
            data["delta_s5s6"] = {
                "title": "Delta Vorlauf/Ruecklauf",
                "value": round(s5_val - s6_val, 1),
                "unit": "K",
                "raw": None,
            }
        else:
            data["delta_s5s6"] = {"title": "Delta Vorlauf/Ruecklauf", "value": None, "unit": "K", "raw": None}

        a12_val = data.get("a12", {}).get("value")
        ao1_val = data.get("ao1", {}).get("value")

        if a12_val == "on" and ao1_val is not None:
            data["brennerleistung"] = {
                "title": "Brennerleistung",
                "value": round(5.0 + ao1_val * 15.0 / 100.0, 2),
                "unit": "kW",
                "raw": None,
            }
        else:
            data["brennerleistung"] = {"title": "Brennerleistung", "value": 0.0, "unit": "kW", "raw": None}
