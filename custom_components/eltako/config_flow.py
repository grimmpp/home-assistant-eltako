"""Config flows for the Eltako integration."""
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr

from . import gateway
from . import config_helpers
from .const import *
from .schema import CONFIG_SCHEMA


class EltakoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Eltako config flows."""

    VERSION = 1
    MANUAL_PATH_VALUE = "Custom path"

    def __init__(self) -> None:
        """Initialize the Eltako config flow."""

    def is_input_available(self, user_input) -> bool:
        if user_input is not None:
            if CONF_SERIAL_PATH not in user_input and user_input[CONF_SERIAL_PATH] is not None:
                if CONF_GATEWAY_DESCRIPTION not in user_input and user_input[CONF_GATEWAY_DESCRIPTION] is not None:
                    return True
        return False

    async def async_step_user(self, user_input=None):
        """Handle an Eltako config flow start."""
        # is called when adding a new gateway
        return await self.async_step_detect()

    async def async_step_detect(self, user_input=None):
        """Propose a list of detected gateways."""
        return await self.manual_selection_routine(user_input)
        
    async def async_step_manual(self, user_input=None):
        """Request manual USB gateway path."""
        return await self.manual_selection_routine(user_input, manual_setp=True)
    
    async def manual_selection_routine(self, user_input=None, manual_setp:bool=False):
        LOGGER.debug("Add new gateway")
        errors = {}
        step_id = "detect"
        if manual_setp:
            step_id = "manual"

        # goes recursively ...
        # check if values were set in the step before
        if user_input is not None:
            if self.is_input_available(user_input):
                
                if await self.validate_eltako_conf(user_input):
                    return self.create_eltako_entry(user_input)
            
            # errors = {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}
            step_id = "manual"

        # find all existing serial paths
        serial_paths = await self.hass.async_add_executor_job(gateway.detect)
        
        if len(serial_paths) == 0:
            step_id = "manual"

        device_registry = dr.async_get(self.hass)
        # get all baseIds of existing/registered gateways so that those will be filtered out for selection
        base_id_of_registed_gateways = await gateway.async_get_base_ids_of_registered_gateway(device_registry)
        g_list = await config_helpers.async_get_list_of_gateways(self.hass, CONFIG_SCHEMA, filter_out=base_id_of_registed_gateways)
        LOGGER.debug("Available gateways to be added: %s", g_list.values())
        if len(g_list) == 0:
            errors = {CONF_GATEWAY_DESCRIPTION: ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE}
        # get all serial paths which are not taken by existing gateways
        serial_paths_of_registered_gateways = await gateway.async_get_serial_path_of_registered_gateway(device_registry)
        serial_paths = [sp for sp in serial_paths if sp not in serial_paths_of_registered_gateways]
        LOGGER.debug("Available serial paths: %s", serial_paths)
        if len(serial_paths) == 0:
            # errors = {CONF_SERIAL_PATH: ERROR_NO_SERIAL_PATH_AVAILABLE}
            step_id = "manual"

        LOGGER.debug("Step mode: %s", step_id)
        if step_id == "manual" and not manual_setp:
            return await self.async_step_manual(user_input)

        # show form in which gateways and serial paths are displayed so that a mapping can be selected.
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_DESCRIPTION): vol.In(g_list.values()),
                vol.Required(CONF_SERIAL_PATH): vol.In(serial_paths),
            }),
            errors=errors,
        )

    async def validate_eltako_conf(self, user_input) -> bool:
        """Return True if the user_input contains a valid gateway path."""
        serial_path: str = user_input[CONF_SERIAL_PATH]
        baud_rate: int = -1
        gateway_selection: str = user_input[CONF_GATEWAY_DESCRIPTION]

        # LOGGER.debug("serial_path: %s", serial_path)
        # LOGGER.debug("gateway_selection: %s", gateway_selection)
        for gdc in gateway.GatewayDeviceType:
            if gdc in gateway_selection:
                baud_rate = gateway.BAUD_RATE_DEVICE_TYPE_MAPPING[gdc]
                break

        path_is_valid = await self.hass.async_add_executor_job(
            gateway.validate_path, serial_path, baud_rate
        )
        return path_is_valid

    def create_eltako_entry(self, user_input):
        """Create an entry for the provided configuration."""
        return self.async_create_entry(title="Eltako", data=user_input)
