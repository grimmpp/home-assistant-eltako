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

from . import GENERAL_SETTINGS

from .device import *
from .gateway import EltakoGateway
from .const import CONF_ID_REGEX, CONF_EEP, CONF_SENDER, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG, ELTAKO_GATEWAY, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako switch platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoEntity] = []
    
    if Platform.SWITCH in config:
        for entity_config in config[Platform.SWITCH]:
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
                LOGGER.warning("[Switch] Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                entities.append(EltakoSwitch(gateway, dev_id, dev_name, dev_eep, sender_id, sender_eep))
    
    log_entities_to_be_added(entities, Platform.SWITCH)
    async_add_entities(entities)


class EltakoSwitch(EltakoEntity, SwitchEntity):
    """Representation of an Eltako switch device."""

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
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
        
        if GENERAL_SETTINGS[CONF_FAST_STATUS_CHANGE]:
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

        if GENERAL_SETTINGS[CONF_FAST_STATUS_CHANGE]:
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
