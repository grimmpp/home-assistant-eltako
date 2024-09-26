"""Support for Eltako light sources."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er

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
    """Set up the Eltako light platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.LIGHT
    if platform in config:
        for entity_config in config[platform]:
            try:
                dev_conf = DeviceConf(entity_config)
                sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                if dev_conf.eep in [A5_38_08]:
                    entities.append(EltakoDimmableLight(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, sender_config.id, sender_config.eep))
                elif dev_conf.eep in [M5_38_08]:
                    entities.append(EltakoSwitchableLight(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, sender_config.id, sender_config.eep))
            
            except Exception as e:
                LOGGER.warning("[%s %s] Could not load configuration", platform, str(dev_conf.id))
                LOGGER.critical(e, exc_info=True)
        
    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class AbstractLightEntity(EltakoEntity, LightEntity, RestoreEntity):

    def load_value_initially(self, latest_state:State):
        # LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - state: {latest_state.state}")
        # LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - attributes: {latest_state.attributes}")
        try:
            if 'unknown' == latest_state.state:
                self._attr_is_on = None
            else:
                if latest_state.state in ['on', 'off']:
                    self._attr_is_on = 'on' == latest_state.state
                else:
                    self._attr_is_on = None

                self._attr_brightness = latest_state.attributes.get('brightness', None)
                
        except Exception as e:
            self._attr_is_on = None
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[{Platform.LIGHT} {self.dev_id}] value initially loaded: [is_on: {self.is_on}, brightness: {self.brightness}, state: {self.state}]")

class EltakoDimmableLight(AbstractLightEntity):
    """Representation of an Eltako light source."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, platform:str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako light source."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._sender_id = sender_id
        self._sender_eep = sender_eep

    
    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light source on or sets a specific dimmer value."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            dimming = CentralCommandDimming(int(brightness / 255.0 * 100.0), 0, 1, 0, 0, 1)
            msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
            self.send_message(msg)

        elif self._sender_eep in [F6_02_01, F6_02_02]:
            address, discriminator = self._sender_id
            # in PCT14 function 02 'direct  pushbutton top on' needs to be configured
            if discriminator == "left":
                action = 1  # 0x30
            elif discriminator == "right":
                action = 3  # 0x70
            else:
                action = 1
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self._sender_eep.eep_string)
            return
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_brightness = brightness
            self._attr_is_on = True
            self.schedule_update_ha_state()


    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light source off."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            dimming = CentralCommandDimming(0, 0, 1, 0, 0, 0)
            msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
            self.send_message(msg)

        elif self._sender_eep in [F6_02_01, F6_02_02]:
            address, discriminator = self._sender_id
            # in PCT14 function 02 'direct  pushbutton top on' needs to be configured
            if discriminator == "left":
                action = 0  # 0x10
            elif discriminator == "right":
                action = 2  # 0x50
            else:
                action = 0
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self._sender_eep.eep_string)
            return
            
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_brightness = 0
            self._attr_is_on = False
            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of this device.

        Dimmer devices like Eltako FUD61 send telegram in different RORGs.
        We only care about the 4BS (0xA5).
        """
        try:
            if msg.org == 0x07:
                decoded:A5_38_08 = self.dev_eep.decode_message(msg)
            elif msg.org == 0x05:
                LOGGER.debug("[Dimmable Light] Ignore on/off message with org=0x05")
                return

        except Exception as e:
            LOGGER.warning("[Dimmable Light] Could not decode message: %s %s", type(e), str(e))
            return

        if self.dev_eep in [A5_38_08]:
            if decoded.command == 0x01:
                if decoded.switching.learn_button != 1:
                    return
                    
                self._attr_is_on = decoded.switching.switching_command
            elif decoded.command == 0x02:
                if decoded.dimming.learn_button != 1:
                    return
                    
                if decoded.dimming.dimming_range == 0:
                    self._attr_brightness = int((decoded.dimming.dimming_value / 100.0) * 255.0)
                elif decoded.dimming.dimming_range == 1:
                    self._attr_brightness = decoded.dimming.dimming_value

                self._attr_is_on = decoded.dimming.switching_command
            else:
                return

            self.schedule_update_ha_state()

        else:
            LOGGER.warning("[%s %s] Device EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self.dev_eep.eep_string)


class EltakoSwitchableLight(AbstractLightEntity):
    """Representation of an Eltako light source."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako light source."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._sender_id = sender_id
        self._sender_eep = sender_eep


    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light source on or sets a specific dimmer value."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            switching = CentralCommandSwitching(0, 1, 0, 0, 1)
            msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
            self.send_message(msg)

        elif self._sender_eep in [F6_02_01, F6_02_02]:
            address, discriminator = self._sender_id
            # in PCT14 function 02 'direct  pushbutton top on' needs to be configured
            if discriminator == "left":
                action = 1  # 0x30
            elif discriminator == "right":
                action = 3  # 0x70
            else:
                action = 1
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self._sender_eep.eep_string)
            return

        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_on = True
            self.schedule_update_ha_state()
        

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light source off."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            switching = CentralCommandSwitching(0, 1, 0, 0, 0)
            msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
            self.send_message(msg)

        elif self._sender_eep in [F6_02_01, F6_02_02]:
            address, discriminator = self._sender_id
            # in PCT14 function 02 'direct  pushbutton top on' needs to be configured
            if discriminator == "left":
                action = 0  # 0x10
            elif discriminator == "right":
                action = 2  # 0x50
            else:
                action = 0
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self._sender_eep.eep_string)
            return
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_on = False
            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of this device."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[%s %s] Could not decode message: %s", Platform.LIGHT, str(self.dev_id), str(e))
            return

        if self.dev_eep in [M5_38_08]:
            self._attr_is_on = decoded.state == True
            self.schedule_update_ha_state()

        else:
            LOGGER.warning("[%s %s] Device EEP %s not supported.", Platform.LIGHT, str(self.dev_id), self.dev_eep.eep_string)