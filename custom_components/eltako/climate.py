"""Support for Eltako Temperature Control sources."""
from __future__ import annotations

import asyncio
import time

from eltakobus.util import AddressExpression, b2s
from eltakobus.eep import *
from eltakobus.message import ESP2Message

from homeassistant.components.climate import (
    ClimateEntity,
    HVACAction,
    HVACMode,
    ClimateEntityFeature,
    PRESET_SLEEP,
    PRESET_HOME,
    PRESET_ECO
)
from homeassistant import config_entries
from homeassistant.const import Platform, CONF_TEMPERATURE_UNIT, Platform
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_state_change_event

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
                room_sensor_entity_id = entity_config.get(CONF_ROOM_SENSOR)
                off_temperature = entity_config.get(CONF_OFF_TEMPERATURE)

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
                                                       thermostat, cooling_switch, cooling_sender,
                                                       dev_conf.area,
                                                       room_sensor_entity_id, off_temperature)
                    entities.append(climate_entity)

                    # subscribe for cooling switch events
                    if cooling_switch is not None:
                        event_id = config_helpers.get_bus_event_type(gateway.dev_id, EVENT_BUTTON_PRESSED, cooling_switch.id,
                                                                     config_helpers.convert_button_pos_from_hex_to_str(cooling_switch.get(CONF_SWITCH_BUTTON)))
                        LOGGER.debug(f"Subscribe for listening to cooling switch events: {event_id}")
                        hass.bus.async_listen(event_id, climate_entity.async_handle_cooling_switch_event)

                    # subscribe for prio config — only meaningful when a physical thermostat is wired up
                    if thermostat is not None:
                        event_id = config_helpers.get_bus_event_type(gateway.base_id, EVENT_CLIMATE_PRIORITY_SELECTED, dev_conf.id)
                        LOGGER.debug(f"Subscribe for listening to priority change events: {event_id}")
                        hass.bus.async_listen(event_id, climate_entity.async_handle_priority_events)

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
    _attr_actuator_mode: A5_10_06.HeaterMode = None
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
    _attr_current_temperature = None
    _attr_target_temperature = None
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    _attr_preset_modes = [PRESET_HOME, # normal mode
                            PRESET_SLEEP, # night set back -4°K
                            PRESET_ECO # -2°K
                            ]   
    _attr_preset_mode = PRESET_HOME


    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP,
                 sender_id: AddressExpression, sender_eep: EEP,
                 temp_unit, min_temp: int, max_temp: int,
                 thermostat: DeviceConf, cooling_switch: DeviceConf, cooling_sender: DeviceConf, dev_area: str=None,
                 room_sensor_entity_id: str=None, off_temperature: float=None):
        """Initialize the Eltako heating and cooling source."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, dev_area=dev_area)
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self.off_temperature = off_temperature
        self._last_on_temp = None

        self.thermostat = thermostat
        if self.thermostat:
            self.listen_to_addresses.append(self.thermostat.id)

        self.room_sensor_entity_id = room_sensor_entity_id
        self._room_sensor_temp = None

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
        # Many A5-10-06 actuators (FTR65HS, FTAF65D, FTR86B, FUTH65D, FUTH55D) only honor
        # priority byte 0x0F (ACTUATOR_ACK). Use it when there is no physical thermostat
        # so commands from HA actually reach the heater.
        if self.thermostat is None:
            self._attr_priority = A5_10_06.ControllerPriority.ACTUATOR_ACK
        else:
            self._attr_priority = A5_10_06.ControllerPriority.AUTO
        self._attr_actuator_mode = A5_10_06.HeaterMode.NORMAL

        # self._loop = asyncio.get_event_loop()
        # self._update_task = asyncio.ensure_future(self._wrapped_update(), loop=self._loop)


    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        if self.room_sensor_entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self.room_sensor_entity_id], self._async_room_sensor_changed
                )
            )
            # seed an initial current temperature from the sensor's existing state
            state = self.hass.states.get(self.room_sensor_entity_id)
            if state and state.state not in ["unknown", "unavailable"]:
                try:
                    self._room_sensor_temp = float(state.state)
                    self._attr_current_temperature = self._room_sensor_temp
                except ValueError:
                    LOGGER.warning(f"[climate {self.dev_id}] Could not convert state {state.state} to float for {self.room_sensor_entity_id}")

    async def _async_room_sensor_changed(self, event: Event):
        """Handle room sensor state changes."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ["unknown", "unavailable"]:
            return

        try:
            self._room_sensor_temp = float(new_state.state)
            self._attr_current_temperature = self._room_sensor_temp

            if self._attr_actuator_mode is None:
                self._attr_actuator_mode = A5_10_06.HeaterMode.NORMAL

            self._send_command(self._attr_actuator_mode, self.target_temperature, self._attr_priority)

            self.schedule_update_ha_state()
            LOGGER.debug(f"[climate {self.dev_id}] Room sensor {self.room_sensor_entity_id} changed to {self._room_sensor_temp}")
        except ValueError:
            LOGGER.warning(f"[climate {self.dev_id}] Could not convert state {new_state.state} to float for {self.room_sensor_entity_id}")


    def load_value_initially(self, latest_state:State):
        LOGGER.debug(f"[climate {self.dev_id}] eneity unique_id: {self.unique_id}")
        LOGGER.debug(f"[climate {self.dev_id}] latest state - state: {latest_state.state}")
        LOGGER.debug(f"[climate {self.dev_id}] latest state - attributes: {latest_state.attributes}")

        try:
            self.hvac_modes = []
            for m_str in latest_state.attributes.get('hvac_modes', []):
                for m_enum in HVACMode:
                    if m_str == m_enum.value:
                        self.hvac_modes.append(m_enum)

            self._attr_current_temperature = latest_state.attributes.get('current_temperature', None)
            self._attr_target_temperature = latest_state.attributes.get('temperature', self._attr_min_temp)
            self._attr_preset_mode = latest_state.attributes.get('preset_mode', None)

            self._attr_hvac_mode = HVACMode.OFF
            if latest_state.state is not None:
                for m_enum in HVACMode:
                    if latest_state.state == m_enum.value:
                        self._attr_hvac_mode = m_enum
                        break

        except Exception as e:
            self._attr_hvac_mode = None
            self._attr_current_temperature = None
            self._attr_target_temperature = None
            LOGGER.warning(f"[climate {self.dev_id}] Cannot restore last state '{latest_state.state}': {e}")

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
                    await self._async_send_command(self._attr_actuator_mode, self.target_temperature, self._attr_priority)
                
            except Exception as e:
                LOGGER.exception(e)
                # FIXME should I just restart with back-off?

    
    async def async_handle_cooling_switch_event(self, call):
        """Receives signal from cooling switches if defined in configuration."""
        # LOGGER.debug(f"[climate {self.dev_id}] Event received: {call.data}")

        LOGGER.debug(f"[climate {self.dev_id}] Cooling Switch {call.data['switch_address']} for button {hex(call.data['data'])} timestamp set.")
        self.cooling_switch_last_signal_timestamp = time.time()

        await self._async_check_if_cooling_is_activated()

    async def async_handle_priority_events(self, call):
        LOGGER.debug(f"[climate {self.dev_id}] Event received: {call.data}")

        self._attr_priority = A5_10_06.ControllerPriority.find_by_description(call.data['priority'])
        if self._attr_priority == A5_10_06.ControllerPriority.THERMOSTAT:
            self._send_command(A5_10_06.HeaterMode.UNKNOWN, 40, A5_10_06.ControllerPriority.HOME_AUTOMATION)   # send 00-00-00-08 to enable thermostat prio
        else:
            self._send_command(self._attr_actuator_mode, self.target_temperature, self._attr_priority)  # send temperature update with new prio
        

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

        new_target_temp = kwargs['temperature']
        LOGGER.debug(f"[climate {self.dev_id}] target temperature changed: to {new_target_temp} (Mode: {self._attr_actuator_mode})")

        if self._attr_actuator_mode in [None, A5_10_06.HeaterMode.OFF]:
            self._attr_actuator_mode = A5_10_06.HeaterMode.NORMAL

        self._attr_target_temperature = new_target_temp
        self._send_command(self._attr_actuator_mode, new_target_temp, self._attr_priority)
        self.schedule_update_ha_state()
        


    async def _async_send_command(self, mode: A5_10_06.HeaterMode, target_temp: float, priority:A5_10_06.ControllerPriority) -> None:
        """Send command to set target temperature."""
        self._send_command(mode, target_temp, priority)

    def _send_command(self, mode: A5_10_06.HeaterMode, target_temp: float, priority:A5_10_06.ControllerPriority) -> None:
        """Send command to set target temperature."""
        address, _ = self._sender_id
        if target_temp is not None and 0 <= target_temp <= 40:
            current_temp = 40
            if self._room_sensor_temp is not None:
                current_temp = self._room_sensor_temp

            LOGGER.debug(f"[climate {self.dev_id}] Send status update: target temp: {target_temp}, current temp: {current_temp}, mode: {mode}, priority: '{priority.description}'")
            msg = A5_10_06(mode, target_temp, current_temp=current_temp, priority=priority).encode_message(address)
            self.send_message(msg)
        else:
            LOGGER.debug(f"[climate {self.dev_id}] Either no current or target temperature is set. Waiting for status update.")
            #This is always the case when there was no sensor signal after HA started.


    def _send_set_normal_mode(self) -> None:
        # When off_temperature is configured, on/off is expressed by sending a target
        # temperature instead of RPS button telegrams (which the actuator cannot query back).
        if self.off_temperature is not None:
            target_temp = self._last_on_temp if self._last_on_temp else self._attr_min_temp
            self._attr_target_temperature = target_temp
            self._send_command(A5_10_06.HeaterMode.NORMAL, target_temp, self._attr_priority)
            self.schedule_update_ha_state()
            return

        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: Normal")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x70', True))


    def _send_mode_off(self) -> None:
        if self.off_temperature is not None:
            if self._attr_hvac_mode != HVACMode.OFF:
                self._last_on_temp = self.target_temperature
            self._attr_target_temperature = self.off_temperature
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF
            self._send_command(A5_10_06.HeaterMode.NORMAL, self.off_temperature, self._attr_priority)
            self.schedule_update_ha_state()
            return

        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: OFF")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x10', True))


    def _send_mode_night(self) -> None:
        if self.off_temperature is not None:
            return

        LOGGER.debug(f"[climate {self.dev_id}] Send signal to set mode: Night")
        address, _ = self._sender_id
        self.send_message(RPSMessage(address, 0x30, b'\x50', True))


    def _send_mode_setback(self) -> None:
        if self.off_temperature is not None:
            return

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

        if msg.address == self.dev_id[0] or msg.address == self._external_dev_id[0]:
            LOGGER.debug(f"[climate {self.dev_id}] Change state triggered by actuator: {self.dev_id}")
            self.change_temperature_values(msg)

        if self.thermostat:
            thermostat_address, _ = self.thermostat.id
            LOGGER.debug(f"thermostat address: {b2s(thermostat_address)}, message address: {b2s(msg.address)}")
            if msg.address == thermostat_address:
                LOGGER.debug(f"[climate {self.dev_id}] Change state triggered by thermostat: {self.thermostat.id}")
                self.change_temperature_values(msg)


    def _send_command_to_change_mode_(self):
        if self.hvac_mode != HVACMode.OFF:
            if self.preset_mode == PRESET_HOME:
                self._send_set_normal_mode()
            elif self.preset_mode == PRESET_ECO:
                self._send_mode_setback()
            elif self.preset_mode == PRESET_SLEEP:
                self._send_mode_night()
        else:
            self._send_mode_off()

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""

        self._attr_preset_mode = preset_mode
        self._send_command_to_change_mode_()


    def change_temperature_values(self, msg: ESP2Message) -> None:
        try:
            if msg.org == 0x07:
                decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning(f"[climate {self.dev_id}] Could not decode message: %s", str(e))
            return

        if  msg.org == 0x07 and self.dev_eep in [A5_10_06]:

            self._attr_actuator_mode = decoded.mode
            LOGGER.debug(f"Decoded mode: {decoded.mode}, target temp: {decoded.target_temperature}, current temp: {decoded.current_temperature}, priority: {decoded.priority.description}")
            self._attr_current_temperature = decoded.current_temperature

            if decoded.mode == A5_10_06.HeaterMode.OFF:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF
            else:
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_hvac_action = HVACAction.HEATING

            if decoded.mode == A5_10_06.HeaterMode.NORMAL:
                self._attr_preset_mode = PRESET_HOME
            elif decoded.mode == A5_10_06.HeaterMode.STAND_BY_2_DEGREES:
                self._attr_preset_mode = PRESET_ECO
            elif decoded.mode == A5_10_06.HeaterMode.NIGHT_SET_BACK_4_DEGREES:
                self._attr_preset_mode = PRESET_SLEEP

            if decoded.mode != A5_10_06.HeaterMode.OFF:
                # show target temp in 0.5 steps
                self._attr_target_temperature =  round( 2*decoded.target_temperature, 0)/2

            # When off_temperature is configured, reaching that target means the actuator is off.
            if self.off_temperature is not None and self._attr_target_temperature == self.off_temperature:
                self._attr_hvac_mode = HVACMode.OFF
                self._attr_hvac_action = HVACAction.OFF

        if msg.org == 0x05:
            heater_mode = A5_10_06.HeaterMode( int.from_bytes(msg.data, byteorder='big') )
            LOGGER.debug(f"[climate {self.dev_id}] Heater running in mode: {heater_mode} (data={b2s(msg.data)})")
            if A5_10_06.HeaterMode.OFF.value == msg.data:
                self._attr_hvac_mode = HVACMode.OFF
            else:
                self._attr_hvac_mode = HVACMode.HEAT
                self._attr_hvac_action = HVACAction.HEATING

                if A5_10_06.HeaterMode.NORMAL == heater_mode:
                    self._attr_preset_mode = PRESET_HOME                
                elif A5_10_06.HeaterMode.STAND_BY_2_DEGREES == heater_mode:
                    self._attr_preset_mode = PRESET_ECO
                elif A5_10_06.HeaterMode.NIGHT_SET_BACK_4_DEGREES == heater_mode:
                    self._attr_preset_mode = PRESET_SLEEP                

        LOGGER.debug(f"[climate {self.dev_id}] Change to hvac_mode: {self.hvac_mode}, preset_mode: {self.preset_mode}, hvac_action: {self.hvac_action}")
        self.schedule_update_ha_state()