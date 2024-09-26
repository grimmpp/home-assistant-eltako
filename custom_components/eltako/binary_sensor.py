"""Support for Eltako binary sensors."""
from __future__ import annotations

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_CLASS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType

from .device import *
from .const import *
from .gateway import EnOceanGateway
from .schema import CONF_EEP_SUPPORTED_BINARY_SENSOR
from . import config_helpers, get_gateway_from_hass, get_device_config_for_gateway

import json

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Binary Sensor platform for Eltako."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)
    
    entities: list[EltakoEntity] = []
    
    platform = Platform.BINARY_SENSOR

    for platform_id in [Platform.BINARY_SENSOR, Platform.SENSOR]:
        if platform_id in config:
            for entity_config in config[platform_id]:
                try:
                    dev_conf = config_helpers.DeviceConf(entity_config, [CONF_DEVICE_CLASS, CONF_INVERT_SIGNAL])
                    if dev_conf.eep.eep_string in CONF_EEP_SUPPORTED_BINARY_SENSOR:
                        if dev_conf.eep == A5_30_03:
                            name = "Digital Input 0"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="0", name=name) ))
                            name = "Digital Input 1"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="1", name=name) ))
                            name = "Digital Input 2"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="2", name=name) ))
                            name = "Digital Input 3"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="3", name=name) ))
                            name = "Status of Wake"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="wake", name=name) ))
                        elif dev_conf.eep == A5_30_01:
                            name = "Digital Input"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="0", name=name) ))
                            name = "Low Battery"
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL),
                                                                EntityDescription(key="low_battery", name=name) ))
                        else:
                            entities.append(EltakoBinarySensor(platform_id, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, 
                                                                dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_INVERT_SIGNAL)))

                except Exception as e:
                    LOGGER.warning("[%s] Could not load configuration for platform_id %s", platform, platform_id)
                    LOGGER.critical(e, exc_info=True)

    # is connection active sensor for gateway (serial connection)
    entities.append(GatewayConnectionState(platform, gateway))

    # dev_id validation not possible because there can be bus sensors as well as decentralized sensors.
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)

    
class AbstractBinarySensor(EltakoEntity, RestoreEntity, BinarySensorEntity):

    def load_value_initially(self, latest_state:State):
        try:
            if 'unknown' == latest_state.state:
                self._attr_is_on = None
            else:
                if latest_state.state in ['on', 'off']:
                    self._attr_is_on = 'on' == latest_state.state
                else:
                    self._attr_is_on = None
                
        except Exception as e:
            self._attr_is_on = None
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[{Platform.BINARY_SENSOR} {self.dev_id}] value initially loaded: [is_on: {self.is_on}, state: {self.state}]")

