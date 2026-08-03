"""Constants for the Eltako integration."""
from enum import Enum
from strenum import StrEnum
import logging

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "eltako"
DATA_ELTAKO: Final = "eltako"
DATA_ENTITIES: Final = "entities"
DATA_TELEGRAM_LOGGER: Final = "telegram_logger"
DATA_DEVICE_ACTIVITY: Final = "device_activity"
DATA_SETTINGS_OVERRIDES: Final = "settings_overrides"
DATA_SETTINGS_STORE: Final = "settings_store"
# NOTE: keys must not start with "gateway" - the gateway objects themselves are stored under
# "gateway_<id>" and are collected by prefix in several places.
DATA_UI_GATEWAYS: Final = "ui_gateway_definitions"
DATA_GATEWAY_STORE: Final = "ui_gateway_store"
DATA_BUS_MEMBERS: Final = "bus_members"
DATA_PORT_FINGERPRINTS: Final = "port_fingerprints"
DATA_PORT_FINGERPRINT_STORE: Final = "port_fingerprint_store"
ELTAKO_GATEWAY: Final = "gateway"
ELTAKO_CONFIG: Final = "config"
MANUFACTURER: Final = "Eltako"

ERROR_INVALID_GATEWAY_PATH: Final = "Invalid gateway path"
ERROR_NO_SERIAL_PATH_AVAILABLE: Final = "No serial path available. Try to reconnect your usb plug."
ERROR_NO_GATEWAY_CONFIGURATION_AVAILABLE: Final = "No gateway configuration available. Enter gateway into '/homeassistant/configuration.yaml'."

SIGNAL_RECEIVE_MESSAGE: Final = "receive_message"
SIGNAL_SEND_MESSAGE: Final = "send_message"
SIGNAL_SEND_MESSAGE_SERVICE: Final = "send_message_service"
EVENT_BUTTON_PRESSED: Final = "btn_pressed"
EVENT_CONTACT_CLOSED: Final = "contact_closed"
ELTAKO_GLOBAL_EVENT_BUS_ID: Final = "eltako_global_event_bus"
EVENT_CLIMATE_PRIORITY_SELECTED: Final = "climate_priority_selected"

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
CONF_ENABLE_FRONTEND: Final = "enable_frontend"
CONF_ENABLE_TEACH_IN_BUTTONS: Final = "enable_teach_in_buttons"

### Deprecated general settings. They are still accepted so that existing configurations
### keep working, but they are ignored. (See config_helpers.check_for_deprecated_settings)
CONF_DEPRECATED_ENABLE_FRONTEND: Final = "enable-frontend"      # replaced by CONF_ENABLE_FRONTEND
CONF_DEPRECATED_FRONTEND_DEV_URL: Final = "frontend-dev-url"    # frontend is part of the integration now
CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI: Final = "enable_telegram_web_ui"    # part of the frontend now

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
CONF_ROOM_SENSOR: Final = "room_sensor"
CONF_OFF_TEMPERATURE: Final = "off_temperature"

CONF_VIRTUAL_NETWORK_GATEWAY: Final = "Virtual ESP2 Reverse Network Bridge"

CONF_GATEWAY_DESCRIPTION_PATTERN: Final = ""

CONF_ID_REGEX: Final = "^([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})-([0-9a-fA-F]{2})( (left|right))?$"
CONF_METER_TARIFFS: Final = "meter_tariffs"
CONF_TIME_CLOSES: Final = "time_closes"
CONF_TIME_OPENS: Final = "time_opens"
CONF_TIME_TILTS: Final = "time_tilts"
CONF_INVERT_SIGNAL: Final = "invert_signal"
CONF_VOC_TYPE_INDEXES: Final = "voc_type_indexes"
CONF_AREA: Final = "area"

### EnOcean telegram logging and analysis (section 'general_settings')
CONF_LOG_ENOCEAN_TELEGRAMS: Final = "log_enocean_telegrams"
CONF_TELEGRAM_LOG_FILENAME: Final = "telegram_log_filename"
CONF_TELEGRAM_LOG_FORMAT: Final = "telegram_log_format"
CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB: Final = "telegram_log_max_file_size_mb"
CONF_TELEGRAM_LOG_BACKUP_COUNT: Final = "telegram_log_backup_count"
CONF_TELEGRAM_LOG_INCLUDE_POLLING: Final = "telegram_log_include_polling"
CONF_TELEGRAM_LOG_DECODE_EEP: Final = "telegram_log_decode_eep"
CONF_TELEGRAM_LOG_BUFFER_SIZE: Final = "telegram_log_buffer_size"

### Log levels per telegram category. They control what ends up in the Home Assistant log
### (logger 'eltako.telegrams'), independent of the telegram log file.
CONF_LOG_LEVEL_INCOMING: Final = "log_level_incoming"
CONF_LOG_LEVEL_OUTGOING: Final = "log_level_outgoing"
CONF_LOG_LEVEL_UNKNOWN_DEVICES: Final = "log_level_unknown_devices"
CONF_LOG_LEVEL_BUS_MESSAGES: Final = "log_level_bus_messages"
CONF_LOG_LEVEL_POLLING: Final = "log_level_polling"
CONF_LOG_LEVEL_DECODE_ERRORS: Final = "log_level_decode_errors"

TELEGRAM_LOGGER_NAME: Final = f"{DOMAIN}.telegrams"


class TelegramLogLevel(StrEnum):
    """Log level of one telegram category. 'off' means: do not log this category."""
    OFF = 'off'
    DEBUG = 'debug'
    INFO = 'info'
    WARNING = 'warning'


