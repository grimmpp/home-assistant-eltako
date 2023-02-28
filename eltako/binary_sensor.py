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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, DOMAIN, MANUFACTURER

CONF_EEP_SUPPORTED = ["F6-02-01", "F6-02-02", "F6-10-00", "D5-00-01", "A5-08-01"]

DEFAULT_NAME = "Binary sensor"
DEPENDENCIES = ["eltakobus"]
EVENT_BUTTON_PRESSED = "button_pressed"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
        vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
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
    dev_eep = config.get(CONF_EEP)
    device_class = config.get(CONF_DEVICE_CLASS)

    add_entities([EltakoBinarySensor(dev_id, dev_name, dev_eep, device_class)])


class EltakoBinarySensor(EltakoEntity, BinarySensorEntity):
    """Representation of Eltako binary sensors such as wall switches.

    Supported EEPs (EnOcean Equipment Profiles):
    - F6-02-01 (Light and Blind Control - Application Style 2)
    - F6-02-02 (Light and Blind Control - Application Style 1)
    - F6-10-00
    - D5-00-01
    """

    def __init__(self, dev_id, dev_name, dev_eep, device_class):
        """Initialize the Eltako binary sensor."""
        super().__init__(dev_id, dev_name)
        self._dev_eep = dev_eep
        self._device_class = device_class
        self.which = -1
        self.onoff = -1
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{device_class}"
        self.entity_id = f"binary_sensor.{self.unique_id}"

    @property
    def name(self):
        """Return the default name for the binary sensor."""
        return None

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return self._device_class

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.dev_id.plain_address().hex())
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self._dev_eep,
        )

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
        
        if self._dev_eep in ["F6-02-01", "F6-02-02"]:
            if msg.org == 0x05:
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
        elif self._dev_eep in ["F6-10-00"]:
            if msg.org != 0x05:
                return

            action = (msg.data[0] & 0x70) >> 4

            if action == 0x07:
                    self._attr_is_on = False
            elif action in (0x04, 0x06):
                    self._attr_is_on = True

            self.schedule_update_ha_state()
        elif self._dev_eep in ["D5-00-01"]:
            if msg.org == 0x06:
                if msg.data[0] == 0x09:
                    self._attr_is_on = False
                elif msg.data[0] == 0x08:
                    self._attr_is_on = True

                self.schedule_update_ha_state()
        elif self._dev_eep in ["A5-08-01"]:
            if msg.org == 0x07:
                if msg.data[3] == 0x0f:
                    self._attr_is_on = False
                elif msg.data[3] == 0x0d:
                    self._attr_is_on = True
                    
                self.schedule_update_ha_state()

