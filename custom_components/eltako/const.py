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

SIGNAL_RECEIVE_MESSAGE: Final = "receive_message"
SIGNAL_SEND_MESSAGE: Final = "send_message"
EVENT_BUTTON_PRESSED: Final = "button_pressed"
EVENT_CONTACT_CLOSED: Final = "contact_closed"

LOGGER: Final = logging.getLogger(DOMAIN)

CONF_EEP: Final = "eep"
CONF_SWITCH_BUTTON: Final = "switch-button"
CONF_SENDER: Final = "sender"
CONF_SENSOR: Final = "sensor"
CONF_GERNERAL_SETTINGS: Final = "general_settings"
CONF_SHOW_DEV_ID_IN_DEV_NAME: Final = "show_dev_id_in_dev_name"
CONF_ENABLE_TEACH_IN_BUTTONS: Final = "enable_teach_in_buttons"
CONF_FAST_STATUS_CHANGE: Final = "fast_status_change"
CONF_GATEWAY: Final = "gateway"
CONF_BASE_ID: Final = "base_id"
CONF_SERIAL_PATH: Final = "serial_path"
CONF_MAX_TARGET_TEMPERATURE: Final = "max_target_temperature"
CONF_MIN_TARGET_TEMPERATURE: Final = "min_target_temperature"
CONF_ROOM_THERMOSTAT: Final = "thermostat"
CONF_COOLING_MODE: Final = "cooling_mode"

CONF_ID_REGEX: Final = "^([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})( (left|right))?$"
CONF_METER_TARIFFS: Final = "meter_tariffs"
CONF_TIME_CLOSES: Final = "time_closes"
CONF_TIME_OPENS: Final = "time_opens"
CONF_INVERT_SIGNAL: Final = "invert_signal"
CONF_VOC_TYPE_INDEXES: Final = "voc_type_indexes"

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

