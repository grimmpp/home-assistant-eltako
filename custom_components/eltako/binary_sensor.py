"""Support for Eltako binary sensors."""
from __future__ import annotations

from eltakobus.util import AddressExpression, b2a
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
from .const import *

import json

DEPENDENCIES = ["eltakobus"]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Binary Sensor platform for Eltako."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]
    
    entities: list[EltakoSensor] = []
    
    if Platform.BINARY_SENSOR in config:
        for entity_config in config[Platform.BINARY_SENSOR]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            device_class = entity_config.get(CONF_DEVICE_CLASS)
            eep_string = entity_config.get(CONF_EEP)
            invert_signal =  entity_config.get(CONF_INVERT_SIGNAL)

            try:
                dev_eep = EEP.find(eep_string)
            except:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                entities.append(EltakoBinarySensor(gateway, dev_id, dev_name, dev_eep, device_class, invert_signal))

    for e in entities:
        LOGGER.debug(f"Add entity {e.dev_name} (id: {e.dev_id}, eep: {e.dev_eep}) of platform type {Platform.BINARY_SENSOR} to Home Assistant.")
    async_add_entities(entities)
    

class EltakoBinarySensor(EltakoEntity, BinarySensorEntity):
    """Representation of Eltako binary sensors such as wall switches.

    Supported EEPs (EnOcean Equipment Profiles):
    - F6-02-01 (Light and Blind Control - Application Style 2)
    - F6-02-02 (Light and Blind Control - Application Style 1)
    - F6-10-00
    - D5-00-01
    """

    def __init__(self, gateway, dev_id, dev_name, dev_eep, device_class, invert_signal):
        """Initialize the Eltako binary sensor."""
        super().__init__(gateway, dev_id, dev_name)
        self._dev_eep = dev_eep
        self._attr_device_class = device_class
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{device_class}"
        self.entity_id = f"binary_sensor.{self.unique_id}"
        self.dev_id = dev_id
        self.dev_name = dev_name
        self.gateway = gateway
        self.invert_signal = invert_signal

    @property
    def name(self):
        """Return the default name for the binary sensor."""
        return None

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
            via_device=(DOMAIN, self.gateway.unique_id),
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
            LOGGER.debug("msg : %s", json.dumps(decoded.__dict__))
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return

        if self._dev_eep in [F6_02_01, F6_02_02]:
            pressed_buttons = []
            pressed = decoded.energy_bow == 1
            two_buttons_pressed = decoded.second_action == 1
            fa = decoded.rocker_first_action
            sa = decoded.rocker_second_action

            # Data is only available when button is pressed. 
            # Button cannot be identified when releasing it.
            # if at least one button is pressed
            if pressed:
                if fa == 0:
                    pressed_buttons += ["LB"]
                if fa == 1:
                    pressed_buttons += ["LT"]
                if fa == 2:
                    pressed_buttons += ["RB"]
                if fa == 3:
                    pressed_buttons += ["RT"]
            if two_buttons_pressed:
                if sa == 0:
                    pressed_buttons += ["LB"]
                if sa == 1:
                    pressed_buttons += ["LT"]
                if sa == 2:
                    pressed_buttons += ["RB"]
                if sa == 3:
                    pressed_buttons += ["RT"]
            else:
                # button released but no detailed information available
                pass

            switch_address = b2a(msg.address, '-').upper()

            event_id = f"{EVENT_BUTTON_PRESSED}_{switch_address}"
            LOGGER.debug("Send event: %s, pressed_buttons: '%s'", event_id, json.dumps(pressed_buttons))
            
            self.hass.bus.fire(
                event_id,
                {
                    "id": event_id,
                    "switch_address": switch_address,
                    "pressed_buttons": pressed_buttons,
                    "pressed": pressed,
                    "two_buttons_pressed": two_buttons_pressed,
                    "rocker_first_action": decoded.rocker_first_action,
                    "rocker_second_action": decoded.rocker_second_action,
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
            # learn button: 0=pressed, 1=not pressed
            if decoded.learn_button == 0:
                return
            
            # contact: 0=open, 1=closed
            if not self.invert_signal:
                self._attr_is_on = decoded.contact == 0
            else:
                self._attr_is_on = decoded.contact == 1 

            self.schedule_update_ha_state()
        elif self._dev_eep in [A5_08_01]:
            if decoded.learn_button == 1:
                return
                
            self._attr_is_on = decoded.pir_status == 1
            
            self.schedule_update_ha_state()

