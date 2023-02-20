"""Support for Eltako binary sensors."""
from __future__ import annotations

from eltakobus.util import combine_hex
from eltakobus.util import AddressExpression
import voluptuous as vol

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA,
    BinarySensorEntity,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_ID, CONF_NAME
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity

DEFAULT_NAME = "Eltako binary sensor"
DEPENDENCIES = ["eltakobus"]
EVENT_BUTTON_PRESSED = "button_pressed"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Binary Sensor platform for Eltako."""
    dev_id = AddressExpression.parse(config.get(CONF_ID))
    dev_name = config.get(CONF_NAME)
    device_class = config.get(CONF_DEVICE_CLASS)

    add_entities([EltakoBinarySensor(dev_id, dev_name, device_class)])


class EltakoBinarySensor(EltakoEntity, BinarySensorEntity):
    """Representation of Eltako binary sensors such as wall switches.

    Supported EEPs (EnOcean Equipment Profiles):
    - F6-02-01 (Light and Blind Control - Application Style 2)
    - F6-02-02 (Light and Blind Control - Application Style 1)
    """

    def __init__(self, dev_id, dev_name, device_class):
        """Initialize the Eltako binary sensor."""
        super().__init__(dev_id, dev_name)
        self._device_class = device_class
        self.which = -1
        self.onoff = -1
        self._attr_unique_id = f"{dev_id.plain_address().hex()}-{device_class}"

    @property
    def name(self):
        """Return the default name for the binary sensor."""
        return self.dev_name

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._device_class

    def value_changed(self, msg):
        """Fire an event with the data that have changed.

        This method is called when there is an incoming message associated
        with this platform.

        Example message data:
        - 2nd button pressed
            ['0xf6', '0x10', '0x00', '0x2d', '0xcf', '0x45', '0x30']
        - button released
            ['0xf6', '0x00', '0x00', '0x2d', '0xcf', '0x45', '0x20']
        """
        # Energy Bow
        pushed = None

        if msg.data[6] == 0x30:
            pushed = 1
        elif msg.data[6] == 0x20:
            pushed = 0

        self.schedule_update_ha_state()

        action = msg.data[1]
        if action == 0x70:
            self.which = 0
            self.onoff = 0
        elif action == 0x50:
            self.which = 0
            self.onoff = 1
        elif action == 0x30:
            self.which = 1
            self.onoff = 0
        elif action == 0x10:
            self.which = 1
            self.onoff = 1
        elif action == 0x37:
            self.which = 10
            self.onoff = 0
        elif action == 0x15:
            self.which = 10
            self.onoff = 1
        self.hass.bus.fire(
            EVENT_BUTTON_PRESSED,
            {
                "id": self.dev_id,
                "pushed": pushed,
                "which": self.which,
                "onoff": self.onoff,
            },
        )
