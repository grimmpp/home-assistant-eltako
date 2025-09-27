"""Simplified config flow for testing dependency installation."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_GATEWAY_DESCRIPTION, CONF_SERIAL_PATH

_LOGGER = logging.getLogger(__name__)


class EltakoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Simplified Eltako config flow for testing."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Basic validation
            gateway_description = user_input.get(CONF_GATEWAY_DESCRIPTION, "")
            serial_path = user_input.get(CONF_SERIAL_PATH, "")

            if not gateway_description:
                errors[CONF_GATEWAY_DESCRIPTION] = "Gateway description required"
            if not serial_path:
                errors[CONF_SERIAL_PATH] = "Serial path required"

            if not errors:
                # Create entry - this should trigger dependency installation
                return self.async_create_entry(
                    title="Eltako",
                    data={
                        CONF_GATEWAY_DESCRIPTION: gateway_description,
                        CONF_SERIAL_PATH: serial_path,
                    }
                )

        # Show form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_DESCRIPTION, default="Test Gateway (Gateway-0)"): str,
                vol.Required(CONF_SERIAL_PATH, default="/dev/ttyUSB0"): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return EltakoOptionsFlowHandler(config_entry)


class EltakoOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Eltako options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional("test_option", default=False): bool,
            })
        )