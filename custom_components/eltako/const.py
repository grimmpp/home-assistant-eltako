"""Constants for the Eltako integration."""
from enum import Enum
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

ERROR_INVALID_GATEWAY_PATH: Final = "Invalid gateway path"
ERROR_NO_SERIAL_PATH_AVAILABLE: Final = "No serial path available. Try to reconnect your usb plug."
ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE: Final = "No gateway configuration available. Enter gateway into '/homeassistant/configuration.yaml'."

SIGNAL_RECEIVE_MESSAGE: Final = "receive_message"
SIGNAL_SEND_MESSAGE: Final = "send_message"
EVENT_BUTTON_PRESSED: Final = "btn_pressed"
EVENT_CONTACT_CLOSED: Final = "contact_closed"

LOGGER: Final = logging.getLogger(DOMAIN)

CONF_UNKNOWN: Final = "unknown"
CONF_REGISTERED_IN: Final = "registered_in"
CONF_COMMENT: Final = "comment"
CONF_EEP: Final = "eep"
CONF_SWITCH_BUTTON: Final = "switch_button"
CONF_SENDER: Final = "sender"
CONF_SENSOR: Final = "sensor"
CONF_GERNERAL_SETTINGS: Final = "general_settings"
CONF_SHOW_DEV_ID_IN_DEV_NAME: Final = "show_dev_id_in_dev_name"
CONF_ENABLE_TEACH_IN_BUTTONS: Final = "enable_teach_in_buttons"
CONF_FAST_STATUS_CHANGE: Final = "fast_status_change"
GATEWAY_DEFAULT_NAME: Final = "EnOcean Gateway"
OLD_GATEWAY_DEFAULT_NAME: Final = "EnOcean ESP2 Gateway"
CONF_GATEWAY: Final = "gateway"
CONF_GATEWAY_ID: Final = "gateway_id"
CONF_GATEWAY_DESCRIPTION: Final = "gateway_description"
CONF_BASE_ID: Final = "base_id"
CONF_DEVICE_TYPE: Final = "device_type"
CONF_SERIAL_PATH: Final = "serial_path"
CONF_GATEWAY_ADDRESS: Final = "address"
CONF_GATEWAY_MESSAGE_DELAY: Final = "message_delay"

CONF_GATEWAY_AUTO_RECONNECT: Final = "auto_reconnect"
CONF_GATEWAY_PORT: Final = "port"
CONF_CUSTOM_SERIAL_PATH: Final = "custom_serial_path"
CONF_MAX_TARGET_TEMPERATURE: Final = "max_target_temperature"
CONF_MIN_TARGET_TEMPERATURE: Final = "min_target_temperature"
CONF_ROOM_THERMOSTAT: Final = "thermostat"
CONF_COOLING_MODE: Final = "cooling_mode"

CONF_VIRTUAL_NETWORK_GATEWAY: Final = "Virtual ESP2 Reverse Network Bridge"

CONF_GATEWAY_DESCRIPTION_PATTERN: Final = ""

CONF_ID_REGEX: Final = "^([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})( (left|right))?$"
CONF_METER_TARIFFS: Final = "meter_tariffs"
CONF_TIME_CLOSES: Final = "time_closes"
CONF_TIME_OPENS: Final = "time_opens"
CONF_TIME_TILTS: Final = "time_tilts"
CONF_INVERT_SIGNAL: Final = "invert_signal"
CONF_VOC_TYPE_INDEXES: Final = "voc_type_indexes"

class LANGUAGE_ABBREVIATION(StrEnum):
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

class GatewayDeviceType(str, Enum):
    GatewayEltakoFAM14 = 'fam14'
    GatewayEltakoFGW14USB = 'fgw14usb'
    GatewayEltakoFAMUSB = 'fam-usb'     # ESP2 transceiver: https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/
    EltakoFTD14 = 'ftd14'
    EnOceanUSB300 = 'enocean-usb300'
    EltakoFAM14 = 'fam14'
    EltakoFGW14USB = 'fgw14usb'
    EltakoFAMUSB = 'fam-usb'
    USB300 = 'enocean-usb300'
    ESP3 = 'esp3-gateway'
    LAN = 'mgw-lan'
    LAN_ESP2 = "lan-gw-esp2"
    VirtualNetworkAdapter = 'esp2-netowrk-reverse-bridge'   # subtype of LAN_ESP2

    @classmethod
    def indexOf(cls, value):
        return list(cls).index(value)
    
    @classmethod
    def get_by_index(cls, index):
        return list(cls)[index]

    @classmethod
    def find(cls, value):
        for t in GatewayDeviceType:
            if t.value.lower() == value.lower():
                return t
        return None

    @classmethod
    def is_transceiver(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAMUSB, GatewayDeviceType.EnOceanUSB300, GatewayDeviceType.USB300, GatewayDeviceType.ESP3]

    @classmethod
    def is_bus_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB,
                            GatewayDeviceType.EltakoFAM14, GatewayDeviceType.EltakoFAMUSB, GatewayDeviceType.EltakoFGW14USB]
    
    @classmethod
    def is_esp2_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB, GatewayDeviceType.GatewayEltakoFAMUSB, 
                            GatewayDeviceType.EltakoFAM14, GatewayDeviceType.EltakoFAMUSB, GatewayDeviceType.EltakoFGW14USB]
    
    @classmethod
    def is_lan_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.LAN, GatewayDeviceType.LAN_ESP2]

BAUD_RATE_DEVICE_TYPE_MAPPING: dict = {
    GatewayDeviceType.GatewayEltakoFAM14: 57600,
    GatewayDeviceType.GatewayEltakoFGW14USB: 57600,
    GatewayDeviceType.GatewayEltakoFAMUSB: 9600,
    GatewayDeviceType.EnOceanUSB300: 57600,
    GatewayDeviceType.EltakoFAM14: 57600,
    GatewayDeviceType.EltakoFGW14USB: 57600,
    GatewayDeviceType.EltakoFAMUSB: 9600,
    GatewayDeviceType.USB300: 57600,
    GatewayDeviceType.ESP3: 57600,
    GatewayDeviceType.LAN: -1,
    GatewayDeviceType.LAN_ESP2: -2,
    GatewayDeviceType.VirtualNetworkAdapter: -2
}