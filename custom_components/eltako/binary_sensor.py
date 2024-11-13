"""Support for Eltako binary sensors."""
from __future__ import annotations
from typing import Dict

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICE_CLASS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType

import time

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

    LAST_RECEIVED_TELEGRAMS:Dict[str,Dict] = {}

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

        telegram_received_time = time.time()

        event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_BUTTON_PRESSED, msg.address)
        event_data = {
            "id": event_id,
            "entity_id": self.entity_id,
            "data": int.from_bytes(msg.data, "big"),
            "eep": self.dev_eep.eep_string,
            "switch_address": b2s(msg.address),
            "pressed_buttons": [],
            "prev_pressed_buttons": [],
            "pressed": False,
            "two_buttons_pressed": False,
            "rocker_first_action": None,
            "rocker_second_action": None,
            "push_telegram_received_time_in_sec": telegram_received_time,
            "release_telegram_received_time_in_sec": -1, 
            "push_duration_in_sec": -1,
        }


        # wall switches
        if self.dev_eep in [F6_02_01, F6_02_02]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id), self.dev_eep.eep_string)
            pressed_buttons = []
            pressed = decoded.energy_bow == 1
            two_buttons_pressed = decoded.second_action == 1
            fa = decoded.rocker_first_action
            sa = decoded.rocker_second_action

            push_telegram_received_time = telegram_received_time
            release_telegram_received_time = -1
            pushed_duration = -1

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

            # fire first event for the entire switch
            event_data.update({
                "pressed_buttons": pressed_buttons,
                "pressed": pressed or two_buttons_pressed,
                "two_buttons_pressed": two_buttons_pressed,
                "rocker_first_action": decoded.rocker_first_action,
                "rocker_second_action": decoded.rocker_second_action,
            })
            

            # send event id containing button positions
            # event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_BUTTON_PRESSED, msg.address, '-'.join(prev_pressed_buttons+pressed_buttons))
            # event_data['id'] = event_id
            # LOGGER.debug("[%s %s] Send event: %s, pressed_buttons: '%s'", Platform.BINARY_SENSOR, str(self.dev_id), event_id, json.dumps(prev_pressed_buttons+pressed_buttons))
            # self.hass.bus.fire(event_id, event_data)


            # Show status change in HA. It will only for the moment when the button is pushed down.
            # Change first button status so that automations can request it after event was fired.
            # != is XOR
            self._attr_is_on = self.invert_signal != (len(pressed_buttons) > 0)
        
        # switch / single button
        elif self.dev_eep in [F6_01_01]:

            # extend event data
            event_data['pressed'] = decoded.button_pushed
                
            # Show status change in HA. It will only for the moment when the button is pushed down.
            self._attr_is_on = self.invert_signal != ( decoded.button_pushed )
            self.schedule_update_ha_state()

            return

        elif self.dev_eep in [F6_10_00]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id), self.dev_eep.eep_string)
            event_data['pressed'] = decoded.handle_position == 0

            # is_on == True => open
            self._attr_is_on = self.invert_signal != (decoded.handle_position > 0)

        elif self.dev_eep in [D5_00_01]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id), self.dev_eep.eep_string)
            # learn button: 0=pressed, 1=not pressed
            if decoded.learn_button == 0:
                return
            
            event_data['pressed'] = decoded.contact == 1
            
            self._attr_is_on = self.invert_signal != decoded.contact == 1

        elif self.dev_eep in [A5_08_01]:
            # Occupancy Sensor
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id), self.dev_eep.eep_string)
            if decoded.learn_button == 0:
                return
                
            event_data['pressed'] = decoded.pir_status == 1

            self._attr_is_on = self.invert_signal != decoded.pir_status == 1

        elif self.dev_eep in [A5_07_01]:
            # LOGGER.debug("[Binary Sensor][%s] Received msg for processing eep %s telegram.", b2s(self.dev_id), self.dev_eep.eep_string)

            event_data['pressed'] = decoded.pir_status == 1

            self._attr_is_on = self.invert_signal != decoded.pir_status_on == 1

        elif self.dev_eep in [A5_30_01]:

            if self.description_key == "low_battery":
                event_data['pressed'] = decoded.low_battery
                self._attr_is_on = self.invert_signal != decoded.low_battery
            else:
                event_data['pressed'] = decoded._contact_closed
                self._attr_is_on = self.invert_signal != decoded._contact_closed


        elif self.dev_eep in [A5_30_03]:

            if self.description_key == "0":
                if decoded.digital_input_0:
                    event_data['pressed_buttons'] = [self.description_key]
                    event_data['pressed'] = True
                self._attr_is_on = self.invert_signal != decoded.digital_input_0

            elif self.description_key == "1":
                if decoded.digital_input_1:
                    event_data['pressed_buttons'] = [self.description_key]
                    event_data['pressed'] = True
                self._attr_is_on = self.invert_signal != decoded.digital_input_1

            elif self.description_key == "2":
                if decoded.digital_input_2:
                    event_data['pressed_buttons'] = [self.description_key]
                    event_data['pressed'] = True
                self._attr_is_on = self.invert_signal != decoded.digital_input_2

            elif self.description_key == "3":
                if decoded.digital_input_3:
                    event_data['pressed_buttons'] = [self.description_key]
                    event_data['pressed'] = True
                self._attr_is_on = self.invert_signal != decoded.digital_input_3

            elif self.description_key == "wake":
                if decoded.status_of_wake:
                    event_data['pressed_buttons'] = [self.description_key]
                    event_data['pressed'] = True
                self._attr_is_on = self.invert_signal != decoded.status_of_wake
            else:
                raise Exception("[%s %s] EEP %s Unknown description key for A5-30-03", Platform.BINARY_SENSOR, str(self.dev_id), A5_30_03.eep_string)

        else:
            LOGGER.warning("[%s %s] EEP %s not found for data processing.", Platform.BINARY_SENSOR, str(self.dev_id), self.dev_eep.eep_string)
            return
        
        self.schedule_update_ha_state()

        # prepare event data
        LOGGER.debug("Fire event for binary sensor.")
        event_data['is_on'] = self.is_on
        prev_pressed_buttons = self.LAST_RECEIVED_TELEGRAMS.get( b2s(self.dev_id), {'pressed_buttons':[]})['pressed_buttons']
        if event_data['pressed_buttons'] == [] and prev_pressed_buttons != []:
            event_data['prev_pressed_buttons'] = prev_pressed_buttons
        # when button released
        if not event_data['pressed']:
            push_telegram_received_time = self.LAST_RECEIVED_TELEGRAMS[ b2s(self.dev_id), {'push_telegram_received_time_in_sec': -1}]['push_telegram_received_time_in_sec']
            release_telegram_received_time = telegram_received_time
            pushed_duration = float(release_telegram_received_time - push_telegram_received_time)

            if push_telegram_received_time == -1:
                raise Exception(f"[{Platform.BINARY_SENSOR} {b2(self.dev_id)}] EEP {self.dev_eep.eep_string}: No information about previouse event.")
        
            event_data.update({
                "push_telegram_received_time_in_sec": push_telegram_received_time,
                "release_telegram_received_time_in_sec": release_telegram_received_time, 
                "push_duration_in_sec": pushed_duration,
            })

        self.LAST_RECEIVED_TELEGRAMS[b2s(self.dev_id)] = event_data
        self.hass.bus.fire(event_id, event_data)

class GatewayConnectionState(AbstractBinarySensor):
    """Protocols last time when message received"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        key = "Gateway_Connection_State"

        self._attr_icon = "mdi:connection"
        self._attr_name = "Connected"
        
        super().__init__(platform, gateway, gateway.base_id, dev_name="Connected", description_key=key)
        self.gateway.add_connection_state_changed_handler(self.async_value_changed)

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