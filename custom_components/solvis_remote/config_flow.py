"""Config flow for the Solvis Heating integration."""

from __future__ import annotations

from functools import partial
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback

from .client import SolvisClient, SolvisAuthError, SolvisConnectionError, SolvisPayloadError
from .const import (
    CGI_COORD_MAX,
    CGI_DELAY_MAX,
    CGI_DELAY_MIN,
    CGI_SECTIONS,
    CGI_WAKEUP_MAX,
    CONF_CGI_PROFILES,
    CONF_ENABLE_CGI,
    CONF_REALM,
    CONF_SCAN_INTERVAL,
    DEFAULT_CGI_PROFILES,
    DEFAULT_REALM,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

logger = logging.getLogger(__name__)

_MENU_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "edit": "Edit",
        "delete": "Delete",
        "add": "Add new profile",
        "back": "Back",
        "none": "None",
    },
    "de": {
        "edit": "Bearbeiten",
        "delete": "Loeschen",
        "add": "Neues Profil hinzufuegen",
        "back": "Zurueck",
        "none": "Keine",
    },
}

_SECTION_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "heizung": "Heating",
        "wasser": "Water",
        "zirkulation": "Circulation",
        "solar": "Solar",
        "sonstig": "Misc",
    },
    "de": {
        "heizung": "Heizung",
        "wasser": "Wasser",
        "zirkulation": "Zirkulation",
        "solar": "Solar",
        "sonstig": "Sonstiges",
    },
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_REALM, default=DEFAULT_REALM): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

# Regex for valid profile keys: lowercase alphanumeric + underscore
_PROFILE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")


def _parse_cgi_options(text: str) -> dict[str, dict] | None:
    """Parse CGI options from multiline text.

    Format: key:label:x:y (one per line)
    Returns dict or None if invalid.
    """
    options: dict[str, dict] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(":")
        if len(parts) != 4:
            return None
        key, label, x_str, y_str = [p.strip() for p in parts]
        if not key or not label:
            return None
        try:
            x = int(x_str)
            y = int(y_str)
        except ValueError:
            return None
        if not (0 <= x <= CGI_COORD_MAX and 0 <= y <= CGI_COORD_MAX):
            return None
        if key in options:
            return None  # Duplicate option key
        options[key] = {"label": label, "x": x, "y": y}
    return options if options else None


def _options_to_text(options: dict[str, dict]) -> str:
    """Convert CGI options dict to multiline text for editing."""
    lines = []
    for key, opt in options.items():
        lines.append(f"{key}:{opt['label']}:{opt['x']}:{opt['y']}")
    return "\n".join(lines)


class SolvisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solvis Heating."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            result = await self._test_connection(user_input)
            if isinstance(result, str):
                errors["base"] = result
            else:
                # result is fetch_data dict — extract system_id for unique_id
                system_raw = result.get("system", {}).get("raw", "")
                system_id = system_raw if system_raw else user_input[CONF_HOST]

                await self.async_set_unique_id(system_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Solvis ({user_input[CONF_HOST]})",
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_REALM: user_input.get(CONF_REALM, DEFAULT_REALM),
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth triggered by ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the reauth confirmation step."""
        errors: dict[str, str] = {}

        entry = self._get_reauth_entry()

        if user_input is not None:
            test_data = {
                CONF_HOST: entry.data[CONF_HOST],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_REALM: entry.data.get(CONF_REALM, DEFAULT_REALM),
            }
            result = await self._test_connection(test_data)
            if isinstance(result, str):
                errors["base"] = result
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, **user_input},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
        )

    async def _test_connection(self, data: dict[str, Any]) -> dict | str:
        """Test connection to the Solvis controller.

        Returns the fetch_data dict on success, or an error key string on failure.
        """
        try:
            client = await self.hass.async_add_executor_job(
                partial(
                    SolvisClient,
                    host=data[CONF_HOST],
                    username=data[CONF_USERNAME],
                    password=data[CONF_PASSWORD],
                    realm=data.get(CONF_REALM, DEFAULT_REALM),
                    timeout=DEFAULT_TIMEOUT,
                )
            )
            return await self.hass.async_add_executor_job(client.fetch_data)
        except SolvisAuthError:
            return "invalid_auth"
        except SolvisConnectionError:
            return "cannot_connect"
        except SolvisPayloadError:
            return "invalid_payload"
        except Exception:
            logger.exception("Unexpected error during connection test")
            return "cannot_connect"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SolvisOptionsFlow:
        """Return the options flow handler."""
        return SolvisOptionsFlow()


class SolvisOptionsFlow(OptionsFlow):
    """Handle options for the Solvis Heating integration."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._editing_profile_key: str | None = None

    def _lang(self) -> str:
        """Return language bucket for UI labels."""
        language = getattr(self.hass.config, "language", "en") or "en"
        return "de" if language.startswith("de") else "en"

    def _menu_label(self, key: str) -> str:
        """Return localized static menu label."""
        return _MENU_LABELS[self._lang()][key]

    def _section_options(self) -> dict[str, str]:
        """Return localized section dropdown options."""
        lang = self._lang()
        labels = _SECTION_LABELS[lang]
        options = {"": self._menu_label("none")}
        for key in CGI_SECTIONS:
            options[key] = labels[key]
        return options

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "cgi_menu"],
        )

    # ------------------------------------------------------------------
    # Settings step (scan_interval + enable_cgi_control)
    # ------------------------------------------------------------------

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle scan interval and CGI enable toggle."""
        if user_input is not None:
            # Preserve existing CGI profiles (never persist None)
            existing_profiles = self.config_entry.options.get(CONF_CGI_PROFILES)
            data: dict[str, Any] = {
                CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                CONF_ENABLE_CGI: user_input.get(CONF_ENABLE_CGI, False),
            }
            if existing_profiles is not None:
                data[CONF_CGI_PROFILES] = existing_profiles
            return self.async_create_entry(data=data)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_enable_cgi = self.config_entry.options.get(CONF_ENABLE_CGI, False)

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(
                        int,
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Optional(
                        CONF_ENABLE_CGI,
                        default=current_enable_cgi,
                    ): bool,
                }
            ),
        )

    # ------------------------------------------------------------------
    # CGI profile management
    # ------------------------------------------------------------------

    def _get_profiles(self) -> dict[str, dict]:
        """Get current CGI profiles (from options or fallback)."""
        return dict(
            self.config_entry.options.get(CONF_CGI_PROFILES, DEFAULT_CGI_PROFILES)
        )

    def _save_profiles(self, profiles: dict[str, dict]) -> ConfigFlowResult:
        """Save CGI profiles and return create_entry result."""
        return self.async_create_entry(
            data={
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                ),
                CONF_ENABLE_CGI: self.config_entry.options.get(
                    CONF_ENABLE_CGI, False
                ),
                CONF_CGI_PROFILES: profiles,
            },
        )

    async def async_step_cgi_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show CGI profile management menu."""
        profiles = self._get_profiles()

        if user_input is not None:
            selected = user_input.get("profile")
            if selected == "__new__":
                return await self.async_step_cgi_add()
            if selected == "__back__":
                return await self.async_step_init()
            if selected and selected.startswith("edit:"):
                self._editing_profile_key = selected[5:]
                return await self.async_step_cgi_edit()
            if selected and selected.startswith("delete:"):
                self._editing_profile_key = selected[7:]
                return await self.async_step_cgi_delete()

        # Build selection options
        options_list: list[tuple[str, str]] = []
        for key, profile in profiles.items():
            options_list.append(
                (f"edit:{key}", f"{self._menu_label('edit')}: {profile['name']}")
            )
            options_list.append(
                (f"delete:{key}", f"{self._menu_label('delete')}: {profile['name']}")
            )
        options_list.append(("__new__", self._menu_label("add")))
        options_list.append(("__back__", self._menu_label("back")))

        return self.async_show_form(
            step_id="cgi_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("profile"): vol.In(
                        {k: label for k, label in options_list}
                    ),
                }
            ),
        )

    async def async_step_cgi_add(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a new CGI profile."""
        errors: dict[str, str] = {}

        if user_input is not None:
            profile_key = user_input["profile_key"].strip().lower()
            profiles = self._get_profiles()

            # Validate key
            if not _PROFILE_KEY_RE.match(profile_key):
                errors["base"] = "invalid_profile"
            elif profile_key in profiles:
                errors["base"] = "duplicate_key"
            else:
                # Parse options
                options = _parse_cgi_options(user_input["options_text"])
                if options is None:
                    errors["base"] = "no_options"
                else:
                    wakeup_count = user_input.get("wakeup_count", 4)
                    wakeup_delay = user_input.get("wakeup_delay", 1.0)
                    reset_x = user_input.get("reset_x", 510)
                    reset_y = user_input.get("reset_y", 510)

                    new_profile: dict[str, Any] = {
                        "name": user_input["name"],
                        "device_group": user_input.get("device_group", "CGI Control"),
                        "icon": user_input.get("icon", "mdi:gesture-tap"),
                        "wakeup_count": wakeup_count,
                        "wakeup_delay": wakeup_delay,
                        "reset_touch": {"x": reset_x, "y": reset_y},
                        "options": options,
                    }
                    section = user_input.get("section", "")
                    if section:
                        new_profile["section"] = section
                    profiles[profile_key] = new_profile
                    return self._save_profiles(profiles)

        return self.async_show_form(
            step_id="cgi_add",
            data_schema=vol.Schema(
                {
                    vol.Required("profile_key"): str,
                    vol.Required("name"): str,
                    vol.Optional("device_group", default="CGI Control"): str,
                    vol.Optional("icon", default="mdi:gesture-tap"): str,
                    vol.Optional("section", default=""): vol.In(
                        self._section_options()
                    ),
                    vol.Optional("wakeup_count", default=4): vol.All(
                        int, vol.Range(min=0, max=CGI_WAKEUP_MAX)
                    ),
                    vol.Optional("wakeup_delay", default=1.0): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=CGI_DELAY_MIN, max=CGI_DELAY_MAX),
                    ),
                    vol.Optional("reset_x", default=510): vol.All(
                        int, vol.Range(min=0, max=CGI_COORD_MAX)
                    ),
                    vol.Optional("reset_y", default=510): vol.All(
                        int, vol.Range(min=0, max=CGI_COORD_MAX)
                    ),
                    vol.Required("options_text"): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "options_format": "key:label:x:y (one per line)",
            },
        )

    async def async_step_cgi_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit an existing CGI profile (key is immutable)."""
        errors: dict[str, str] = {}
        profile_key = self._editing_profile_key
        profiles = self._get_profiles()
        profile = profiles.get(profile_key, {})

        if user_input is not None:
            options = _parse_cgi_options(user_input["options_text"])
            if options is None:
                errors["base"] = "no_options"
            else:
                updated_profile: dict[str, Any] = {
                    "name": user_input["name"],
                    "device_group": user_input.get(
                        "device_group", profile.get("device_group", "CGI Control")
                    ),
                    "icon": user_input.get("icon", profile.get("icon", "mdi:gesture-tap")),
                    "wakeup_count": user_input.get("wakeup_count", 4),
                    "wakeup_delay": user_input.get("wakeup_delay", 1.0),
                    "reset_touch": {
                        "x": user_input.get("reset_x", 510),
                        "y": user_input.get("reset_y", 510),
                    },
                    "options": options,
                }
                section = user_input.get("section", "")
                if section:
                    updated_profile["section"] = section
                profiles[profile_key] = updated_profile
                return self._save_profiles(profiles)

        # Pre-fill with current values
        current_options_text = _options_to_text(profile.get("options", {}))
        reset = profile.get("reset_touch", {"x": 510, "y": 510})

        return self.async_show_form(
            step_id="cgi_edit",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=profile.get("name", "")): str,
                    vol.Optional(
                        "device_group",
                        default=profile.get("device_group", "CGI Control"),
                    ): str,
                    vol.Optional(
                        "icon",
                        default=profile.get("icon", "mdi:gesture-tap"),
                    ): str,
                    vol.Optional(
                        "section",
                        default=profile.get("section", ""),
                    ): vol.In(self._section_options()),
                    vol.Optional(
                        "wakeup_count",
                        default=profile.get("wakeup_count", 4),
                    ): vol.All(int, vol.Range(min=0, max=CGI_WAKEUP_MAX)),
                    vol.Optional(
                        "wakeup_delay",
                        default=profile.get("wakeup_delay", 1.0),
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=CGI_DELAY_MIN, max=CGI_DELAY_MAX),
                    ),
                    vol.Optional("reset_x", default=reset.get("x", 510)): vol.All(
                        int, vol.Range(min=0, max=CGI_COORD_MAX)
                    ),
                    vol.Optional("reset_y", default=reset.get("y", 510)): vol.All(
                        int, vol.Range(min=0, max=CGI_COORD_MAX)
                    ),
                    vol.Required("options_text", default=current_options_text): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "profile_key": profile_key,
                "options_format": "key:label:x:y (one per line)",
            },
        )

    async def async_step_cgi_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a CGI profile."""
        profile_key = self._editing_profile_key
        profiles = self._get_profiles()
        profile = profiles.get(profile_key, {})

        if user_input is not None:
            if user_input.get("confirm"):
                profiles.pop(profile_key, None)
                return self._save_profiles(profiles)
            return await self.async_step_cgi_menu()

        return self.async_show_form(
            step_id="cgi_delete",
            data_schema=vol.Schema(
                {
                    vol.Required("confirm", default=False): bool,
                }
            ),
            description_placeholders={
                "profile_name": profile.get("name", profile_key),
            },
        )
