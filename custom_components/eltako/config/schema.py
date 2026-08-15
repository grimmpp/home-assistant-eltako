"""Voluptuous schemas for the Eltako integration."""

from abc import ABC
from typing import ClassVar
import voluptuous as vol

import homeassistant.helpers.config_validation as cv


from eltakobus.eep import (A5_04_01, A5_04_02, A5_04_03, A5_06_01, A5_06_02, A5_06_03, A5_07_01,
                           A5_08_01, A5_09_04, A5_09_05, A5_09_0C, A5_10_03,
                           A5_10_06, A5_10_12, A5_12_01, A5_12_02, A5_12_03, A5_13_01, A5_30_01, A5_30_03,
                           A5_14_09, A5_14_0A, A5_20_04, A5_38_08, D5_00_01, F6_01_01, F6_02_01, F6_02_02,
                           F6_05_01, F6_05_02, F6_10_00, G5_3F_7F, H5_3F_7F,
                           M5_38_08, VOC_SubstancesType, EEP)

from ..observation.integration_log import LOG_LEVELS as INTEGRATION_LOG_LEVELS
from ..const import (CONF_AREA, CONF_BASE_ID, CONF_COOLING_MODE, CONF_DEPRECATED_ENABLE_FRONTEND,
                     CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI, CONF_DEPRECATED_FRONTEND_DEV_URL,
                     CONF_DEVICE_TYPE, CONF_EEP, CONF_ENABLE_FRONTEND, CONF_ENABLE_TEST_PAGE,
                     CONF_FAST_STATUS_CHANGE, CONF_GATEWAY, CONF_GATEWAY_ADDRESS,
                     CONF_GATEWAY_AUTO_RECONNECT, CONF_GATEWAY_ID, CONF_GATEWAY_MESSAGE_DELAY,
                     CONF_GATEWAY_PORT, CONF_GERNERAL_SETTINGS, CONF_GRAFANA_TOKEN, CONF_GRAFANA_URL,
                     CONF_ID_REGEX, CONF_INVERT_SIGNAL, CONF_LOG_ENOCEAN_TELEGRAMS,
                     CONF_LOG_LEVEL, CONF_LOG_LEVEL_BUS_MESSAGES, CONF_LOG_LEVEL_DECODE_ERRORS,
                     CONF_LOG_LEVEL_INCOMING,
                     CONF_LOG_LEVEL_OUTGOING, CONF_LOG_LEVEL_POLLING, CONF_LOG_LEVEL_UNKNOWN_DEVICES,
                     CONF_MAX_TARGET_TEMPERATURE, CONF_METER_TARIFFS, CONF_MIN_TARGET_TEMPERATURE,
                     CONF_OFF_TEMPERATURE, CONF_PLUG_AND_PLAY, CONF_PLUG_AND_PLAY_INTERVAL, CONF_ROOM_SENSOR,
                     CONF_ROOM_THERMOSTAT, CONF_SENDER, CONF_SENSOR, CONF_SERIAL_PATH,
                     CONF_SHOW_DEV_ID_IN_DEV_NAME, CONF_SHOW_PANEL_IN_SIDEBAR, CONF_SIMULATED,
                     CONF_SWITCH_BUTTON, CONF_TELEGRAM_LOG_BACKUP_COUNT, CONF_TELEGRAM_LOG_BUFFER_SIZE,
                     CONF_TELEGRAM_LOG_DECODE_EEP, CONF_TELEGRAM_LOG_FILENAME, CONF_TELEGRAM_LOG_FORMAT,
                     CONF_TELEGRAM_LOG_INCLUDE_POLLING, CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB,
                     CONF_TELEGRAM_LOG_ROTATE_DAYS, CONF_TIMESERIES_BUCKET, CONF_TIMESERIES_ENABLED,
                     CONF_TIMESERIES_MEASUREMENT, CONF_TIMESERIES_ORG, CONF_TIMESERIES_TOKEN,
                     CONF_TIMESERIES_URL, CONF_TIME_CLOSES, CONF_TIME_OPENS, CONF_TIME_TILTS,
                     CONF_VOC_TYPE_INDEXES, DOMAIN, LANGUAGE_ABBREVIATION, TelegramLogFormat,
                     TelegramLogLevel)
