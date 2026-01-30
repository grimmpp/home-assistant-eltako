"""Support for Eltako fans."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from . import config_helpers, get_gateway_from_hass, get_device_config_for_gateway
from .config_helpers import DeviceConf
from .device import *
from .gateway import EnOceanGateway
from .const import *

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako fan platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.FAN
    if platform in config:
        for entity_config in config[platform]:
            try:
                dev_conf = DeviceConf(entity_config)
                sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                if dev_conf.eep in [A5_38_08, M5_38_08]:
                    entities.append(EltakoFan(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, sender_config.id, sender_config.eep))
            
            except Exception as e:
                LOGGER.warning("[%s %s] Could not load configuration", platform, str(dev_conf.id))
                LOGGER.critical(e, exc_info=True)
        
    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class EltakoFan(EltakoEntity, FanEntity, RestoreEntity):
    """Representation of an Eltako fan."""

    def __init__(self, platform:str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako fan."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        
        if dev_eep in [A5_38_08]:
            self._attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        elif dev_eep in [M5_38_08]:
            self._attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def load_value_initially(self, latest_state:State):
        try:
            if 'unknown' == latest_state.state:
                self._attr_percentage = None
            else:
                if latest_state.state == 'on':
                    self._attr_percentage = latest_state.attributes.get('percentage', 100)
                else:
                    self._attr_percentage = 0
                
        except Exception as e:
            self._attr_percentage = None
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[{Platform.FAN} {self.dev_id}] value initially loaded: [percentage: {self.percentage}, state: {self.state}]")

    def turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        """Turn on the fan."""
        if percentage is None:
            percentage = 100
        self.set_percentage(percentage)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        self.set_percentage(0)

    def set_percentage(self, percentage: int) -> None:
        """Set the speed percentage of the fan."""
        address, _ = self._sender_id
        
        if percentage == 0:
            if self._sender_eep == A5_38_08:
                if self.dev_eep in [M5_38_08]:
                    switching = CentralCommandSwitching(0, 1, 0, 0, 0)
                    msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
                    self.send_message(msg)
                else:
                    dimming = CentralCommandDimming(0, 0, 1, 0, 0, 0)
                    msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
                    self.send_message(msg)
        else:
            if self._sender_eep == A5_38_08:
                if self.dev_eep in [M5_38_08]:
                    switching = CentralCommandSwitching(0, 1, 0, 0, 1)
                    msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
                    self.send_message(msg)
                else:
                    dimming = CentralCommandDimming(int(percentage), 0, 1, 0, 0, 1)
                    msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
                    self.send_message(msg)

        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_percentage = percentage
            self.schedule_update_ha_state()

    def value_changed(self, msg):
        """Update the internal state of this device."""
        try:
            if msg.org == 0x07:
                decoded = self.dev_eep.decode_message(msg)
            elif msg.org == 0x05:
                # ignore status messages from other devices
                return
            elif self.dev_eep in [M5_38_08]:
                decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Fan] Could not decode message: %s %s", type(e), str(e))
            return

        if self.dev_eep in [A5_38_08]:
            if decoded.command == 0x02:
                if decoded.dimming.learn_button != 1:
                    return
                    
                if decoded.dimming.dimming_range == 0:
                    # 0..100
                    self._attr_percentage = decoded.dimming.dimming_value
                elif decoded.dimming.dimming_range == 1:
                    # 0..255 -> 0..100
                    self._attr_percentage = int((decoded.dimming.dimming_value / 255.0) * 100.0)

                if decoded.dimming.switching_command == 0:
                     self._attr_percentage = 0

            self.schedule_update_ha_state()

        elif self.dev_eep in [M5_38_08]:
            if decoded.state:
                self._attr_percentage = 100
            else:
                self._attr_percentage = 0
            self.schedule_update_ha_state() 

