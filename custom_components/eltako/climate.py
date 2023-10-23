"""Support for Eltako Temperature Control sources."""
from __future__ import annotations

import math
from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.climate import (
    ClimateEntity,
    HVACAction,
    HVACMode
)
from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_NAME, Platform, TEMP_CELSIUS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, CONF_SENDER, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG, ELTAKO_GATEWAY, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako Temperature Control platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoSensor] = []
    
    if Platform.CLIMATE in config:
        for entity_config in config[Platform.CLIMATE]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            eep_string = entity_config.get(CONF_EEP)
            
            sender_config = entity_config.get(CONF_SENDER)
            sender_id = AddressExpression.parse(sender_config.get(CONF_ID))
            sender_eep_string = sender_config.get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
                sender_eep = EEP.find(sender_eep_string)
            except Exception as e:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                LOGGER.critical(e, exc_info=True)
                continue
            else:
                if dev_eep in [A5_10_06]:
                    entities.append(ClimateController(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep))
        
    for e in entities:
        LOGGER.debug(f"Add entity {e.dev_name} (id: {e.dev_id}, eep: {e.dev_eep}) of platform type {Platform.CLIMATE} to Home Assistant.")
    async_add_entities(entities)


class ClimateController(EltakoEntity, ClimateEntity):
    """Representation of an Eltako heating and cooling actor."""

    _attr_hvac_action = HVACAction.OFF
    _attr_hvac_mode = HVACMode.HEAT
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.COOL]
    _attr_fan_mode = None
    _attr_fan_modes = None
    _attr_is_aux_heat = None
    _attr_preset_mode = None
    _attr_preset_modes = None
    _attr_swing_mode = None
    _attr_swing_modes = None
    _attr_target_temperature_high = 25
    _attr_target_temperature_low = 8
    _attr_temperature_unit = TEMP_CELSIUS

    def __init__(self, gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep):
        """Initialize the Eltako heating and cooling source."""
        super().__init__(gateway, dev_id, dev_name)
        self._dev_eep = dev_eep
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"climate.{self.unique_id}"

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
            model=self._dev_eep.eep_string,
            via_device=(DOMAIN, self.gateway.unique_id),
        )
    
    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        LOGGER.info("async func")
        LOGGER.info(f"hvac_mode {hvac_mode}")
        LOGGER.info(f"target temp {self.target_temperature}")
        LOGGER.info(f"current temp {self.current_temperature}")

    def set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        LOGGER.info("sync func")
        LOGGER.info(f"hvac_mode {hvac_mode}")
        LOGGER.info(f"target temp {self.target_temperature}")
        LOGGER.info(f"current temp {self.current_temperature}")

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        LOGGER.info("async func")
        LOGGER.info(kwargs)

    def set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        LOGGER.info("sync func")
        LOGGER.info(kwargs)

    def value_changed(self, msg):
        """Update the internal state of this device."""
        try:
            if msg.org == 0x07:
                decoded = self._dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return

        if  msg.org == 0x07 and self._dev_eep in [A5_10_06]:
            self._attr_current_temperature = decoded.temp
            self._attr_target_temperature = decoded.set_point_temp
            
            if decoded.mode == A5_10_06.Heater_Mode.OFF:
                self._attr_hvac_action = HVACAction.OFF
            elif decoded.mode == A5_10_06.Heater_Mode.NORMAL:
                self._attr_hvac_action = HVACAction.HEATING
            elif decoded.mode == A5_10_06.Heater_Mode.STAND_BY_2_DEGREES:
                self._attr_hvac_action = HVACAction.IDLE

        self.schedule_update_ha_state()