from ..core.gateway import GatewayDeviceType

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA as BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.components.cover import (
    DEVICE_CLASSES_SCHEMA as COVER_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ID,
    CONF_NAME,
    CONF_DEVICES,
    Platform,
    CONF_TEMPERATURE_UNIT,
    UnitOfTemperature,
    CONF_LANGUAGE,
)

A5_02_EEPS = [EEP.find(f"A5-02-{suffix}").eep_string for suffix in (
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "0A", "0B",
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "1A", "1B", "20", "30",
)]
A5_07_EEPS = [A5_07_01.eep_string, EEP.find("A5-07-02").eep_string, EEP.find("A5-07-03").eep_string]

CONF_EEP_SUPPORTED_BINARY_SENSOR = [F6_01_01.eep_string,
                                    F6_02_01.eep_string,
                                    F6_02_02.eep_string,
                                    F6_10_00.eep_string,
                                    D5_00_01.eep_string,
                                    A5_07_01.eep_string,
                                    A5_08_01.eep_string,
                                    A5_30_01.eep_string,
                                    A5_30_03.eep_string,
                                    EEP.find("A5-07-02").eep_string,
                                    EEP.find("A5-07-03").eep_string,
                                    A5_14_09.eep_string,
                                    A5_14_0A.eep_string,
                                    F6_05_01.eep_string,
                                    F6_05_02.eep_string]
CONF_EEP_SUPPORTED_SENSOR_ROCKER_SWITCH = [F6_02_01.eep_string, F6_02_02.eep_string]

def _get_sender_schema(supported_sender_eep) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Required(CONF_EEP): vol.In(supported_sender_eep),
        }
    )

def _get_receiver_schema(supported_sender_eep) -> vol.Schema:
    return _get_sender_schema(supported_sender_eep).extend({
        vol.Optional(CONF_GATEWAY_ID, default=None): cv.Number,
    })

class EltakoPlatformSchema(ABC):
    """Voluptuous schema for Eltako platform entity configuration."""
    PLATFORM: ClassVar[Platform | str]
    ENTITY_SCHEMA: ClassVar[vol.Schema]

    @classmethod
    def platform_node(cls) -> dict[vol.Optional, vol.All]:
        """Return a schema node for the platform."""
        return {
            vol.Optional(str(cls.PLATFORM)): vol.All(
                cv.ensure_list, [cls.ENTITY_SCHEMA]
            )
        }


