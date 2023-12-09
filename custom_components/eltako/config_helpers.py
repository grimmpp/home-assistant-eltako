from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICE, CONF_DEVICES, CONF_NAME

from eltakobus.util import AddressExpression, b2a

from .const import *

# default settings from configuration
DEFAULT_GENERAL_SETTINGS = {
    CONF_FAST_STATUS_CHANGE: False,
    CONF_SHOW_DEV_ID_IN_DEV_NAME: False,
    CONF_ENABLE_TEACH_IN_BUTTONS: False
}

def get_general_settings_from_configuration(hass: HomeAssistant) -> dict:
    settings = DEFAULT_GENERAL_SETTINGS
    if hass and CONF_GERNERAL_SETTINGS in hass.data[DATA_ELTAKO][ELTAKO_CONFIG]:
        settings = hass.data[DATA_ELTAKO][ELTAKO_CONFIG][CONF_GERNERAL_SETTINGS]
    
    # LOGGER.debug(f"General Settings: {settings}")

    return settings


async def async_get_gateway_config(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    # LOGGER.debug(f"config: {config}")
    if CONF_GATEWAY in config:
        if isinstance(config[CONF_GATEWAY], dict) and CONF_DEVICE in config[CONF_GATEWAY]:
            return config[CONF_GATEWAY]
        elif len(config[CONF_GATEWAY]) > 0 and CONF_DEVICE in config[CONF_GATEWAY][0]:
            return config[CONF_GATEWAY][0]
    return None

async def async_get_gateway_config_serial_port(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    gateway_config = await async_get_gateway_config(hass, CONFIG_SCHEMA, get_integration_config)
    if gateway_config is not None and CONF_SERIAL_PATH in gateway_config:
        return gateway_config[CONF_SERIAL_PATH]
    return None

async def async_get_home_assistant_config(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    _conf = await get_integration_config(hass, DOMAIN)
    if not _conf or DOMAIN not in _conf:
        LOGGER.warning("No `eltako:` key found in configuration.yaml.")
        # generate defaults
        return CONFIG_SCHEMA({DOMAIN: {}})[DOMAIN]
    else:
        return _conf[DOMAIN]
    
def get_device_config(config: dict, base_id: AddressExpression) -> dict:
    gateways = config[CONF_GATEWAY]
    for g in gateways:
        if g[CONF_BASE_ID].upper() == b2a(base_id[0],'-').upper():
            return g[CONF_DEVICES]
    return None

async def async_get_list_of_gateways(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    return get_list_of_gateways_by_config(config)

def get_list_of_gateways_by_config(config: dict) -> dict:
    """Compiles a list of all gateways in config."""
    result = {}
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            g_name = g[CONF_NAME]
            g_device = g[CONF_DEVICE]
            g_base_id = g[CONF_BASE_ID]
            display_name = f"{g_name} - {g_device} ({g_base_id.upper()})"
            result[g_base_id.upper()] = display_name
    return result

def compare_enocean_ids(id1: bytes, id2: bytes, len=3) -> bool:
    """Compares two bytes arrays. len specifies the length to be checked."""
    for i in range(0,len):
        if id1[i] != id2[i]:
            return False
    return True

def get_device_name(dev_name: str, dev_id: AddressExpression, general_config: dict) -> str:
    if general_config[CONF_SHOW_DEV_ID_IN_DEV_NAME]:
        return f"{dev_name} ({b2a(dev_id[0],'-').upper()})"
    else:
        return dev_name
    
def get_bus_event_type(gateway_id :AddressExpression, function_id: str, source_id: AddressExpression = None, data: str=None) -> str:
    event_id = f"{DOMAIN}.gw_{b2a(gateway_id[0],'-').upper()}.{function_id}"
    
    # add source id e.g. switch id
    if source_id is not None:
        event_id += f".sid_{b2a(source_id[0],'-').upper()}"
    
    # add data for better handling in automations
    if data is not None:
        event_id += f".d_{data}"

    return event_id

def convert_button_pos_from_hex_to_str(pos: int) -> str:
    if pos == 0x10:
        return "LB"
    if pos == 0x30:
        return "LT"
    if pos == 0x70:
        return "RT"
    if pos == 0x50:
        return "RB"
    return None