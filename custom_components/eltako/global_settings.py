from homeassistant.core import HomeAssistant

from .const import *

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
