"""Config flow for the Solvis Heating integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback

from .client import SolvisClient, SolvisAuthError, SolvisConnectionError, SolvisPayloadError
from .const import (
    DOMAIN,
    CONF_REALM,
    CONF_SCAN_INTERVAL,
    DEFAULT_REALM,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
)

logger = logging.getLogger(__name__)

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
        client = SolvisClient(
            host=data[CONF_HOST],
            username=data[CONF_USERNAME],
            password=data[CONF_PASSWORD],
            realm=data.get(CONF_REALM, DEFAULT_REALM),
            timeout=DEFAULT_TIMEOUT,
        )
        try:
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the options step — connection params + scan interval."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection with the (potentially changed) parameters
            test_data = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_REALM: user_input.get(CONF_REALM, DEFAULT_REALM),
            }
            client = SolvisClient(
                host=test_data[CONF_HOST],
                username=test_data[CONF_USERNAME],
                password=test_data[CONF_PASSWORD],
                realm=test_data[CONF_REALM],
                timeout=DEFAULT_TIMEOUT,
            )
            try:
                await self.hass.async_add_executor_job(client.fetch_data)
            except SolvisAuthError:
                errors["base"] = "invalid_auth"
            except SolvisConnectionError:
                errors["base"] = "cannot_connect"
            except SolvisPayloadError:
                errors["base"] = "invalid_payload"
            except Exception:
                logger.exception("Unexpected error during options connection test")
                errors["base"] = "cannot_connect"

            if not errors:
                # Persist connection params in data, scan_interval in options
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_REALM: user_input.get(CONF_REALM, DEFAULT_REALM),
                    },
                )
                return self.async_create_entry(
                    data={CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]},
                )

        # Pre-fill with current values
        entry = self.config_entry
        current_host = entry.data.get(CONF_HOST, "")
        current_user = entry.data.get(CONF_USERNAME, "")
        current_pass = entry.data.get(CONF_PASSWORD, "")
        current_realm = entry.data.get(CONF_REALM, DEFAULT_REALM)
        current_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current_host): str,
                    vol.Required(CONF_USERNAME, default=current_user): str,
                    vol.Required(CONF_PASSWORD, default=current_pass): str,
                    vol.Optional(CONF_REALM, default=current_realm): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(
                        int,
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
            errors=errors,
        )
