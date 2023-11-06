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
from homeassistant.const import CONF_ID, CONF_NAME, Platform, TEMP_CELSIUS, CONF_TEMPERATURE_UNIT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .gateway import EltakoGateway
from .device import EltakoEntity
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

            cooling_switch_id = None
            cooling_switch_eep_string = None
            cooling_switch_eep = None
            cooling_sender_id = None
            cooling_sender_eep_string = None
            cooling_sender_eep = None
            if CONF_COOLING_MODE in entity_config.keys():
                LOGGER.debug("Read cooling switch config")
                cooling_switch_id = AddressExpression.parse(entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_ID))
                cooling_switch_eep_string = entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_EEP)
                switch_button = entity_config.get(CONF_COOLING_MODE).get(CONF_SENSOR).get(CONF_SWITCH_BUTTON)

                if CONF_SENDER in entity_config.get(CONF_COOLING_MODE).keys():
                    LOGGER.debug("Read cooling sender config")
                    cooling_sender_id = AddressExpression.parse(entity_config.get(CONF_COOLING_MODE).get(CONF_SENDER).get(CONF_ID))
                    cooling_sender_eep_string = entity_config.get(CONF_COOLING_MODE).get(CONF_SENDER).get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
                sender_eep = EEP.find(sender_eep_string)
                if cooling_switch_eep_string: cooling_switch_eep = EEP.find(cooling_switch_eep_string)
                if cooling_sender_eep_string: cooling_sender_eep = EEP.find(cooling_sender_eep_string)
            except Exception as e:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                LOGGER.critical(e, exc_info=True)
                continue
            else:
                if dev_eep in [A5_10_06]:
                    cooling_switch_entity = None
                    if cooling_switch_id:
                        cooling_switch_entity = CoolingSwitch(gateway, cooling_switch_id, 'cooling switch', cooling_switch_eep, switch_button)
                        entities.append(cooling_switch_entity)

                    climate_entity = ClimateController(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep, temp_unit, min_temp, max_temp, cooling_switch_entity, cooling_sender_id, cooling_sender_eep)
                    entities.append(climate_entity)

        
    for e in entities:
        LOGGER.debug(f"Add entity {e.dev_name} (id: {e.dev_id}, eep: {e.dev_eep}) of platform type {Platform.CLIMATE} to Home Assistant.")
    async_add_entities(entities)


class CoolingSwitch(EltakoEntity):
    last_cooling_signal: float = 0
    SENDER_FREQUENCY_IN_MIN: int = 15 # FTS14EM signals are repeated every 15min

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, button:int):
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self.button = button

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of this device."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning(f"[climate {self.dev_id}] Could not decode message: {str(e)}")
            LOGGER.debug(f"[climate {self.dev_id}] Message: {msg}")
            return

        if self.dev_eep in [M5_38_08]:
# 0x70 = top right
# 0x50 = bottom right
# 0x30 = top left
# 0x10 = bottom left            
            LOGGER.debug(f"[Cooling Switch {self.dev_id}] Received status: {decoded.state} and data {int.from_bytes(msg.data)} from button type {self.dev_eep.eep_string} type {type(msg.data)}")
            LOGGER.debug(f"[Cooling Switch {self.dev_id}] Button {hex(self.button)} defined for cooling mode. type {type(self.button)}")
            if self.button == int.from_bytes(msg.data):
                self.last_cooling_signal = time.time()
                LOGGER.debug(f"[Cooling Switch {self.dev_id}] Cooling mode signal received.")

        else:
            LOGGER.debug(f"[Cooling Switch {self.dev_id}] Received status: {decoded.state} and data {msg.data} from contact type {self.dev_eep.eep_string}")

            


    def is_cooling_mode_active(self):
        return (time.time() - self.last_cooling_signal) / 60.0 <= self.SENDER_FREQUENCY_IN_MIN   # time difference of last signal less than 16min


