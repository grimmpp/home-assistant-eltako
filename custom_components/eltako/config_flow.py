"""Config flows for the Eltako integration."""
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE

from . import gateway
from .const import CONF_GATEWAY, CONF_SERIAL_PATH, DOMAIN, ERROR_INVALID_GATEWAY_PATH, LOGGER
from .gateway import GatewayDeviceTypes


class EltakoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Eltako config flows."""

    VERSION = 1
    MANUAL_PATH_VALUE = "Custom path"

    def __init__(self) -> None:
        """Initialize the Eltako config flow."""

    async def async_step_user(self, user_input=None):
        """Handle an Eltako config flow start."""
        LOGGER.debug(f"[Eltako FlowHandler] user_input {user_input}")
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_detect()

    async def async_step_detect(self, user_input=None):
        """Propose a list of detected gateways."""
        errors = {}
        
        if user_input is not None:
            if CONF_GATEWAY in user_input.keys() and CONF_SERIAL_PATH in user_input[CONF_GATEWAY]:
                if user_input[CONF_GATEWAY][CONF_SERIAL_PATH] == self.MANUAL_PATH_VALUE:
                    return await self.async_step_manual(None)
                
            if await self.validate_eltako_conf(user_input):
                return self.create_eltako_entry(user_input)
            
            errors = {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}

        serial_paths = await self.hass.async_add_executor_job(gateway.detect)
        
        if len(serial_paths) == 0:
            return await self.async_step_manual(user_input)

        serial_paths.append(self.MANUAL_PATH_VALUE)
        
        return self.async_show_form(
            step_id="detect",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL_PATH): vol.In(serial_paths)}),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None):
        """Request manual USB gateway path."""
        default_value = None
        errors = {}
        
        if user_input is not None:
            if await self.validate_eltako_conf(user_input):
                return self.create_eltako_entry(user_input)
            
            if CONF_GATEWAY not in user_input.keys():
                user_input[CONF_GATEWAY] = {}
                user_input[CONF_GATEWAY][CONF_DEVICE] = GatewayDeviceTypes.GatewayEltakoFGW14USB # set default device
            
            default_value = user_input[CONF_GATEWAY][CONF_SERIAL_PATH]
            errors = {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {vol.Required(CONF_SERIAL_PATH, default=default_value): str}
            ),
            errors=errors,
        )

    async def validate_eltako_conf(self, user_input) -> bool:
        """Return True if the user_input contains a valid gateway path."""
        if CONF_GATEWAY not in user_input.keys():
            serial_path = user_input[CONF_GATEWAY][CONF_SERIAL_PATH]
        else:
            serial_path = None

        path_is_valid = await self.hass.async_add_executor_job(
            gateway.validate_path, serial_path
        )
        return path_is_valid

    def create_eltako_entry(self, user_input):
        """Create an entry for the provided configuration."""
        return self.async_create_entry(title="Eltako", data=user_input)
