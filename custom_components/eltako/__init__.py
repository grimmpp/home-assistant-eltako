"""Support for Eltako devices."""
import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_DEVICE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.reload import async_integration_yaml_config

from .const import DATA_ELTAKO, DOMAIN, ELTAKO_GATEWAY, ELTAKO_CONFIG, LOGGER, PLATFORMS
from .gateway import EltakoGateway
from .schema import (
    BinarySensorSchema,
    LightSchema,
    SwitchSchema,
    SensorSchema,
    CoverSchema,
    HeatingAndCoolingSchema,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    **BinarySensorSchema.platform_node(),
                    **LightSchema.platform_node(),
                    **SwitchSchema.platform_node(),
                    **SensorSchema.platform_node(),
                    **SensorSchema.platform_node(),
                    **CoverSchema.platform_node(),
                    **HeatingAndCoolingSchema.platform_node(),
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Eltako gateway for the given entry."""
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    
    # Read the config
    _conf = await async_integration_yaml_config(hass, DOMAIN)
    if not _conf or DOMAIN not in _conf:
        LOGGER.warning("No `eltako:` key found in configuration.yaml.")
        # generate defaults
        config = CONFIG_SCHEMA({DOMAIN: {}})[DOMAIN]
    else:
        config = _conf[DOMAIN]

    eltako_data[ELTAKO_CONFIG] = config
    
    # Initialise the gateway
    serial_path = config_entry.data[CONF_DEVICE]
    usb_gateway = EltakoGateway(hass, serial_path, config_entry)
    await usb_gateway.async_setup()
    eltako_data[ELTAKO_GATEWAY] = usb_gateway
    
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