class ClimateController(EltakoEntity, ClimateEntity):
    """Representation of an Eltako heating and cooling actor."""

    _update_frequency = 50 # sec
    _actor_mode: A5_10_06.Heater_Mode = None
    _hvac_mode_from_heating = HVACMode.HEAT

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


    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP, temp_unit, min_temp: int, max_temp: int, cooling_switch: CoolingSwitch=None, cooling_sender_id: AddressExpression=None, cooling_sender_eep: EEP=None):
        """Initialize the Eltako heating and cooling source."""
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"climate.{self.unique_id}"

        self.cooling_switch = cooling_switch
        self._cooling_sender_id = cooling_sender_id
        self._cooling_sender_eep = cooling_sender_eep

        if self.cooling_switch:
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
                LOGGER.debug(f"[climate {self.dev_id}] Wait {self._update_frequency} sec for next status update.")
                await asyncio.sleep(self._update_frequency)
                
                LOGGER.debug(f"[climate {self.dev_id}] Send status update")
                await self._async_send_command(self._actor_mode, self.target_temperature)
                
                if self._get_mode() == HVACMode.COOL:
                    await self._async_send_mode_cooling()
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
    

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode on the panel."""
        LOGGER.info("async func")
        LOGGER.info(f"hvac_mode {hvac_mode}")
        LOGGER.info(f"self.hvac_mode {self.hvac_mode}")
        LOGGER.info(f"target temp {self.target_temperature}")
        LOGGER.info(f"current temp {self.current_temperature}")

        if hvac_mode == HVACMode.OFF:
            if hvac_mode != self.hvac_mode:
                self._send_mode_off()

            elif self._get_mode() == HVACMode.COOL:
                await self.async_set_hvac_mode(HVACMode.COOL)

            else:
                await self.async_set_hvac_mode(HVACMode.HEAT)
            
        elif hvac_mode == self._hvac_mode_from_heating:
            self._attr_hvac_mode = hvac_mode
            self._send_set_normal_mode()


    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        LOGGER.info("async func")
        LOGGER.info(f"hvac_mode {self.hvac_mode}")
        LOGGER.info(f"hvac_action {self.hvac_action}")
        LOGGER.info(f"target temp {self.target_temperature}")
        LOGGER.info(f"current temp {self.current_temperature}")
        LOGGER.info(f"kwargs {kwargs}")
        LOGGER.info(f"actor_mode {self._actor_mode}")

        if self._actor_mode != None and self.current_temperature > 0:
            new_target_temp = kwargs['temperature']

            if self._actor_mode == A5_10_06.Heater_Mode.OFF:
                self._actor_mode = A5_10_06.Heater_Mode.NORMAL

            self._send_command(self._actor_mode, new_target_temp)
        else:
            LOGGER.debug(f"[climate {self.dev_id}] default state of actor was not yet transferred.")

    def _send_command(self, mode: A5_10_06.Heater_Mode, target_temp: float) -> None:
        address, _ = self._sender_id
        if self._sender_eep == A5_10_06:
            if self.current_temperature and self.target_temperature:
                msg = A5_10_06(mode, target_temp, self.current_temperature, self.hvac_action == HVACAction.IDLE).encode_message(address)
                self.send_message(msg)
            else:
                LOGGER.debug(f"[climate {self.dev_id}] Either no current or target temperature is set.")
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
        if self._cooling_sender_id:
            LOGGER.debug(f"[climate {self.dev_id}] Send command for cooling:")
            address, _ = self._cooling_sender_id
            self.send_message(RPSMessage(address, 0x30, b'\x50', True))
            # Regular4BSMessage???

    async def _async_send_command(self, mode: A5_10_06.Heater_Mode, target_temp: float) -> None:
        self._send_command(mode, target_temp)


    def _get_mode(self) -> HVACMode:

        if self.cooling_switch and self.cooling_switch.is_cooling_mode_active():
            return HVACMode.COOL

        return HVACMode.HEAT


    def value_changed(self, msg: ESP2Message) -> None:
        """Update the internal state of this device."""
        try:
            if  msg.org == 0x07:
                decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning(f"[climate {self.dev_id}] Could not decode message: %s", str(e))
            return

        if  msg.org == 0x07 and self.dev_eep in [A5_10_06]:
            
            self._actor_mode = decoded.mode
            self._attr_current_temperature = decoded.current_temp

            if decoded.mode == A5_10_06.Heater_Mode.OFF:
                self._attr_hvac_mode = HVACMode.OFF
            elif decoded.mode == A5_10_06.Heater_Mode.NORMAL:
                self._attr_hvac_mode = self._hvac_mode_from_heating
            elif decoded.mode == A5_10_06.Heater_Mode.STAND_BY_2_DEGREES:
                self._attr_hvac_mode = self._hvac_mode_from_heating

            if decoded.mode != A5_10_06.Heater_Mode.OFF:
                self._attr_target_temperature = decoded.target_temp

        self.schedule_update_ha_state()
