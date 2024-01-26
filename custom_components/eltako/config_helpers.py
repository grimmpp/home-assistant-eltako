from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.const import CONF_DEVICES, CONF_NAME, CONF_ID

from eltakobus.util import AddressExpression, b2a
from eltakobus.eep import EEP

from .const import *

# default settings from configuration
DEFAULT_GENERAL_SETTINGS = {
    CONF_FAST_STATUS_CHANGE: False,
    CONF_SHOW_DEV_ID_IN_DEV_NAME: False,
    CONF_ENABLE_TEACH_IN_BUTTONS: False
}

class DeviceConf(dict):
    """Object representation of config."""
    def __init__(self, config: ConfigType, extra_keys:[str]=[]):
        # merge everything into dict
        self.update(config)
        
        # additionally add attributes
        self.id = config.get(CONF_ID, None)
        if self.id is not None and isinstance(self.id, str):
            self.id = AddressExpression.parse(self.id)
        self[CONF_ID] = self.id

        self.eep = config.get(CONF_EEP, None)
        if self.eep is not None:
            self.eep = EEP.find(self.eep)
        self[CONF_EEP] = self.eep

        self.name = config.get(CONF_NAME, None)
        self[CONF_NAME] = self.name

        self.base_id = config.get(CONF_BASE_ID, None)
        if self.base_id is not None:
            self.base_id = AddressExpression.parse(self.base_id)
        self[CONF_BASE_ID] = self.base_id

        self.device_type = config.get(CONF_DEVICE_TYPE, None)
        self[CONF_DEVICE_TYPE] = self.device_type

        self.gateway_id = config.get(CONF_GATEWAY_ID, None)
        self[CONF_GATEWAY_ID] = self.gateway_id

        # add extra fields
        for ek in extra_keys:
            if ek in config:
                setattr(self, ek, config.get(ek))

    def get(self, key: str):
        return super().get(key, None)

def get_device_conf(config: ConfigType, key: str, extra_keys:[str]=[]) -> DeviceConf:
    if config is not None:
        if key in config.keys():
            return DeviceConf(config.get(key))
    return None

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
        if isinstance(config[CONF_GATEWAY], dict) and CONF_DEVICE_TYPE in config[CONF_GATEWAY]:
            return config[CONF_GATEWAY]
        elif len(config[CONF_GATEWAY]) > 0 and CONF_DEVICE_TYPE in config[CONF_GATEWAY][0]:
            return config[CONF_GATEWAY][0]
    return None

async def async_find_gateway_config_by_base_id(base_id: AddressExpression, hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_BASE_ID].upper() == format_address(base_id[0]):
                return g
    return None

async def async_find_gateway_config_by_id(id: int, hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    return find_gateway_config_by_id(config, id)

def find_gateway_config_by_id(config: dict, id: int) -> dict:
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_ID] == id:
                return g
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
    
def get_device_config(config: dict, id: int) -> dict:
    gateways = config[CONF_GATEWAY]
    for g in gateways:
        if g[CONF_ID] == id:
            return g[CONF_DEVICES]
    return None

async def async_get_list_of_gateway_descriptions(hass: HomeAssistant, CONFIG_SCHEMA: dict, get_integration_config=async_integration_yaml_config, filter_out: [str]=[]) -> dict:
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA, get_integration_config)
    return get_list_of_gateway_descriptions(config, filter_out)

def get_list_of_gateway_descriptions(config: dict, filter_out: [str]=[]) -> dict:
    """Compiles a list of all gateways in config."""
    result = {}
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            g_id = g[CONF_ID]
            g_name = g.get(CONF_NAME, None)
            g_device_type = g[CONF_DEVICE_TYPE]
            g_base_id = g.get(CONF_BASE_ID, None)
            if g_base_id and g_base_id not in filter_out:
                result[g_id] = get_gateway_name(g_name, g_device_type, g_id, AddressExpression.parse(g_base_id))
    return result

def config_check_gateway(config: dict) -> bool:
    #ids in gateway config are unique
    g_ids = []
    if CONF_GATEWAY in config:
        for g in config[CONF_GATEWAY]:
            if g[CONF_ID] in g_ids:
                return False
            g_ids.append(g[CONF_ID])
    
    if len(g_ids) == 0:
        return False

    return True

def compare_enocean_ids(id1: bytes, id2: bytes, len=3) -> bool:
    """Compares two bytes arrays. len specifies the length to be checked."""
    for i in range(0,len):
        if id1[i] != id2[i]:
            return False
    return True

def get_gateway_name(dev_name:str, dev_type:str, dev_id: int, base_id:AddressExpression) -> str:
    if not dev_name or len(dev_name) == 0:
        dev_name = GATEWAY_DEFAULT_NAME
    return f"{dev_name} - {dev_type} (Id: {dev_id}, BaseId: {format_address(base_id)})"

def format_address(address: AddressExpression, separator:str='-') -> str:
    return b2a(address[0], '-').upper()

def get_device_name(dev_name: str, dev_id: AddressExpression, general_config: dict) -> str:
    if general_config[CONF_SHOW_DEV_ID_IN_DEV_NAME]:
        return f"{dev_name} ({format_address(dev_id)})"
    else:
        return dev_name
    
def get_id_from_name(dev_name: str) -> AddressExpression:
    return int(dev_name.split('(Id: ')[1].split(',')[0])
    
def get_bus_event_type(gateway_id: int, function_id: str, source_id: AddressExpression = None, data: str=None) -> str:
    event_id = f"{DOMAIN}.gw_{gateway_id}.{function_id}"
    
    # add source id e.g. switch id
    if source_id is not None:
        event_id += f".sid_{format_address(source_id)}"
    
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

def convert_button_abbreviation(buttons:[str]) -> [str]:
    result = []
    for b in buttons:
        if b.lower() == "LB":
            result.append("Left Bottom")
        elif b.lower() == "LT":
            result.append("Left Top")
        elif b.lower() == "RB":
            result.append("Right Bottom")
        elif b.lower() == "RT":
            result.append("Right Top")
    return result

def button_abbreviation_to_str(buttons:[str]) -> [str]:
    return ', '.join(convert_button_abbreviation(buttons))