"""Support for Eltako binary sensors."""
from __future__ import annotations

from eltakobus.util import combine_hex
from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.binary_sensor import (
    DEVICE_CLASSES_SCHEMA,
    PLATFORM_SCHEMA,
    BinarySensorEntity,
)
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_CLASS, CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG, LOGGER

DEPENDENCIES = ["eltakobus"]
EVENT_BUTTON_PRESSED = "button_pressed"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Binary Sensor platform for Eltako."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    
    entities: list[EltakoSensor] = []
    
    if Platform.BINARY_SENSOR in config:
        for entity_config in config[Platform.BINARY_SENSOR]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            device_class = entity_config.get(CONF_DEVICE_CLASS)
            eep_string = entity_config.get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
            except:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                entities.append(EltakoBinarySensor(dev_id, dev_name, dev_eep, device_class))


    async_add_entities(entities)
    

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
            model=self._dev_eep.eep_string,
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
        
        try:
            decoded = self._dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return
        
        if self._dev_eep in [F6_02_01, F6_02_02]:
            if decoded.rocker_first_action == 0:
                discriminator = "left"
                action = 1
            elif decoded.rocker_first_action == 1:
                discriminator = "left"
                action = 0
            elif decoded.rocker_first_action == 2:
                discriminator = "right"
                action = 1
            elif decoded.rocker_first_action == 3:
                discriminator = "right"
                action = 0
            else:
                return
            
            pressed = decoded.energy_bow
            
            self.hass.bus.fire(
                EVENT_BUTTON_PRESSED,
                {
                    "id": self.dev_id.plain_address(),
                    "discriminator": discriminator,
                    "action": action,
                    "pressed": pressed,
                },
            )
        elif self._dev_eep in [F6_10_00]:
            action = (decoded.movement & 0x70) >> 4
            
            if action == 0x07:
                self._attr_is_on = False
            elif action in (0x04, 0x06):
                self._attr_is_on = False
            else:
                return

            self.schedule_update_ha_state()
        elif self._dev_eep in [D5_00_01]:
            if decoded.learn_button == 0:
                return
            
            self._attr_is_on = decoded.contact == 0

            self.schedule_update_ha_state()
        elif self._dev_eep in [A5_08_01]:
            if decoded.learn_button == 0:
                return
                
            self._attr_is_on = decoded.pir_status == 0
            
            self.schedule_update_ha_state()

