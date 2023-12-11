"""Voluptuous schemas for the Eltako integration."""

from typing import Final

from abc import ABC
from typing import ClassVar
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import ENTITY_CATEGORIES_SCHEMA

from eltakobus.eep import *

from .const import *
from .gateway import GatewayDeviceTypes

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA as BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.components.cover import (
    DEVICE_CLASSES_SCHEMA as COVER_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.components.sensor import (
    CONF_STATE_CLASS,
    DEVICE_CLASSES_SCHEMA as SENSOR_DEVICE_CLASSES_SCHEMA,
    STATE_CLASSES_SCHEMA,
)
from homeassistant.components.switch import (
    DEVICE_CLASSES_SCHEMA as SWITCH_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.components.cover import (
    DEVICE_CLASSES_SCHEMA as COVER_DEVICE_CLASSES_SCHEMA,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ENTITY_CATEGORY,
    CONF_ENTITY_ID,
    CONF_EVENT,
    CONF_MODE,
    CONF_ID,
    CONF_NAME,
    CONF_TYPE,
    CONF_DEVICE,
    CONF_DEVICES,
    Platform,
    CONF_TEMPERATURE_UNIT,
    UnitOfTemperature,
    CONF_LANGUAGE,
)

CONF_EEP_SUPPORTED_BINARY_SENSOR = [F6_02_01.eep_string, F6_02_02.eep_string, F6_10_00.eep_string, D5_00_01.eep_string, A5_08_01.eep_string]
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
        vol.Optional(CONF_GATEWAY_BASE_ID, default=None): cv.matches_regex(CONF_ID_REGEX),
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
                vol.Optional(CONF_DEVICE_CLASS): BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
                vol.Optional(CONF_INVERT_SIGNAL, default=False): cv.boolean,
            }
        ),
    )

class LightSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako lights."""
    PLATFORM = Platform.LIGHT

    CONF_EEP_SUPPORTED = [A5_38_08.eep_string, M5_38_08.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [A5_38_08.eep_string]

    DEFAULT_NAME = "Light"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        ),
    )

class SwitchSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako switches."""
    PLATFORM = Platform.SWITCH

    CONF_EEP_SUPPORTED = [M5_38_08.eep_string]
    CONF_SENDER_EEP_SUPPORTED = [F6_02_01.eep_string]

    DEFAULT_NAME = "Switch"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_SENDER_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        ),
    )

class SensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako sensors."""
    PLATFORM = Platform.SENSOR

    CONF_EEP_SUPPORTED = [A5_04_02.eep_string,
                          A5_09_0C.eep_string,
                          A5_10_06.eep_string,
                          A5_10_12.eep_string,
                          A5_12_01.eep_string, 
                          A5_12_02.eep_string, 
                          A5_12_03.eep_string, 
                          A5_13_01.eep_string, 
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
                vol.Optional(CONF_LANGUAGE, default="en"): vol.In([v for v in LANGUAGE_ABBREVIATIONS]),
                vol.Optional(CONF_VOC_TYPE_INDEXES, default=[0]): vol.All(cv.ensure_list, [vol.In([v.index for v in VOC_SubstancesType])]),
                vol.Optional(CONF_METER_TARIFFS, default=DEFAULT_METER_TARIFFS): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=16))]),
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
                vol.Optional(CONF_DEVICE_CLASS): COVER_DEVICE_CLASSES_SCHEMA,
                vol.Optional(CONF_TIME_CLOSES): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                vol.Optional(CONF_TIME_OPENS): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
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
            vol.Optional(CONF_GATEWAY_BASE_ID, default=None): cv.matches_regex(CONF_ID_REGEX),
        }),
    })

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_CLIMATE_EEP),
                vol.Required(CONF_SENDER): _get_sender_schema(CONF_CLIMATE_SENDER_EEP),             # temperature controller command
                vol.Required(CONF_TEMPERATURE_UNIT): vol.In([u.value for u in UnitOfTemperature]),  # for display: "°C", "°F", "K"
                vol.Optional(CONF_MIN_TARGET_TEMPERATURE, default=17): cv.Number,
                vol.Optional(CONF_MAX_TARGET_TEMPERATURE, default=25): cv.Number,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,  
                vol.Optional(CONF_ROOM_THERMOSTAT): _get_sender_schema(CONF_CLIMATE_SENDER_EEP),    # physical thermostat like FUTH
                vol.Optional(CONF_COOLING_MODE): CONF_COOLING_MODE_SCHEMA                           # if not provided cooling is not supported
            }
        ),
    )

class GatewaySchema(EltakoPlatformSchema):
    """Voluptuous schema for bus gateway"""
    PLATFORM = CONF_GATEWAY

    ENTITY_SCHEMA = vol.Schema({
            vol.Required(CONF_DEVICE, default=GatewayDeviceTypes.GatewayEltakoFAM14.value): vol.In([g.value for g in GatewayDeviceTypes]),
            vol.Optional(CONF_NAME, default=""): cv.string,
            vol.Required(CONF_BASE_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Optional(CONF_SERIAL_PATH): cv.string,
            vol.Required(CONF_DEVICES): vol.All(vol.Schema({
                **BinarySensorSchema.platform_node(),
                **LightSchema.platform_node(),
                **SwitchSchema.platform_node(),
                **SensorSchema.platform_node(),
                **SensorSchema.platform_node(),
                **CoverSchema.platform_node(),
                **ClimateSchema.platform_node(),
            })),
        })
    
    @classmethod
    def get_schema(cls) -> vol.Schema:
        """Return a schema."""
        return cls.ENTITY_SCHEMA

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Optional(CONF_GERNERAL_SETTINGS): GeneralSettings.get_schema(),
            vol.Optional(CONF_GATEWAY): vol.All(cv.ensure_list, [GatewaySchema.ENTITY_SCHEMA]),
        })
    },
    extra=vol.ALLOW_EXTRA,
)
