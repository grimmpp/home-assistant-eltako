"""Support for Eltako switches."""
from __future__ import annotations

from typing import Any

from eltakobus.util import combine_hex
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

from .const import DOMAIN, LOGGER
from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako switch platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    
    entities: list[EltakoSensor] = []
    
    if Platform.SWITCH in config:
        for entity_config in config[Platform.SWITCH]:
            dev_id = AddressExpression.parse(entity_entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            sender_id = AddressExpression.parse(entity_config.get(CONF_SENDER_ID))
            eep_string = entity_config.get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
            except:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                entities.append(EltakoSwitch(dev_id, dev_name, dev_eep))
        
    async_add_entities(entities)


class EltakoSwitch(EltakoEntity, SwitchEntity):
    """Representation of an Eltako switch device."""

    def __init__(self, dev_id, dev_name, dev_eep, sender_id):
        """Initialize the Eltako switch device."""
        super().__init__(dev_id, dev_name)
        self._dev_eep = dev_eep
        self._sender_id = sender_id
        self._on_state = False
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"switch.{self.unique_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id.plain_address().hex())},
            manufacturer=MANUFACTURER,
            name=dev_name,
            model=dev_eep.eep_string,
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
        
        if discriminator == "left":
            action = 0
        elif discriminator == "right":
            action = 2
        else:
            action = 0
            
        msg = F6_02_01(action, 1, 0, 0).encode_message(address)
        self.send_message(msg)
        
        self._on_state = True

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        address, discriminator = self._sender_id
        
        if discriminator == "left":
            action = 1
        elif discriminator == "right":
            action = 3
        else:
            action = 1
            
        msg = F6_02_01(action, 1, 0, 0).encode_message(address)
        self.send_message(msg)
        
        self._on_state = False

    def value_changed(self, msg):
        """Update the internal state of the switch."""
        try:
            decoded = self._dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return

        if self._dev_eep in [M5_38_08]:
            self._on_state = decoded.state
            self.schedule_update_ha_state()
