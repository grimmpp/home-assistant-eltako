"""Support for Eltako devices."""
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.reload import async_integration_yaml_config, async_get_platform_without_config_entry
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from .const import *
from .configuration_helpers import *
from .gateway import EltakoGateway, GatewayDeviceTypes, EnoceanUSB300Gateway

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    
    # Read the config
    config = await async_get_home_assistant_config(hass)
    eltako_data[ELTAKO_CONFIG] = config
    # print whole eltako configuration
    LOGGER.debug(f"config: {config}\n")

    # Initialise the gateway
    gateway_config = await async_get_gateway_config(hass)
    if gateway_config:
        gateway_device = gateway_config[CONF_DEVICE]
        # if len(config[CONF_GATEWAY]) > 1:
        #     LOGGER.warning("[Eltako Setup] More than 1 gateway is defined in the Home Assistant Configuration for Eltako Integration/Domain. Only the first entry is considered and the others will be ignored!")
    else:
        gateway_device = GatewayDeviceTypes.GatewayEltakoFGW14USB # default device
        LOGGER.info("[Eltako Setup] Eltako FGW14USB was set as default device.")

    serial_path = config_entry.data[CONF_DEVICE]

    match gateway_device:
        case GatewayDeviceTypes.GatewayEltakoFAM14 | GatewayDeviceTypes.GatewayEltakoFGW14USB:
            LOGGER.debug(f"[Eltako Setup] Initializes USB device {gateway_device}")
            usb_gateway = EltakoGateway(hass, serial_path, config_entry)
        case GatewayDeviceTypes.EnOceanUSB300:
            usb_gateway = EnoceanUSB300Gateway(hass, serial_path, config_entry)
    
    if usb_gateway is None:
        LOGGER.error(f"[Eltako Setup] USB device {gateway_device} is not supported.")
        return False
    
    await usb_gateway.async_setup()
    eltako_data[ELTAKO_GATEWAY] = usb_gateway
    
    hass.data[DATA_ELTAKO][DATA_ENTITIES] = {}
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(config_entry, platform)
        )
    
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload Eltako config entry."""
    eltako_gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]
    eltako_gateway.unload()
    hass.data.pop(DATA_ELTAKO)

    return True
