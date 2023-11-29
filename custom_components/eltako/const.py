"""Constants for the Eltako integration."""
from strenum import StrEnum
import logging

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "eltako"
DATA_ELTAKO: Final = "eltako"
DATA_ENTITIES: Final = "entities"
ELTAKO_GATEWAY: Final = "gateway"
ELTAKO_CONFIG: Final = "config"
MANUFACTURER: Final = "Eltako"

ERROR_INVALID_GATEWAY_PATH: Final = "invalid_gateway_path"

SIGNAL_RECEIVE_MESSAGE: Final = "eltako.receive_message"
SIGNAL_SEND_MESSAGE: Final = "eltako.send_message"
EVENT_BUTTON_PRESSED: Final = "eltako_button_pressed"
EVENT_CONTACT_CLOSED: Final = "eltako_contact_closed"

LOGGER: Final = logging.getLogger(DOMAIN)

CONF_EEP: Final = "eep"
CONF_SWITCH_BUTTON: Final = "switch-button"
CONF_SENDER: Final = "sender"
CONF_SENSOR: Final = "sensor"
CONF_GERNERAL_SETTINGS: Final = "general-settings"
CONF_FAST_STATUS_CHANGE: Final = "fast-status-change"
CONF_GATEWAY: Final = "gateway"
CONF_SERIAL_PATH: Final = "serial_path"
CONF_MAX_TARGET_TEMPERATURE: Final = "max_target_temperature"
CONF_MIN_TARGET_TEMPERATURE: Final = "min_target_temperature"
CONF_COOLING_MODE: Final = "cooling_mode"

CONF_ID_REGEX: Final = "^([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})( (left|right))?$"
CONF_METER_TARIFFS: Final = "meter_tariffs"
CONF_TIME_CLOSES: Final = "time_closes"
CONF_TIME_OPENS: Final = "time_opens"
CONF_INVERT_SIGNAL: Final = "invert-signal"
CONF_VOC_TYPE_INDEXES: Final = "voc-type-indexes"

class LANGUAGE_ABBREVIATIONS(StrEnum):
    LANG_ENGLISH = 'en'
    LANG_GERMAN = 'de'

PLATFORMS: Final = [
    Platform.LIGHT,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.COVER,
    Platform.CLIMATE,
    Platform.BUTTON,
]