class GeneralSettings(EltakoPlatformSchema):
    """Voluptuous schema for general settings of this integration"""
    PLATFORM = CONF_GERNERAL_SETTINGS

    ENTITY_SCHEMA = vol.Schema({
            vol.Optional(CONF_FAST_STATUS_CHANGE, default=False): cv.boolean,
            vol.Optional(CONF_SHOW_DEV_ID_IN_DEV_NAME, default=False): cv.boolean,

            # Plug & play: detect connected gateways and their devices automatically
            vol.Optional(CONF_PLUG_AND_PLAY, default=False): cv.boolean,
            # once a day: probing the ports and reading a bus is not free, and a gateway is
            # plugged in rarely. The button on the overview page runs it on demand.
            vol.Optional(CONF_PLUG_AND_PLAY_INTERVAL, default=1440): vol.All(vol.Coerce(int), vol.Range(min=0, max=10080)),

            # Web ui / panel of the integration incl. all its sub pages. On by default: it is
            # the place where gateways, devices and these settings are configured, so an
            # installation without any yaml has to be able to reach it.
            vol.Optional(CONF_ENABLE_FRONTEND, default=True): cv.boolean,
            # only the entry in the sidebar - the panel stays reachable under its url either way
            vol.Optional(CONF_SHOW_PANEL_IN_SIDEBAR, default=True): cv.boolean,
            vol.Optional(CONF_ENABLE_TEST_PAGE, default=True): cv.boolean,

            # EnOcean telegram logging and analysis
            vol.Optional(CONF_LOG_ENOCEAN_TELEGRAMS, default=False): cv.boolean,
            vol.Optional(CONF_TELEGRAM_LOG_FILENAME, default=""): cv.string,
            vol.Optional(CONF_TELEGRAM_LOG_FORMAT, default=TelegramLogFormat.JSONL.value): vol.In([f.value for f in TelegramLogFormat]),
            vol.Optional(CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB, default=10): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1024)),
            vol.Optional(CONF_TELEGRAM_LOG_ROTATE_DAYS, default=7): vol.All(vol.Coerce(float), vol.Range(min=0, max=3650)),
            vol.Optional(CONF_TELEGRAM_LOG_BACKUP_COUNT, default=3): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional(CONF_TELEGRAM_LOG_INCLUDE_POLLING, default=False): cv.boolean,
            vol.Optional(CONF_TELEGRAM_LOG_DECODE_EEP, default=True): cv.boolean,
            vol.Optional(CONF_TELEGRAM_LOG_BUFFER_SIZE, default=500): vol.All(vol.Coerce(int), vol.Range(min=0, max=100000)),

            # export of the recorded telegrams into a timeseries database (InfluxDB, for Grafana)
            vol.Optional(CONF_TIMESERIES_ENABLED, default=False): cv.boolean,
            vol.Optional(CONF_TIMESERIES_URL, default=""): cv.string,
            vol.Optional(CONF_TIMESERIES_TOKEN, default=""): cv.string,
            vol.Optional(CONF_TIMESERIES_ORG, default=""): cv.string,
            vol.Optional(CONF_TIMESERIES_BUCKET, default="eltako"): cv.string,
            vol.Optional(CONF_TIMESERIES_MEASUREMENT, default="eltako_telegram"): cv.string,
            vol.Optional(CONF_GRAFANA_URL, default=""): cv.string,
            vol.Optional(CONF_GRAFANA_TOKEN, default=""): cv.string,

            # level of the integration itself; '' keeps whatever `logger:` configures
            vol.Optional(CONF_LOG_LEVEL, default=""): vol.In(INTEGRATION_LOG_LEVELS + [""]),

            # log levels per telegram category
            vol.Optional(CONF_LOG_LEVEL_INCOMING, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),
            vol.Optional(CONF_LOG_LEVEL_OUTGOING, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),
            vol.Optional(CONF_LOG_LEVEL_UNKNOWN_DEVICES, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),
            vol.Optional(CONF_LOG_LEVEL_BUS_MESSAGES, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),
            vol.Optional(CONF_LOG_LEVEL_POLLING, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),
            vol.Optional(CONF_LOG_LEVEL_DECODE_ERRORS, default=TelegramLogLevel.OFF.value): vol.In([level.value for level in TelegramLogLevel]),

            # deprecated options: still accepted so that existing configurations do not break,
            # but they have no effect anymore. A warning is logged during setup.
            vol.Optional(CONF_DEPRECATED_ENABLE_FRONTEND): cv.boolean,
            vol.Optional(CONF_DEPRECATED_FRONTEND_DEV_URL): cv.string,
            vol.Optional(CONF_DEPRECATED_ENABLE_TELEGRAM_WEB_UI): cv.boolean,
    })

    @classmethod
    def get_id(cls) -> str:
        return cls.PLATFORM

    @classmethod
    def get_schema(cls) -> vol.Schema:
        return cls.ENTITY_SCHEMA


class BinarySensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako binary sensors."""
    PLATFORM = Platform.BINARY_SENSOR

    CONF_EEP = CONF_EEP
    CONF_ID_REGEX = CONF_ID_REGEX
    CONF_INVERT_SIGNAL = CONF_INVERT_SIGNAL

    DEFAULT_NAME = "Binary sensor"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED_BINARY_SENSOR),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
                vol.Optional(CONF_INVERT_SIGNAL, default=False): cv.boolean,
            }
        ),
    )

class LightSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako lights."""
    PLATFORM = Platform.LIGHT

    CONF_EEP_SUPPORTED = [A5_38_08.eep_string, M5_38_08.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [A5_38_08.eep_string, F6_02_01.eep_string, F6_02_02.eep_string]

    DEFAULT_NAME = "Light"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
            }
        ),
    )

class SwitchSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako switches."""
    PLATFORM = Platform.SWITCH

    CONF_EEP_SUPPORTED = [M5_38_08.eep_string, F6_02_01.eep_string, F6_02_02.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [F6_02_01.eep_string, F6_02_02.eep_string, A5_38_08.eep_string]

    DEFAULT_NAME = "Switch"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
            }
        ),
    )

class SensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako sensors."""
    PLATFORM = Platform.SENSOR

    CONF_EEP_SUPPORTED = [*A5_02_EEPS,
                          A5_04_01.eep_string,
                          A5_04_02.eep_string,
                          A5_04_03.eep_string,
                          A5_06_01.eep_string,
                          A5_06_02.eep_string,
                          A5_06_03.eep_string,
                          *A5_07_EEPS,
                          A5_08_01.eep_string,
                          A5_09_04.eep_string,
                          A5_09_05.eep_string,
                          A5_09_0C.eep_string,
                          A5_10_03.eep_string,
                          A5_10_06.eep_string,
                          A5_10_12.eep_string,
                          A5_12_01.eep_string,
                          A5_12_02.eep_string,
                          A5_12_03.eep_string,
                          A5_13_01.eep_string,
                          A5_20_04.eep_string,
                          F6_10_00.eep_string,
                          ]

    DEFAULT_NAME = ""
    DEFAULT_METER_TARIFFS = [1]

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
                vol.Optional(CONF_LANGUAGE, default="en"): vol.In([v for v in LANGUAGE_ABBREVIATION]),
                vol.Optional(CONF_VOC_TYPE_INDEXES, default=[0]): vol.All(cv.ensure_list, [vol.In([v.index for v in VOC_SubstancesType])]),
                vol.Optional(CONF_METER_TARIFFS, default=DEFAULT_METER_TARIFFS): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=16))]),
                vol.Optional(CONF_DEVICE_CLASS): BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
            }
        ),
    )

class CoverSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako covers."""
    PLATFORM = Platform.COVER

    CONF_EEP_SUPPORTED = [G5_3F_7F.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [H5_3F_7F.eep_string]

    DEFAULT_NAME = "Cover"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): COVER_DEVICE_CLASSES_SCHEMA,
                vol.Optional(CONF_TIME_CLOSES): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                vol.Optional(CONF_TIME_OPENS): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                vol.Optional(CONF_TIME_TILTS): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            }
        ),
    )

class ClimateSchema(EltakoPlatformSchema):
    """Schema for Eltako heating and cooling."""
    PLATFORM = Platform.CLIMATE

    CONF_CLIMATE_EEP = [A5_10_06.eep_string]
    CONF_CLIMATE_SENDER_EEP = [A5_10_06.eep_string]

    DEFAULT_NAME = "Climate"
    DEFAULT_COOLING_SWITCH_NAME = "cooling mode switch"
    DEFAULT_COOLING_SENDER_NAME = "cooling mode sender"

    CONF_COOLING_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SENSOR): vol.Schema(  # detects if heater is switch globally into cooling mode
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Optional(CONF_SWITCH_BUTTON, default=0): cv.byte,
        }),
        vol.Optional(CONF_SENDER): vol.Schema(  # sends frequently a signal to stay in cooling mode if detect by cooling-mode-sensor
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Required(CONF_EEP): vol.In([F6_02_01.eep_string, F6_02_02.eep_string]),
            vol.Optional(CONF_NAME, default=DEFAULT_COOLING_SENDER_NAME): cv.string,
            vol.Optional(CONF_GATEWAY_ID, default=None): cv.matches_regex(CONF_ID_REGEX),
        }),
    })

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_CLIMATE_EEP),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_CLIMATE_SENDER_EEP),             # temperature controller command
                vol.Optional(CONF_TEMPERATURE_UNIT, default="°C"): vol.In([u.value for u in UnitOfTemperature]),  # for display: "°C", "°F", "K"
                vol.Optional(CONF_MIN_TARGET_TEMPERATURE, default=17): cv.Number,
                vol.Optional(CONF_MAX_TARGET_TEMPERATURE, default=25): cv.Number,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
                vol.Optional(CONF_ROOM_THERMOSTAT): _get_sender_schema(CONF_CLIMATE_SENDER_EEP),    # physical thermostat like FUTH
                vol.Optional(CONF_COOLING_MODE): CONF_COOLING_MODE_SCHEMA,                          # if not provided cooling is not supported
                vol.Optional(CONF_ROOM_SENSOR): cv.string,                                          # entity_id of an HA sensor providing current temperature
                vol.Optional(CONF_OFF_TEMPERATURE): cv.Number,                                      # anti-frost / off-mode target temperature
            }
        ),
    )


class FanSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako ventilation fans."""
    PLATFORM = Platform.FAN

    CONF_EEP_SUPPORTED = [A5_38_08.eep_string, M5_38_08.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [A5_38_08.eep_string]
    DEFAULT_NAME = "Fan"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_AREA): cv.string,
            }
        ),
    )

