"""Support for Eltako switches."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant import config_entries
from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import config_helpers, get_gateway_from_hass, get_device_config_for_gateway
from .device import *
from .gateway import ESP2Gateway
from .const import *


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako switch platform."""
    gateway: ESP2Gateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.SWITCH
    if platform in config:
        for entity_config in config[platform]:
            try:
                dev_conf = device_conf(entity_config)
                sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                entities.append(EltakoSwitch(gateway, dev_conf.id, dev_conf.name, dev_conf.eep, sender_config.id, sender_config.eep))
            
            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)
                
    
    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, Platform.SWITCH)
    async_add_entities(entities)


class EltakoSwitch(EltakoEntity, SwitchEntity):
    """Representation of an Eltako switch device."""

    def __init__(self, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        """Initialize the Eltako switch device."""
        super().__init__(gateway, dev_id, dev_name, dev_eep)
        self.dev_eep = dev_eep
        self._sender_id = sender_id
        self._sender_eep = sender_eep
        self._on_state = False
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"switch.{self.unique_id}"

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
        """Return whether the switch is on or off."""
        return self._on_state


    @property
    def name(self):
        """Return the device name."""
        return None


    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        address, discriminator = self._sender_id
        
        if self._sender_eep == F6_02_01:
            if discriminator == "left":
                action = 0
            elif discriminator == "right":
                action = 2
            else:
                action = 0
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._on_state = True
            self.schedule_update_ha_state()


    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        address, discriminator = self._sender_id
        
        if self._sender_eep == F6_02_01:
            if discriminator == "left":
                action = 1
            elif discriminator == "right":
                action = 3
            else:
                action = 1
                
            pressed_msg = F6_02_01(action, 1, 0, 0).encode_message(address)
            self.send_message(pressed_msg)
            
            released_msg = F6_02_01(action, 0, 0, 0).encode_message(address)
            self.send_message(released_msg)

        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._on_state = False
            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of the switch."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Switch] Could not decode message: %s", str(e))
            return

        if self.dev_eep in [M5_38_08]:
            self._on_state = decoded.state
            self.schedule_update_ha_state()
