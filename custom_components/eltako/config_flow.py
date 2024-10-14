"""Config flows for the Eltako integration."""
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler

import voluptuous as vol

import ipaddress

from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_NAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr

# from virtual_network_gateway import TCP_SERVER_PORT
from . import gateway
from . import config_helpers
from .const import *
from .schema import CONFIG_SCHEMA


class EltakoFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Eltako config flows."""

    VERSION = 1
    MINOR_VERSION = 1
    MANUAL_PATH_VALUE = "Custom path"

    def __init__(self) -> None:
        """Initialize the Eltako config flow."""

    def is_input_available(self, user_input) -> bool:
        LOGGER.debug("Check available data")
        if user_input is not None:
            if CONF_SERIAL_PATH in user_input and user_input[CONF_SERIAL_PATH] is not None:
                if CONF_GATEWAY_DESCRIPTION in user_input and user_input[CONF_GATEWAY_DESCRIPTION] is not None:
                    return True
        return False

    async def async_step_user(self, user_input=None):
        """Handle an Eltako config flow start."""
        # is called when adding a new gateway
        LOGGER.debug("config_flow user step started.")
        return await self.async_step_detect()

    async def async_step_detect(self, user_input=None):
        """Propose a list of detected gateways."""
        LOGGER.debug("config_flow detect step started.")
        return await self.manual_selection_routine(user_input)
        
    async def async_step_manual(self, user_input=None):
        """Request manual USB gateway path."""
        LOGGER.debug("config_flow manual step started.")
        return await self.manual_selection_routine(user_input, manual_setp=True)
    
    async def manual_selection_routine(self, user_input=None, manual_setp:bool=False):
        LOGGER.debug("Add new gateway")
        errors = {}

        if DATA_ELTAKO in self.hass.data:
            LOGGER.debug("Available Eltako Objects")
            for g in self.hass.data[DATA_ELTAKO]:
                LOGGER.debug(g)

        # get configuration for debug purpose
        config = await config_helpers.async_get_home_assistant_config(self.hass, CONFIG_SCHEMA)
        LOGGER.debug(f"Config: {config}\n")

        # ensure data entry is set
        if DATA_ELTAKO not in self.hass.data:
            LOGGER.debug("No configuration available.")
            self.hass.data.setdefault(DATA_ELTAKO, {})

        # goes recursively ...
        # check if values were set in the step before
        if user_input is not None:
            if self.is_input_available(user_input):
                if await self.validate_eltako_conf(user_input):
                    return self.create_eltako_entry(user_input)
            
                errors = {CONF_SERIAL_PATH: ERROR_INVALID_GATEWAY_PATH}

        LOGGER.debug("Get data for gateway selection")

        # find all existing serial paths
        serial_paths = await self.hass.async_add_executor_job(gateway.detect)
        
        # get available (not registered) gateways
        g_list_dict = (await config_helpers.async_get_list_of_gateway_descriptions(self.hass, CONFIG_SCHEMA)) 
        # add virtual lan gateway manually
        virt_gw_id = -123
        virt_gw = {
            CONF_ID: virt_gw_id,
            CONF_NAME: CONF_VIRTUAL_NETWORK_GATEWAY,
            CONF_DEVICE_TYPE: GatewayDeviceType.LAN_ESP2.value,
            CONF_GATEWAY_ADDRESS: "homeassistant.local",
            CONF_GATEWAY_PORT: 12345
        }
        g_list_dict[virt_gw_id] = config_helpers.get_gateway_name(virt_gw[CONF_ID], virt_gw[CONF_DEVICE_TYPE], virt_gw_id)
        # filter out registered gateways. all registered gateways are listen in data section
        g_list = list([g for g in g_list_dict.values() if g not in self.hass.data[DATA_ELTAKO] and 'gateway_'+str(config_helpers.get_id_from_gateway_name(g)) not in self.hass.data[DATA_ELTAKO]])
        LOGGER.debug("Available gateways to be added: %s", g_list)
        if len(g_list) == 0:
            LOGGER.debug("No gateways are configured in the 'configuration.yaml'.")
            errors = {CONF_GATEWAY_DESCRIPTION: ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE}

        # add manually added serial paths and ip addresses from configuration
        for g_id in g_list_dict.keys():
            g_c = config_helpers.find_gateway_config_by_id(config, g_id)
            if g_c is None and g_id == virt_gw_id:
                g_c = virt_gw
            if CONF_SERIAL_PATH in g_c:
                serial_paths.append(g_c[CONF_SERIAL_PATH])
            if CONF_GATEWAY_ADDRESS in g_c:
                address = g_c[CONF_GATEWAY_ADDRESS]
                serial_paths.append(address)

        # get all serial paths which are not taken by existing gateways
        device_registry = dr.async_get(self.hass)
        serial_paths_of_registered_gateways = await gateway.async_get_serial_path_of_registered_gateway(device_registry)
        serial_paths = list(set([sp for sp in serial_paths if sp not in serial_paths_of_registered_gateways]))
        LOGGER.debug("Available serial paths/IP addresses: %s", serial_paths)

        if manual_setp or len(serial_paths) == 0:
            LOGGER.debug("No usb port or any manually configured address available.")
            errors = {CONF_SERIAL_PATH: ERROR_NO_SERIAL_PATH_AVAILABLE}
                
            return self.async_show_form(
                step_id="manual",
                data_schema=vol.Schema({
                    vol.Required(CONF_GATEWAY_DESCRIPTION, msg="EnOcean Gateway", description="Gateway to be initialized."): vol.In(g_list),
                    vol.Required(CONF_SERIAL_PATH, msg="Serial Port/IP Address", description="Serial path/IP address for selected gateway."): str
                }),
                errors=errors,
            )


        # show form in which gateways and serial paths are displayed so that a mapping can be selected.
        return self.async_show_form(
            step_id="detect",
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_DESCRIPTION, msg="EnOcean Gateway", description="Gateway to be initialized."): vol.In(g_list),
                vol.Required(CONF_SERIAL_PATH, msg="Serial Port/IP Address", description="Serial path/IP address for selected gateway."): vol.In(serial_paths),
            }),
            errors=errors,
        )

    async def validate_eltako_conf(self, user_input) -> bool:
        """Return True if the user_input contains a valid gateway path."""
        serial_path: str = user_input[CONF_SERIAL_PATH]
        baud_rate: int = -1
        gateway_selection: str = user_input[CONF_GATEWAY_DESCRIPTION]

        LOGGER.debug("Start serial path validation for %s", gateway_selection)

        for gdc in gateway.GatewayDeviceType:
            if gdc in gateway_selection:
                baud_rate = gateway.BAUD_RATE_DEVICE_TYPE_MAPPING[gdc]
                break
        
        # check ip address for esp3 over tcp
        for gdt_lan in [GatewayDeviceType.LAN.value, GatewayDeviceType.LAN_ESP2.value]:
            if gdt_lan in gateway_selection:
                try:
                    ip = ipaddress.ip_address(serial_path)
                    LOGGER.debug("Found valid IP Address %s.", serial_path)
                    return True
                except Exception:
                    LOGGER.debug("serial_path: %s is no valid IP Address", serial_path)
                    return False
            # check serial ports / usb
            else:
                path_is_valid = await self.hass.async_add_executor_job(
                    gateway.validate_path, serial_path, baud_rate
                )
                LOGGER.debug("serial_path: %s, validated with baud rate %d is %s", serial_path, baud_rate, path_is_valid)

        return path_is_valid

    def create_eltako_entry(self, user_input):
        """Create an entry for the provided configuration."""
        LOGGER.debug("Create Gateway Entry")
        return self.async_create_entry(title="Eltako", data=user_input)