class GatewaySchema(EltakoPlatformSchema):
    """Voluptuous schema for bus gateway"""
    PLATFORM = CONF_GATEWAY

    ENTITY_SCHEMA = vol.Schema({
            vol.Required(CONF_ID): cv.Number,
            vol.Required(CONF_DEVICE_TYPE, default=GatewayDeviceType.GatewayEltakoFGW14USB.value): vol.In([g.value for g in GatewayDeviceType]),
            vol.Optional(CONF_BASE_ID, default='00-00-00-00'): cv.matches_regex(CONF_ID_REGEX),
            vol.Optional(CONF_NAME, default=""): cv.string,
            vol.Optional(CONF_SERIAL_PATH): cv.string,
            vol.Optional(CONF_GATEWAY_AUTO_RECONNECT, default=True): cv.boolean,
            vol.Optional(CONF_GATEWAY_ADDRESS): cv.string,
            vol.Optional(CONF_GATEWAY_MESSAGE_DELAY, default=0.01): cv.Number,
            vol.Optional(CONF_GATEWAY_PORT, default=5100): cv.Number,
            # A gateway of this type whose hardware does not exist: nothing is opened, its
            # devices are simulated in this process (see simulation/). Everything else about
            # the gateway stays as it is, so a simulated FAM14 is still a bus gateway.
            vol.Optional(CONF_SIMULATED, default=False): cv.boolean,
            vol.Optional(CONF_DEVICES): vol.All(vol.Schema({
                **BinarySensorSchema.platform_node(),
                **LightSchema.platform_node(),
                **SwitchSchema.platform_node(),
                **SensorSchema.platform_node(),
                **CoverSchema.platform_node(),
                **ClimateSchema.platform_node(),
                **FanSchema.platform_node(),
            })),
        })

    @classmethod
    def get_schema(cls) -> vol.Schema:
        """Return a schema."""
        return cls.ENTITY_SCHEMA

CONFIG_SCHEMA = vol.Schema(
    {
        # An `eltako:` line with nothing under it is a valid configuration - and a useful one:
        # Home Assistant loads a custom integration only for a config entry or for a yaml key,
        # so that single line is the shortest way to get the web ui into the sidebar without
        # adding the integration first. Everything else is then configured in the web ui.
        # An empty section arrives as None, which a dictionary schema would reject.
        DOMAIN: vol.All(lambda section: {} if section is None else section, vol.Schema({
            vol.Optional(CONF_GERNERAL_SETTINGS): GeneralSettings.get_schema(),
            vol.Optional(CONF_GATEWAY): vol.All(cv.ensure_list, [GatewaySchema.ENTITY_SCHEMA]),
        })),
    },
    extra=vol.ALLOW_EXTRA,
)
