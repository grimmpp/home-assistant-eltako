from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICE
from homeassistant.helpers.reload import async_integration_yaml_config

from .const import *
from .schema import *

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            vol.Schema(
                {
                    **GeneralSettings.platform_node(),
                    **GatewaySchema.platform_node(),
                    **BinarySensorSchema.platform_node(),
                    **LightSchema.platform_node(),
                    **SwitchSchema.platform_node(),
                    **SensorSchema.platform_node(),
                    **SensorSchema.platform_node(),
                    **CoverSchema.platform_node(),
                    **ClimateSchema.platform_node(),
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# default settings from configuration
DEFAULT_GENERAL_SETTINGS = {
    CONF_FAST_STATUS_CHANGE: False
}

def get_general_settings_from_configuration(hass: HomeAssistant) -> dict:
    settings = DEFAULT_GENERAL_SETTINGS
    if hass and CONF_GERNERAL_SETTINGS in hass.data[DATA_ELTAKO][ELTAKO_CONFIG]:
        settings = hass.data[DATA_ELTAKO][ELTAKO_CONFIG][CONF_GERNERAL_SETTINGS][0]
    
    # LOGGER.debug(f"General Settings: {settings}")

    return settings


async def async_get_gateway_config(hass: HomeAssistant) -> dict:
    config = await async_get_home_assistant_config(hass)
    # LOGGER.debug(f"config: {config}")
    if CONF_GATEWAY in config:
        if isinstance(config[CONF_GATEWAY], dict) and CONF_DEVICE in config[CONF_GATEWAY]:
            return config[CONF_GATEWAY]
        elif len(config[CONF_GATEWAY]) > 0 and CONF_DEVICE in config[CONF_GATEWAY][0]:
            return config[CONF_GATEWAY][0]
    return None

async def async_get_gateway_config_serial_port(hass: HomeAssistant) -> dict:
    gateway_config = await async_get_gateway_config(hass)
    if gateway_config is not None:
        return gateway_config[CONF_SERIAL_PATH]
    return None

async def async_get_home_assistant_config(hass: HomeAssistant) -> dict:
    _conf = await async_integration_yaml_config(hass, DOMAIN)
    if not _conf or DOMAIN not in _conf:
        LOGGER.warning("No `eltako:` key found in configuration.yaml.")
        # generate defaults
        return CONFIG_SCHEMA({DOMAIN: {}})[DOMAIN]
    else:
        return _conf[DOMAIN]