### Groups of the general settings (used to structure the web ui)
SETTING_GROUPS: Final = [
    ('general', "General", "Behaviour of the integration and its entities."),
    ('web_ui', "Web UI", "This user interface."),
    ('telegram_log', "Telegram recording", "Live view, statistics and the telegram log file."),
    ('log_levels', "Log levels of telegrams", "What is written into the Home Assistant log "
     "(logger 'eltako.telegrams'). Use this to follow specific telegrams without flooding the log."),
]


class TelegramLogFormat(StrEnum):
    """Serialization format of the telegram log file."""
    JSONL = 'jsonl'     # one json object per line, best suited for analysis
    CSV = 'csv'         # spreadsheet friendly


class TelegramDirection(StrEnum):
    """Direction of a recorded telegram seen from Home Assistant."""
    INCOMING = 'incoming'
    OUTGOING = 'outgoing'


### Web UI (panel) of the integration. The frontend is part of this integration
### (custom_components/eltako/frontend) and contains all sub pages (overview, telegram
### logging, device statistics, about, ...).
PANEL_URL_PATH: Final = "eltako"                    # sidebar/url path: /eltako
PANEL_TITLE: Final = "Eltako"
PANEL_ICON: Final = "mdi:access-point-network"   # radio/telegrams fit EnOcean better than a bus
PANEL_WEBCOMPONENT: Final = "eltako-panel"
PANEL_STATIC_URL: Final = "/eltako_frontend"        # url the frontend folder is served under
PANEL_JS_FILE: Final = "eltako-panel.js"            # entry point of the frontend

### Devices which are created through the web ui (stored in the options of the config entry)
CONF_UI_DEVICES: Final = "ui_devices"

### Websocket commands
WS_INTEGRATION_INFO: Final = "eltako/integration_info"
WS_DEVICE_FORM: Final = "eltako/devices/form"
WS_DEVICE_LIST: Final = "eltako/devices/list"
WS_DEVICE_ADD: Final = "eltako/devices/add"
WS_DEVICE_UPDATE: Final = "eltako/devices/update"
WS_DEVICE_REMOVE: Final = "eltako/devices/remove"
WS_DEVICE_ACTIVITY: Final = "eltako/devices/activity"
WS_DEVICE_ACTIVITY_CLEAR: Final = "eltako/devices/activity_clear"
WS_SETTINGS_GET: Final = "eltako/settings/get"
WS_SETTINGS_SET: Final = "eltako/settings/set"
WS_SETTINGS_RESET: Final = "eltako/settings/reset"
WS_GATEWAY_SCAN: Final = "eltako/gateways/scan"
WS_GATEWAY_FORM: Final = "eltako/gateways/form"
WS_GATEWAY_ADD: Final = "eltako/gateways/add"
WS_GATEWAY_REMOVE: Final = "eltako/gateways/remove"
WS_BUS_MEMBERS: Final = "eltako/bus/members"
WS_BUS_READ_MEMORY: Final = "eltako/bus/read_memory"
WS_BUS_TEACH_IN_SENDERS: Final = "eltako/bus/teach_in_senders"
WS_SEND_TELEGRAM: Final = "eltako/send_telegram"
WS_SEND_TELEGRAM_FORM: Final = "eltako/send_telegram_form"

### source of a config flow which was started from the web ui
SOURCE_UI_GATEWAY: Final = "ui_gateway"
WS_TELEGRAM_LOG_INFO: Final = "eltako/telegram_log/info"
WS_TELEGRAM_LOG_STATISTICS: Final = "eltako/telegram_log/statistics"
WS_TELEGRAM_LOG_RECENT: Final = "eltako/telegram_log/recent"
WS_TELEGRAM_LOG_SUBSCRIBE: Final = "eltako/telegram_log/subscribe"
WS_TELEGRAM_LOG_CLEAR: Final = "eltako/telegram_log/clear"
WS_TELEGRAM_LOG_REFRESH_DEVICES: Final = "eltako/telegram_log/refresh_devices"

### Services of the telegram logger
SERVICE_CLEAR_TELEGRAM_LOG: Final = "clear_telegram_log"

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
    Platform.SELECT
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
    LAN = 'lan'
    MGW_LAN = 'mgw-lan'
    EUL_LAN = 'eul_lan'
    LAN_ESP2 = "lan-gw-esp2"
    VirtualNetworkAdapter = 'esp2-network-reverse-bridge'   # subtype of LAN_ESP2

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
        return dev_type in [GatewayDeviceType.GatewayEltakoFAMUSB, GatewayDeviceType.EnOceanUSB300, GatewayDeviceType.USB300, GatewayDeviceType.ESP3, GatewayDeviceType.LAN, 
                            GatewayDeviceType.LAN_ESP2, GatewayDeviceType.MGW_LAN, GatewayDeviceType.EUL_LAN]

    @classmethod
    def is_bus_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB,
                            GatewayDeviceType.EltakoFAM14, GatewayDeviceType.EltakoFAMUSB, GatewayDeviceType.EltakoFGW14USB]
    
    @classmethod
    def is_esp2_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB, GatewayDeviceType.GatewayEltakoFAMUSB, 
                            GatewayDeviceType.EltakoFAM14, GatewayDeviceType.EltakoFAMUSB, GatewayDeviceType.EltakoFGW14USB, GatewayDeviceType.LAN_ESP2, 
                            GatewayDeviceType.VirtualNetworkAdapter]
    
    @classmethod
    def is_lan_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.LAN, GatewayDeviceType.LAN_ESP2, GatewayDeviceType.MGW_LAN, GatewayDeviceType.EUL_LAN, GatewayDeviceType.VirtualNetworkAdapter]

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
    GatewayDeviceType.LAN_ESP2: -1,
    GatewayDeviceType.MGW_LAN: -1,
    GatewayDeviceType.EUL_LAN: -1,
    GatewayDeviceType.VirtualNetworkAdapter: -1,
}