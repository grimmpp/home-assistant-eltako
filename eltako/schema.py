"""Voluptuous schemas for the Eltako integration."""

from abc import ABC
from typing import ClassVar
import voluptuous as vol

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

from .const import CONF_ID_REGEX, CONF_EEP, CONF_SENDER_ID, CONF_METER_TARIFFS, DOMAIN

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
    
    CONF_EEP_SUPPORTED = ["F6-02-01", "F6-02-02", "F6-10-00", "D5-00-01", "A5-08-01"]

    DEFAULT_NAME = "Binary sensor"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_DEVICE_CLASS): BINARY_SENSOR_DEVICE_CLASSES_SCHEMA,
            }
        ),
    )

class LightSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako lights."""

    PLATFORM = Platform.LIGHT

    CONF_EEP = CONF_EEP
    CONF_ID_REGEX = CONF_ID_REGEX
    CONF_SENDER_ID = CONF_SENDER_ID

    CONF_EEP_SUPPORTED = ["A5-38-08", "M5-38-08"]

    DEFAULT_NAME = "Light"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER_ID): cv.string,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        ),
    )

class SwitchSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako switches."""

    PLATFORM = Platform.SWITCH

    CONF_EEP = CONF_EEP
    CONF_ID_REGEX = CONF_ID_REGEX
    CONF_SENDER_ID = CONF_SENDER_ID

    CONF_EEP_SUPPORTED = ["M5-38-08"]

    DEFAULT_NAME = "Switch"

    ENTITY_SCHEMA = vol.All(
        vol.Schema(
            {
                vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
                vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
                vol.Required(CONF_SENDER_ID): cv.string,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        ),
    )

class SensorSchema(EltakoPlatformSchema):
    """Voluptuous schema for Eltako sensors."""

    PLATFORM = Platform.SENSOR

    CONF_EEP = CONF_EEP
    CONF_ID_REGEX = CONF_ID_REGEX
    CONF_METER_TARIFFS = CONF_METER_TARIFFS
    
    CONF_EEP_SUPPORTED = ["A5-13-01", "F6-10-00", "A5-12-01", "A5-12-02", "A5-12-03"]

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
