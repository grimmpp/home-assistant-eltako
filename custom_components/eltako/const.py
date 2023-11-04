"""Constants for the Eltako integration."""
import logging

from homeassistant.const import Platform

DOMAIN = "eltako"
DATA_ELTAKO = "eltako"
ELTAKO_GATEWAY = "gateway"
ELTAKO_CONFIG = "config"
MANUFACTURER = "Eltako"

ERROR_INVALID_GATEWAY_PATH = "invalid_gateway_path"

SIGNAL_RECEIVE_MESSAGE = "eltako.receive_message"
SIGNAL_SEND_MESSAGE = "eltako.send_message"
EVENT_BUTTON_PRESSED = "eltako_button_pressed"

LOGGER = logging.getLogger("eltako")

CONF_EEP = "eep"
CONF_DATA = "data"
CONF_SENDER = "sender"
CONF_SENSOR = "sensor"
CONF_GATEWAY = "gateway"
CONF_SERIAL_PATH = "serial_path"
CONF_MAX_TARGET_TEMPERATURE = "max_target_temperature"
CONF_MIN_TARGET_TEMPERATURE = "min_target_temperature"
CONF_COOLING_MODE = "cooling_mode"

CONF_ID_REGEX = "^([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})( (left|right))?$"
CONF_METER_TARIFFS = "meter_tariffs"
CONF_TIME_CLOSES = "time_closes"
CONF_TIME_OPENS = "time_opens"
CONF_INVERT_SIGNAL = "invert-signal"

PLATFORMS = [
    Platform.LIGHT,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.COVER,
    Platform.CLIMATE,
]
