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

LOGGER = logging.getLogger("eltako")

CONF_EEP = "eep"
CONF_SENDER_ID = "sender_id"
CONF_ID_REGEX = "([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})"
CONF_METER_TARIFFS = "meter_tariffs"

PLATFORMS = [
    Platform.LIGHT,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]