class EltakoBinarySensor(AbstractBinarySensor):
    """Representation of Eltako binary sensors such as wall switches.

    Supported EEPs (EnOcean Equipment Profiles):
    - F6-02-01 (Light and Blind Control - Application Style 2)
    - F6-02-02 (Light and Blind Control - Application Style 1)
    - F6-10-00
    - D5-00-01
    """

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name:str, dev_eep: EEP, 
                 device_class: str, invert_signal: bool, description: EntityDescription=None):
        """Initialize the Eltako binary sensor."""
        if description:
            self.entity_description = EntityDescription(
                key=description.key,
                name=description.name
                )
            self._channel = description.key
        else:
            self._channel = None

        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, self._channel)
        self.invert_signal = invert_signal
        self._attr_device_class = device_class

        if device_class is None or device_class == '':
            if dev_eep in [A5_07_01, A5_08_01]:
                self._attr_device_class = BinarySensorDeviceClass.OCCUPANCY
                self._attr_icon = 'mdi:motion-sensor'
            if dev_eep in [D5_00_01]:
                self._attr_device_class = BinarySensorDeviceClass.WINDOW
            if dev_eep in [F6_10_00]:
                self._attr_device_class = BinarySensorDeviceClass.WINDOW
            

    def value_changed(self, msg: ESP2Message):
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
            decoded = self.dev_eep.decode_message(msg)
            LOGGER.debug("decoded : %s", json.dumps(decoded.__dict__))
            # LOGGER.debug("msg : %s, data: %s", type(msg), msg.data)
        except Exception as e:
            LOGGER.warning("[%s %s] Could not decode message for eep %s does not fit to message type %s (org %s)", 
                            Platform.BINARY_SENSOR, str(self.dev_id), self.dev_eep.eep_string, type(msg).__name__, str(msg.org) )
            return

        if self.dev_eep in [F6_02_01, F6_02_02]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id[0]), self.dev_eep.eep_string)
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

            # fire first event for the entire switch
            switch_address = config_helpers.format_address((msg.address, None))
            event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_BUTTON_PRESSED, AddressExpression((msg.address, None)))
            event_data = {
                    "id": event_id,
                    "data": int.from_bytes(msg.data, "big"),
                    "switch_address": switch_address,
                    "pressed_buttons": pressed_buttons,
                    "pressed": pressed,
                    "two_buttons_pressed": two_buttons_pressed,
                    "rocker_first_action": decoded.rocker_first_action,
                    "rocker_second_action": decoded.rocker_second_action,
                }
            
            LOGGER.debug("[%s %s] Send event: %s, pressed_buttons: '%s'", Platform.BINARY_SENSOR, str(self.dev_id), event_id, json.dumps(pressed_buttons))
            self.hass.bus.fire(event_id, event_data)

            # fire second event for a specific buttons pushed on the swtich
            event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_BUTTON_PRESSED, AddressExpression((msg.address, None)), '-'.join(pressed_buttons))
            event_data = {
                    "id": event_id,
                    "data": int.from_bytes(msg.data, "big"),
                    "switch_address": switch_address,
                    "pressed_buttons": pressed_buttons,
                    "pressed": pressed,
                    "two_buttons_pressed": two_buttons_pressed,
                    "rocker_first_action": decoded.rocker_first_action,
                    "rocker_second_action": decoded.rocker_second_action,
                }
            LOGGER.debug("[%s %s] Send event: %s, pressed_buttons: '%s'", Platform.BINARY_SENSOR, str(self.dev_id), event_id, json.dumps(pressed_buttons))
            self.hass.bus.fire(event_id, event_data)

            # Show status change in HA. It will only for the moment when the button is pushed down.
            if not self.invert_signal:
                self._attr_is_on = len(pressed_buttons) > 0
            else: 
                self._attr_is_on = not ( len(pressed_buttons) > 0 )
            self.schedule_update_ha_state()

            return
        
        elif self.dev_eep in [F6_01_01]:

            # fire event
            switch_address = config_helpers.format_address((msg.address, None))
            event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_BUTTON_PRESSED, AddressExpression((msg.address, None)))
            event_data = {
                    "id": event_id,
                    "data": int.from_bytes(msg.data, "big"),
                    "switch_address": switch_address,
                    "pressed": decoded.button_pushed,
                }
            LOGGER.debug("[%s %s] Send event: %s, pushed down: %s", Platform.BINARY_SENSOR, str(self.dev_id), event_id, str(decoded.button_pushed))
            self.hass.bus.fire(event_id, event_data)
            
            # Show status change in HA. It will only for the moment when the button is pushed down.
            if not self.invert_signal:
                self._attr_is_on = decoded.button_pushed
            else: 
                self._attr_is_on = not ( decoded.button_pushed )
            self.schedule_update_ha_state()

            return

        elif self.dev_eep in [F6_10_00]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id[0]), self.dev_eep.eep_string)
            
            # is_on == True => open
            self._attr_is_on = decoded.handle_position > 0

            if self.invert_signal:
                self._attr_is_on = not self._attr_is_on

        elif self.dev_eep in [D5_00_01]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id[0]), self.dev_eep.eep_string)
            # learn button: 0=pressed, 1=not pressed
            if decoded.learn_button == 0:
                return
            
            # contact: 0=open, 1=closed
            if not self.invert_signal:
                self._attr_is_on = decoded.contact == 0
            else:
                self._attr_is_on = decoded.contact == 1

        elif self.dev_eep in [A5_08_01]:
            # Occupancy Sensor
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id[0]), self.dev_eep.eep_string)
            if decoded.learn_button == 0:
                return
                
            self._attr_is_on = decoded.pir_status == 1

            if self.invert_signal:
                self._attr_is_on = not self._attr_is_on

        elif self.dev_eep in [A5_07_01]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id[0]), self.dev_eep.eep_string)

            self._attr_is_on = decoded.pir_status_on == 1

            if self.invert_signal:
                self._attr_is_on = not self._attr_is_on

        elif self.dev_eep in [A5_30_01]:

            if self.description_key == "low_battery":
                self._attr_is_on = decoded.low_battery
            else:
                self._attr_is_on = decoded._contact_closed

            if self.invert_signal:
                self._attr_is_on = not self._attr_is_on

        elif self.dev_eep in [A5_30_03]:

            if self.description_key == "0":
                self._attr_is_on = decoded.digital_input_0
            elif self.description_key == "1":
                self._attr_is_on = decoded.digital_input_1
            elif self.description_key == "2":
                self._attr_is_on = decoded.digital_input_2
            elif self.description_key == "3":
                self._attr_is_on = decoded.digital_input_3
            elif self.description_key == "wake":
                self._attr_is_on = decoded.status_of_wake
            else:
                raise Exception("[%s %s] EEP %s Unknown description key for A5-30-03", Platform.BINARY_SENSOR, str(self.dev_id), A5_30_03.eep_string)

            if self.invert_signal:
                self._attr_is_on = not self._attr_is_on

        else:
            LOGGER.warning("[%s %s] EEP %s not found for data processing.", Platform.BINARY_SENSOR, str(self.dev_id), self.dev_eep.eep_string)
            return
        
        self.schedule_update_ha_state()

        if self.is_on:
            LOGGER.debug("Fire event for binary sensor.")
            switch_address = config_helpers.format_address((msg.address, None))
            event_id = config_helpers.get_bus_event_type(self.gateway.base_id, EVENT_CONTACT_CLOSED, AddressExpression((msg.address, None)))
            self.hass.bus.fire(
                event_id,
                {
                    "id": event_id,
                    "contact_address": switch_address,
                    "is_on": self.is_on
                },
            )

class GatewayConnectionState(AbstractBinarySensor):
    """Protocols last time when message received"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        key = "Gateway_Connection_State"

        self._attr_icon = "mdi:connection"
        self._attr_name = "Connected"
        
        super().__init__(platform, gateway, gateway.base_id, dev_name="Connected", description_key=key)
        self.gateway.set_connection_state_changed_handler(self.async_value_changed)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway.serial_path)},
            name= self.gateway.dev_name,
            manufacturer=MANUFACTURER,
            model=self.gateway.model,
            via_device=(DOMAIN, self.gateway.serial_path)
        )
    
    async def async_value_changed(self, connected:bool) -> None:
        try:
            self.value_changed(connected)
        except AttributeError as e:
            # Home Assistant is not ready yet
            pass
    
    def value_changed(self, connected: bool) -> None:
        """Update the current value."""
        LOGGER.debug("[%s] [Gateway Id %s] connected %s", Platform.BINARY_SENSOR, str(self.gateway.dev_id), str(connected) )

        self._attr_is_on = connected
        self.schedule_update_ha_state()