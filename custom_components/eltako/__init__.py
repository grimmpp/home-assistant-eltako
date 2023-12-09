"""Support for Eltako devices."""
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from .const import *
from .schema import CONFIG_SCHEMA
from .config_helpers import *
from .gateway import *

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    
    # Read the config
    config = await async_get_home_assistant_config(hass, CONFIG_SCHEMA)
    eltako_data[ELTAKO_CONFIG] = config
    # print whole eltako configuration
    LOGGER.debug(f"config: {config}\n")

    general_settings = get_general_settings_from_configuration(hass)

    # Initialise the gateway
    gateway_config = await async_get_gateway_config(hass, CONFIG_SCHEMA)
    if not gateway_config:
        raise Exception("[Eltako Integration Setup] No gateway configuration found.")
    
    gateway_device = gateway_config[CONF_DEVICE]
    gateway_base_id = AddressExpression.parse(gateway_config[CONF_BASE_ID])
    if CONF_NAME in gateway_config:
        gateway_name = gateway_config[CONF_NAME]
    else:
        gateway_name = None

    general_settings[CONF_ENABLE_TEACH_IN_BUTTONS] = gateway_device in [GatewayDeviceTypes.GatewayEltakoFAMUSB, GatewayDeviceTypes.EnOceanUSB300]
    # if len(config[CONF_GATEWAY]) > 1:
    #     LOGGER.warning("[Eltako Setup] More than 1 gateway is defined in the Home Assistant Configuration for Eltako Integration/Domain. Only the first entry is considered and the others will be ignored!")

    serial_path = config_entry.data[CONF_DEVICE]

    LOGGER.debug(f"[Eltako Setup] Initializes USB device {gateway_device}")
    match gateway_device:
        case GatewayDeviceTypes.GatewayEltakoFAM14:
            baud_rate=57600
            usb_gateway = EltakoGatewayFam14(general_settings, hass, serial_path, baud_rate, gateway_base_id, gateway_name, config_entry)
        case GatewayDeviceTypes.GatewayEltakoFGW14USB:
            baud_rate=57600
            usb_gateway = EltakoGatewayFgw14Usb(general_settings, hass, serial_path, baud_rate, gateway_base_id, gateway_name, config_entry)
        case GatewayDeviceTypes.GatewayEltakoFAMUSB:
            baud_rate=9600
            usb_gateway = EltakoGatewayFamUsb(general_settings, hass, serial_path, baud_rate, gateway_base_id, gateway_name, config_entry)
        case GatewayDeviceTypes.EnOceanUSB300:
            raise NotImplemented("EnOcean USB300 based on ESP3 protocol not yet supported!")
            usb_gateway = EnoceanUSB300Gateway(hass, serial_path, baud_rate, config_entry)
    
    if usb_gateway is None:
        LOGGER.error(f"[Eltako Setup] USB device {gateway_device} is not supported.")
        return False
    
    await usb_gateway.async_setup()
    eltako_data[ELTAKO_GATEWAY] = usb_gateway
    
    devices_config = get_config_seciont_devices_for_gateway_base_id(config_entry, usb_gateway.base_id)

    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(devices_config, platform)
        )
    
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""
    eltako_gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]
    eltako_gateway.unload()
    hass.data.pop(DATA_ELTAKO)

    return True
