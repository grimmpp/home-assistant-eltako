"""Support for Eltako light sources."""
from __future__ import annotations

import math
from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
)
from homeassistant import config_entries
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .config_helpers import *
from .device import *
from .gateway import EltakoGateway
from .const import *


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako light platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoEntity] = []
    
    if Platform.LIGHT in config:
        for entity_config in config[Platform.LIGHT]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            eep_string = entity_config.get(CONF_EEP)
            
            sender_config = entity_config.get(CONF_SENDER)
            sender_id = AddressExpression.parse(sender_config.get(CONF_ID))
            sender_eep_string = sender_config.get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
                sender_eep = EEP.find(sender_eep_string)
            except:
                LOGGER.warning("[Light] Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                if dev_eep in [A5_38_08]:
                    entities.append(EltakoDimmableLight(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep))
                elif dev_eep in [M5_38_08]:
                    entities.append(EltakoSwitchableLight(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep))
        
    log_entities_to_be_added(entities, Platform.LIGHT)
    async_add_entities(entities)


class EltakoDimmableLight(EltakoEntity, LightEntity):
    """Representation of an Eltako light source."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako light source."""
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self.dev_eep = dev_eep
        self._on_state = False
        self._attr_brightness = 50
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"light.{self.unique_id}"

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

    @property
    def is_on(self):
        """If light is on."""
        return self._on_state
    

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light source on or sets a specific dimmer value."""
        self._attr_brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            dimming = CentralCommandDimming(int(self.brightness / 255.0 * 100.0), 0, 1, 0, 0, 1)
            msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
            self.send_message(msg)
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._on_state = True
            self.schedule_update_ha_state()


    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light source off."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            dimming = CentralCommandDimming(0, 0, 1, 0, 0, 0)
            msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
            self.send_message(msg)
            
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_brightness = 0
            self._on_state = False
            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of this device.

        Dimmer devices like Eltako FUD61 send telegram in different RORGs.
        We only care about the 4BS (0xA5).
        """
        try:
            if msg.org == 0x07:
                decoded = self.dev_eep.decode_message(msg)
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
                    
                self._on_state = decoded.switching.switching_command
            elif decoded.command == 0x02:
                if decoded.dimming.learn_button != 1:
                    return
                    
                if decoded.dimming.dimming_range == 0:
                    self._attr_brightness = int((decoded.dimming.dimming_value / 100.0) * 255.0)
                elif decoded.dimming.dimming_range == 1:
                    self._attr_brightness = decoded.dimming.dimming_value

                self._on_state = decoded.dimming.switching_command
            else:
                return

            self.schedule_update_ha_state()


class EltakoSwitchableLight(EltakoEntity, LightEntity):
    """Representation of an Eltako light source."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako light source."""
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self.dev_eep = dev_eep
        self._on_state = False
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"light.{self.unique_id}"

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

    @property
    def is_on(self):
        """If light is on."""
        return self._on_state
    

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light source on or sets a specific dimmer value."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            switching = CentralCommandSwitching(0, 1, 0, 0, 1)
            msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
            self.send_message(msg)

        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._on_state = True
            self.schedule_update_ha_state()
        

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light source off."""
        address, _ = self._sender_id
        
        if self._sender_eep == A5_38_08:
            switching = CentralCommandSwitching(0, 1, 0, 0, 0)
            msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
            self.send_message(msg)
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._on_state = False
            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of this device."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Light] Could not decode message: %s", str(e))
            return

        if self.dev_eep in [M5_38_08]:
            self._on_state = decoded.state
            self.schedule_update_ha_state()
