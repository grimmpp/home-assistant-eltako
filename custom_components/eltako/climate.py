"""Support for Eltako Temperature Control sources."""
from __future__ import annotations

import math
from typing import Any

import asyncio
import time

from eltakobus.util import AddressExpression, b2a
from eltakobus.eep import *
from eltakobus.message import ESP2Message

from homeassistant.components.climate import (
    ClimateEntity,
    HVACAction,
    HVACMode,
    ClimateEntityFeature
)
from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_NAME, Platform, TEMP_CELSIUS, CONF_TEMPERATURE_UNIT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .gateway import EltakoGateway
from .device import *
from .const import *

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako Temperature Control platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway: EltakoGateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoEntity] = []
    
    if Platform.CLIMATE in config:
        for entity_config in config[Platform.CLIMATE]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            eep_string = entity_config.get(CONF_EEP)
            temp_unit = entity_config.get(CONF_TEMPERATURE_UNIT)
            max_temp = entity_config.get(CONF_MAX_TARGET_TEMPERATURE)
            min_temp = entity_config.get(CONF_MIN_TARGET_TEMPERATURE)
            
            sender_config = entity_config.get(CONF_SENDER)
            sender_id = AddressExpression.parse(sender_config.get(CONF_ID))
            sender_eep_string = sender_config.get(CONF_EEP)

            thermostat_sender_id = None
            thermostat_sender_eep_string = None
            thermostat_sender_eep = None
            if CONF_ROOM_THERMOSTAT in entity_config.keys():
                thermostat_sender_id = AddressExpression.parse(entity_config.get(CONF_ROOM_THERMOSTAT).get(CONF_ID))
                thermostat_sender_eep_string = entity_config.get(CONF_ROOM_THERMOSTAT).get(CONF_EEP)


            cooling_switch_id = None
            cooling_switch_button = None
            cooling_sender_id = None
            cooling_sender_eep_string = None
            cooling_sender_eep = None
            if CONF_COOLING_MODE in entity_config.keys():
                LOGGER.debug("[Climate] Read cooling switch config")
                # cooling_switch_id = AddressExpression.parse(entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_ID))
                cooling_switch_id = entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_ID)
                cooling_switch_button = entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_SWITCH_BUTTON)

                if CONF_SENDER in entity_config.get(CONF_COOLING_MODE).keys():
                    LOGGER.debug("[Climate] Read cooling sender config")
                    cooling_sender_id = AddressExpression.parse(entity_config.get(CONF_COOLING_MODE).get(CONF_SENDER).get(CONF_ID))
                    cooling_sender_eep_string = entity_config.get(CONF_COOLING_MODE).get(CONF_SENDER).get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
                sender_eep = EEP.find(sender_eep_string)
                if thermostat_sender_eep_string: thermostat_sender_eep = EEP.find(thermostat_sender_eep_string)
                if cooling_sender_eep_string: cooling_sender_eep = EEP.find(cooling_sender_eep_string)
            except Exception as e:
                LOGGER.warning("[Climate] Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                LOGGER.critical(e, exc_info=True)
                continue
            else:
                if dev_eep in [A5_10_06]:
                    ###### This way it is decouple from the order how devices will be loaded.
                    climate_entity = ClimateController(gateway, dev_id, dev_name, dev_eep, 
                                                       sender_id, sender_eep, 
                                                       temp_unit, min_temp, max_temp, 
                                                       thermostat_sender_id, thermostat_sender_eep,
                                                       cooling_switch_id, cooling_switch_button,
                                                       cooling_sender_id, cooling_sender_eep)
                    entities.append(climate_entity)

                    # subscribe for cooling switch events
                    if cooling_switch_id is not None:
                        event_id = f"{EVENT_BUTTON_PRESSED}_{cooling_switch_id.upper()}"
                        hass.bus.async_listen(event_id, climate_entity.async_handle_event)

                        event_id = f"{EVENT_CONTACT_CLOSED}_{cooling_switch_id.upper()}"
                        hass.bus.async_listen(event_id, climate_entity.async_handle_event)

    validate_ids_of_climate(entities)
    log_entities_to_be_added(entities, Platform.CLIMATE)
    async_add_entities(entities)


def validate_ids_of_climate(entities:[EltakoEntity]):
    for e in entities:
        e.validate_dev_id()
        e.validate_sender_id()
        if hasattr(e, "cooling_sender_id"):
            e.validate_sender_id(e.cooling_sender_id)
class ClimateController(EltakoEntity, ClimateEntity):
    """Representation of an Eltako heating and cooling actor."""

    _update_frequency = 55 # sec
    _actuator_mode: A5_10_06.Heater_Mode = None
    _hvac_mode_from_heating = HVACMode.HEAT

    COOLING_SWITCH_SIGNAL_FREQUENCY_IN_MIN: int = 15 # FTS14EM signals are repeated every 15min

    _attr_hvac_action = None
    _attr_hvac_mode = HVACMode.OFF
    _attr_fan_mode = None
    _attr_fan_modes = None
    _attr_is_aux_heat = None
    _attr_preset_mode = None
    _attr_preset_modes = None
    _attr_swing_mode = None
    _attr_swing_modes = None
    _attr_current_temperature = 0
    _attr_target_temperature = 0
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE


    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, 
                 sender_id: AddressExpression, sender_eep: EEP, 
                 temp_unit, min_temp: int, max_temp: int, 
                 thermostat_sender_id: AddressExpression=None, thermostat_eep: EEP=None,
                 cooling_switch_id:str=None, cooling_switch_button:int=0,
                 cooling_sender_id: AddressExpression=None, cooling_sender_eep: EEP=None):
        """Initialize the Eltako heating and cooling source."""
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"climate.{self.unique_id}"

        self.thermostat_id = thermostat_sender_id
        self.thermostat_eep = thermostat_eep
        if thermostat_sender_id:
            self.listen_to_addresses.append(thermostat_sender_id)

        self.cooling_switch_id = None
        self.cooling_switch_id_string = cooling_switch_id
        self.cooling_switch_button = cooling_switch_button
        self.cooling_switch_last_signal_timestamp = 0

        if cooling_switch_id is not None:
            try:
                self.cooling_switch_id = AddressExpression.parse(self.cooling_switch_id_string)
                self.listen_to_addresses.append(self.cooling_switch_id)
            except Exception as e:
                LOGGER.error(e)

        self._cooling_sender_id = cooling_sender_id
        
        if self.cooling_switch_id_string:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
        else:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

        self._attr_temperature_unit = temp_unit
        # self._attr_target_temperature_high = max_temp
        # self._attr_target_temperature_low = min_temp
        self._attr_max_temp = max_temp
        self._attr_min_temp = min_temp

        self._loop = asyncio.get_event_loop()
        self._update_task = asyncio.ensure_future(self._wrapped_update(), loop=self._loop)


    async def _wrapped_update(self, *args) -> None:
        while True:    
            try:
                # LOGGER.debug(f"[climate {self.dev_id}] Wait {self._update_frequency}s for next status update.")
                await asyncio.sleep(self._update_frequency)
                
                # fakes physical switch and sends frequently in cooling state.
                if self.cooling_switch_id:
                    await self._async_check_if_cooling_is_activated()
                    
                    await self._async_send_mode_cooling()

                # send frequently status update if not connected with thermostat. 
                if self.thermostat_id is None:
                    await self._async_send_command(self._actuator_mode, self.target_temperature)
                
            except Exception as e:
                LOGGER.exception(e)
                # FIXME should I just restart with back-off?


    @property
    def name(self):
        """Return the name of the device if any."""
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
            model=self.dev_eep.eep_string,
            via_device=(DOMAIN, self.gateway.unique_id),
        )
    
    async def async_handle_event(self, call):
        """Receives signal from cooling switches if defined in configuration."""
        # LOGGER.debug(f"[climate {self.dev_id}] Event received: {call.data}")

        if call.data['id'].startswith(EVENT_BUTTON_PRESSED):
            if (call.data['pressed'] or call.data['two_buttons_pressed']) and call.data['data'] == self.cooling_switch_button:
                LOGGER.debug(f"[climate {self.dev_id}] Cooling Switch {call.data['switch_address']} for button {hex(call.data['data'])} timestamp set.")
                self.cooling_switch_last_signal_timestamp = time.time()
        elif call.data['id'].startswith(EVENT_CONTACT_CLOSED):
            LOGGER.debug(f"[climate {self.dev_id}] Cooling Switch {call.data['switch_address']} timestamp set.")
            self.cooling_switch_last_signal_timestamp = time.time()

        await self._async_check_if_cooling_is_activated()


    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode on the panel."""

        # We use off button as toggle switch
        if hvac_mode == HVACMode.OFF:
            if hvac_mode != self.hvac_mode:
                self._send_mode_off()

            # when cooling is active swtich from off to cooling
            elif self._get_mode() == HVACMode.COOL:
                await self.async_set_hvac_mode(HVACMode.COOL)

            # when heating is actice swtich from off to heating
            else:
                await self.async_set_hvac_mode(HVACMode.HEAT)
            
        # mode can only be selected when active. e.g. heating can be selected if in heating mode. cooling would be inactive. cooling and heating mode needs to be switched via rocker swtich.
        elif hvac_mode == self._get_mode():
            self._attr_hvac_mode = hvac_mode
            self._send_set_normal_mode()


    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""

        if self._actuator_mode != None and self.current_temperature > 0:
            new_target_temp = kwargs['temperature']

            if self._actuator_mode == A5_10_06.Heater_Mode.OFF:
                self._actuator_mode = A5_10_06.Heater_Mode.NORMAL

            self._send_command(self._actuator_mode, new_target_temp)
        else:
            LOGGER.debug(f"[climate {self.dev_id}] default state of actor was not yet transferred.")


    async def _async_send_command(self, mode: A5_10_06.Heater_Mode, target_temp: float) -> None:
        """Send command to set target temperature."""
        self._send_command(mode, target_temp)

    def _send_command(self, mode: A5_10_06.Heater_Mode, target_temp: float) -> None:
        """Send command to set target temperature."""
        address, _ = self._sender_id
        if self.current_temperature and self.target_temperature:
            LOGGER.debug(f"[climate {self.dev_id}] Send status update: current temp: {target_temp}, mode: {mode}")
            msg = A5_10_06(mode, target_temp, self.current_temperature, self.hvac_action == HVACAction.IDLE).encode_message(address)
            self.send_message(msg)
        else:
            LOGGER.debug(f"[climate {self.dev_id}] Either no current or target temperature is set. Waiting for status update.")
            #This is always the case when there was no sensor signal after HA started.


    def _send_set_normal_mode(self) -> None:
        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: Normal")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x70', True))


    def _send_mode_off(self) -> None:
        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: OFF")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x10', True))


    def _send_mode_night(self) -> None:
        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: Night")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x50', True))


    def _send_mode_setback(self) -> None:
        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: Temperature Setback")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x30', True))


    async def _async_send_mode_cooling(self) -> None:
        """fake physical switch and send cooling status."""
        if self._cooling_sender_id:
            LOGGER.debug(f"[climate {self.dev_id}] Send command for cooling")
            address, _ = self._cooling_sender_id
            self.send_message(RPSMessage(address, 0x30, b'\x50', True))


    def _get_mode(self) -> HVACMode:

        # if no cooling switch is define return mode from config
        if self.cooling_switch_id_string is None:
            return self._hvac_mode_from_heating 

        # does cooling signal stays within the time range?
        else:
            # LOGGER.debug(f"[climate {self.dev_id}] Cooling mode switch last_received_signal:{self.cooling_switch_last_signal_timestamp}")
            if (time.time() - self.cooling_switch_last_signal_timestamp) / 60.0 <= self.COOLING_SWITCH_SIGNAL_FREQUENCY_IN_MIN:
                LOGGER.debug(f"[climate {self.dev_id}] Cooling mode is active.")
                return HVACMode.COOL
        
        # is cooling signal timed out?
        return HVACMode.HEAT
    

    async def _async_check_if_cooling_is_activated(self) -> None:
        # LOGGER.debug(f"[climate {self.dev_id}] Check if cooling switch is activated.")
        new_mode = self._get_mode()
        if new_mode != self._hvac_mode_from_heating:
            self._hvac_mode_from_heating = new_mode
            await self.async_set_hvac_mode(self._hvac_mode_from_heating)

        LOGGER.debug(f"[climate {self.dev_id}] {new_mode} mode is activated.")


    def value_changed(self, msg: ESP2Message) -> None:
        """Update the internal state of this device."""

        climate_address, _ = self.dev_id
        if msg.address == climate_address:
            LOGGER.debug(f"[climate {self.dev_id}] Change state triggered by actuator: {self.dev_id}")
            self.change_temperature_values(msg)

        if self.thermostat_id:
            thermostat_address, _ = self.thermostat_id
            if msg.address == thermostat_address:
                LOGGER.debug(f"[climate {self.dev_id}] Change state triggered by thermostat: {self.thermostat_id}")
                self.change_temperature_values(msg)

        if self.cooling_switch_id:
            cooling_switch_address, _ = self.cooling_switch_id
            if msg.address == cooling_switch_address:
                LOGGER.debug(f"[climate {self.dev_id}] Change mode triggered by cooling switch: {cooling_switch_address}")
                LOGGER.debug(f"NOT YET IMPLEMENTED");


    def change_temperature_values(self, msg: ESP2Message) -> None:
        try:
            if  msg.org == 0x07:
                decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning(f"[climate {self.dev_id}] Could not decode message: %s", str(e))
            return

        if  msg.org == 0x07 and self.dev_eep in [A5_10_06]:

            self._actuator_mode = decoded.mode
            self._attr_current_temperature = decoded.current_temperature

            if decoded.mode == A5_10_06.Heater_Mode.OFF:
                self._attr_hvac_mode = HVACMode.OFF
            elif decoded.mode == A5_10_06.Heater_Mode.NORMAL:
                self._attr_hvac_mode = self._hvac_mode_from_heating
            elif decoded.mode == A5_10_06.Heater_Mode.STAND_BY_2_DEGREES:
                self._attr_hvac_mode = self._hvac_mode_from_heating

            if decoded.mode != A5_10_06.Heater_Mode.OFF:
                # show target temp in 0.5 steps
                self._attr_target_temperature =  round( 2*decoded.target_temperature, 0)/2 

        self.schedule_update_ha_state()