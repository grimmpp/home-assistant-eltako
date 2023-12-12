"""Support for Eltako devices."""
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_NAME, CONF_PATH
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from .const import *
from .schema import CONFIG_SCHEMA
from . import config_helpers
from .gateway import *

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component."""
    return True

def print_config_entry(config_entry: ConfigEntry) -> None:
    LOGGER.debug("ConfigEntry")
    LOGGER.debug("- tilte: %s", config_entry.title)
    LOGGER.debug("- domain: %s", config_entry.domain)
    LOGGER.debug("- unique_id: %s", config_entry.unique_id)
    LOGGER.debug("- version: %s", config_entry.version)
    LOGGER.debug("- entry_id: %s", config_entry.entry_id)
    LOGGER.debug("- state: %s", config_entry.state)
    for k in config_entry.data.keys():
        LOGGER.debug("- data %s - %s", k, config_entry.data.get(k, ''))

def print_dict(_dict: dict):
    LOGGER.debug("Print dict:")
    for k in _dict.keys():
        LOGGER.debug("- %s: %s", k, _dict[k])

LOG_PREFIX = "Eltako Integration Setup"

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    print_config_entry(config_entry)

    # Check domain
    if config_entry.domain != DOMAIN:
        raise Exception(f"[{LOG_PREFIX}] Ooops, received configuration entry of wrong domain '%s' (expected: '')!", config_entry.domain, DOMAIN)

    
    # Read the config
    config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)
    # set config for global access
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    eltako_data[ELTAKO_CONFIG] = config
    # print whole eltako configuration
    LOGGER.debug(f"config: {config}\n")

    general_settings = config_helpers.get_general_settings_from_configuration(hass)

    # Initialise the gateway
    # get base_id from user input
    gateway_description = config_entry.data[CONF_DEVICE]    # from user input
    gateway_base_id = config_helpers.get_id_from_name(gateway_description)
    
    # get home assistant configuration section matching base_id
    gateway_config = await config_helpers.async_find_gateway_config_by_base_id(gateway_base_id, hass, CONFIG_SCHEMA)
    if not gateway_config:
        raise Exception(f"[{LOG_PREFIX}] No gateway configuration found.")
    
    gateway_device_type = gateway_config[CONF_DEVICE]    # from configuration
    # gateway_base_id = AddressExpression.parse(gateway_config[CONF_BASE_ID])   # not needed
    gateway_name = gateway_config.get(CONF_NAME, None)  # from configuration
    gateway_serial_path = config_entry.data[CONF_SERIAL_PATH]

    # only transceiver can send teach-in telegrams
    general_settings[CONF_ENABLE_TEACH_IN_BUTTONS] = GatewayDeviceType.is_transceiver(gateway_device_type)
    

    LOGGER.debug(f"[{LOG_PREFIX}] Initializes Gateway Device '{gateway_description}'")
    if GatewayDeviceType.is_esp2_gateway(gateway_device_type):
        baud_rate= BAUD_RATE_DEVICE_TYPE_MAPPING[GatewayDeviceType.GatewayEltakoFAM14]
        usb_gateway = ESP2Gateway(general_settings, hass, gateway_device_type, gateway_serial_path, baud_rate, gateway_base_id, gateway_name, config_entry)
    else:
        baud_rate= BAUD_RATE_DEVICE_TYPE_MAPPING[GatewayDeviceType.EnOceanUSB300]
        raise NotImplemented(f"[{LOG_PREFIX}] Gateway {gateway_device_type} not yet implemented and supported!")
    
    if usb_gateway is None:
        LOGGER.error(f"[{LOG_PREFIX}] USB device {gateway_device_type} is not supported.")
        return False
    
    await usb_gateway.async_setup()
    if ELTAKO_GATEWAY not in hass.data[DATA_ELTAKO]:
        hass.data[DATA_ELTAKO] = {}
    hass.data[DATA_ELTAKO][usb_gateway.dev_name] = usb_gateway
    
    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )

    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""
    LOGGER.debug("async_unload_entry")
    print_config_entry(config_entry)

    LOGGER.debug("Existing entities")
    entity_reg = er.async_get(hass)
    for e in entity_reg.entities.values():
        LOGGER.debug("- name: %s, dev_id: %d, e_id: %s", e.name, e.device_id, e.entity_id)

    gateway_name = config_entry.data[CONF_DEVICE]
    eltako_gateway = hass.data[DATA_ELTAKO][gateway_name]
    eltako_gateway.unload()
    hass.data[DATA_ELTAKO].remove(gateway_name)
    # if len(hass.data[DATA_ELTAKO]) == 0:
    #     hass.data.remove(DATA_ELTAKO)

    return True
