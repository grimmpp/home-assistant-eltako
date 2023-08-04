"""Voluptuous schemas for the Eltako integration."""

from abc import ABC
from typing import ClassVar
import voluptuous as vol
from eltakobus.eep import *


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
    Platform,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import ENTITY_CATEGORIES_SCHEMA

from .const import CONF_ID_REGEX, CONF_EEP, CONF_SENDER, CONF_METER_TARIFFS, CONF_TIME_CLOSES, CONF_TIME_OPENS, DOMAIN, CONF_INVERT_SIGNAL

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

class BinarySensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako binary sensors."""
    PLATFORM = Platform.BINARY_SENSOR

    CONF_EEP = CONF_EEP
    CONF_ID_REGEX = CONF_ID_REGEX
    CONF_INVERT_SIGNAL = CONF_INVERT_SIGNAL
    
    CONF_EEP_SUPPORTED = [F6_02_01.eep_string, F6_02_02.eep_string, F6_10_00.eep_string, D5_00_01.eep_string, A5_08_01.eep_string]

    DEFAULT_NAME = "Binary sensor"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
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

    SENDER_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Required(CONF_EEP): vol.In(CONF_SENDER_EEP_SUPPORTED),
        }
    )

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): SENDER_SCHEMA,
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

    SENDER_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Required(CONF_EEP): vol.In(CONF_SENDER_EEP_SUPPORTED),
        }
    )

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): SENDER_SCHEMA,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        ),
    )

class SensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako sensors."""
    PLATFORM = Platform.SENSOR

    CONF_EEP_SUPPORTED = [A5_13_01.eep_string, F6_10_00.eep_string, A5_12_01.eep_string, A5_12_02.eep_string, A5_12_03.eep_string, A5_04_02.eep_string]

    DEFAULT_NAME = ""
    DEFAULT_METER_TARIFFS = [1]

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
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

    SENDER_SCHEMA = vol.Schema(
        {
            vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
            vol.Required(CONF_EEP): vol.In(CONF_SENDER_EEP_SUPPORTED),
        }
    )

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER): SENDER_SCHEMA,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): COVER_DEVICE_CLASSES_SCHEMA,
                vol.Optional(CONF_TIME_CLOSES): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
                vol.Optional(CONF_TIME_OPENS): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            }
        ),
    )
