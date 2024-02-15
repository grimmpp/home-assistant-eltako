"""Support for Eltako Temperature Control sources."""
from __future__ import annotations

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
from homeassistant.const import Platform, CONF_TEMPERATURE_UNIT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .gateway import EnOceanGateway
from .device import *
from .const import *
from .config_helpers import DeviceConf
from . import config_helpers, get_gateway_from_hass, get_device_config_for_gateway

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako Temperature Control platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.CLIMATE
    if platform in config:
        for entity_config in config[platform]:
            
            try:
                dev_conf = DeviceConf(entity_config, [CONF_TEMPERATURE_UNIT, CONF_MAX_TARGET_TEMPERATURE, CONF_MIN_TARGET_TEMPERATURE])
                sender = config_helpers.get_device_conf(entity_config, CONF_SENDER)
                thermostat = config_helpers.get_device_conf(entity_config, CONF_ROOM_THERMOSTAT)

                cooling_switch = None
                cooling_sender = None
                if CONF_COOLING_MODE in config.keys():
                    LOGGER.debug("[Climate] Read cooling switch config")
                    cooling_switch = config_helpers.get_device_conf(entity_config.get(CONF_COOLING_MODE), CONF_SENSOR [CONF_SWITCH_BUTTON])
                    LOGGER.debug("[Climate] Read cooling sender config")
                    cooling_sender = config_helpers.get_device_conf(entity_config.get(CONF_COOLING_MODE), CONF_SENDER)

                if dev_conf.eep in [A5_10_06]:
                    ###### This way it is decouple from the order how devices will be loaded.
                    climate_entity = ClimateController(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, 
                                                       sender.id, sender.eep, 
                                                       dev_conf.get(CONF_TEMPERATURE_UNIT), 
                                                       dev_conf.get(CONF_MIN_TARGET_TEMPERATURE), dev_conf.get(CONF_MAX_TARGET_TEMPERATURE), 
                                                       thermostat, cooling_switch, cooling_sender)
                    entities.append(climate_entity)

                    # subscribe for cooling switch events
                    if cooling_switch is not None:
                        event_id = config_helpers.get_bus_event_type(gateway.base_id, EVENT_BUTTON_PRESSED, cooling_switch.id, 
                                                                     config_helpers.convert_button_pos_from_hex_to_str(cooling_switch.get(CONF_SWITCH_BUTTON)))
                        LOGGER.debug(f"Subscribe for listening to cooling switch events: {event_id}")
                        hass.bus.async_listen(event_id, climate_entity.async_handle_event)

            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)
                continue

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


def validate_ids_of_climate(entities:list[EltakoEntity]):
    for e in entities:
        e.validate_dev_id()
        e.validate_sender_id()
        if hasattr(e, "cooling_sender_id"):
            e.validate_sender_id(e.cooling_sender_id)
class ClimateController(EltakoEntity, ClimateEntity, RestoreEntity):
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


    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, 
                 sender_id: AddressExpression, sender_eep: EEP, 
                 temp_unit, min_temp: int, max_temp: int, 
                 thermostat: DeviceConf, cooling_switch: DeviceConf, cooling_sender: DeviceConf):
        """Initialize the Eltako heating and cooling source."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep

        self.thermostat = thermostat
        if self.thermostat:
            self.listen_to_addresses.append(self.thermostat.id)

        self.cooling_switch = cooling_switch
        self.cooling_switch_last_signal_timestamp = 0

        self.cooling_sender = cooling_sender
        
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


    def load_value_initially(self, latest_state:State):
        # LOGGER.debug(f"[climate {self.dev_id}] eneity unique_id: {self.unique_id}")
        # LOGGER.debug(f"[climate {self.dev_id}] latest state - state: {latest_state.state}")
        # LOGGER.debug(f"[climate {self.dev_id}] latest state - attributes: {latest_state.attributes}")

        try:
            self.hvac_modes = []
            for m_str in latest_state.attributes.get('hvac_modes', []):
                for m_enum in HVACMode:
                    if m_str == m_enum.value:
                        self.hvac_modes.append(m_enum)

            self._attr_current_temperature = float(latest_state.attributes.get('current_temperature', None) )
            self._attr_target_temperature = float(latest_state.attributes.get('temperature', None) )

            if 'unknown' == latest_state.state:
                self._attr_hvac_mode = None
            else:
                for m_enum in HVACMode:
                    if latest_state.state == m_enum.value:
                        self._attr_hvac_mode = m_enum
                        break
                
        except Exception as e:
            self._attr_hvac_mode = None
            self._attr_current_temperature = None
            self._attr_target_temperature = None
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[climate {self.dev_id}] value initially loaded: [state: {self.state}, modes: [{self.hvac_modes}], current temp: {self.current_temperature}, target temp: {self.target_temperature}]")


    async def _wrapped_update(self, *args) -> None:
        while True:    
            try:
                # LOGGER.debug(f"[climate {self.dev_id}] Wait {self._update_frequency}s for next status update.")
                await asyncio.sleep(self._update_frequency)
                
                # fakes physical switch and sends frequently in cooling state.
                if self.cooling_switch:
                    await self._async_check_if_cooling_is_activated()
                    
                    await self._async_send_mode_cooling()

                # send frequently status update if not connected with thermostat. 
                if self.thermostat is None:
                    await self._async_send_command(self._actuator_mode, self.target_temperature)
                
            except Exception as e:
                LOGGER.exception(e)
                # FIXME should I just restart with back-off?

    
    async def async_handle_event(self, call):
        """Receives signal from cooling switches if defined in configuration."""
        # LOGGER.debug(f"[climate {self.dev_id}] Event received: {call.data}")

        LOGGER.debug(f"[climate {self.dev_id}] Cooling Switch {call.data['switch_address']} for button {hex(call.data['data'])} timestamp set.")
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
        if self.cooling_sender:
            LOGGER.debug(f"[climate {self.dev_id}] Send command for cooling")
            self.send_message(RPSMessage(self.cooling_sender.id[0], 0x30, b'\x50', True))


    def _get_mode(self) -> HVACMode:

        # if no cooling switch is define return mode from config
        if self.cooling_switch is None:
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

        if self.thermostat:
            thermostat_address, _ = self.thermostat.id
            if msg.address == thermostat_address:
                LOGGER.debug(f"[climate {self.dev_id}] Change state triggered by thermostat: {self.thermostat.id}")
                self.change_temperature_values(msg)

        # Implemented via eventing: async_handle_event
        # if self.cooling_switch:
        #     if msg.address == self.cooling_switch.id[0]:
        #         LOGGER.debug(f"[climate {self.dev_id}] Change mode triggered by cooling switch: {self.cooling_switch.id[0]}")
        #         LOGGER.debug(f"NOT YET IMPLEMENTED")


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