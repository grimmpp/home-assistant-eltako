"""Support for Eltako covers."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant import config_entries
from homeassistant.components.cover import PLATFORM_SCHEMA, CoverEntity, CoverEntityFeature
from homeassistant.const import CONF_DEVICE_CLASS, CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, CONF_TIME_CLOSES, CONF_TIME_OPENS, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG, LOGGER

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako cover platform."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    
    entities: list[EltakoSensor] = []
    
    if Platform.COVER in config:
        for entity_config in config[Platform.COVER]:
            dev_id = AddressExpression.parse(entity_entity_config.get(CONF_ID))
            dev_name = entity_config.get(CONF_NAME)
            sender_id = AddressExpression.parse(entity_config.get(CONF_SENDER_ID))
            device_class = entity_config.get(CONF_DEVICE_CLASS)
            time_closes = entity_config.get(CONF_TIME_CLOSES)
            time_opens = entity_config.get(CONF_TIME_OPENS)
            eep_string = entity_config.get(CONF_EEP)

            try:
                dev_eep = EEP.find(eep_string)
            except:
                LOGGER.warning("Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                entities.append(EltakoCover(dev_id, dev_name, dev_eep, sender_id, device_class, time_closes, time_opens))
        
    async_add_entities(entities)

class EltakoCover(EltakoEntity, CoverEntity):
    """Representation of an Eltako cover device."""

    def __init__(self, dev_id, dev_name, dev_eep, sender_id, device_class, time_closes, time_opens):
        """Initialize the Eltako cover device."""
        super().__init__(dev_id, dev_name)
        self._dev_eep = dev_eep
        self._sender_id = sender_id
        self._device_class = device_class
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = False
        self._attr_current_cover_position = 100
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{device_class}"
        self.entity_id = f"cover.{self.unique_id}"
        self._time_closes = time_closes
        self._time_opens = time_opens
        
        self._attr_supported_features = (CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP)
        
        if time_closes is not None and time_opens is not None:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION

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
        )
        
    @property
    def name(self):
        """Return the device name."""
        return None

    def open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        time = 255
        
        address, _ = self._sender_id
        
        msg = H5_3F_7F(time, 0x01, 1).encode_message(address)
        self.send_message(msg)
        
        self._attr_is_opening = True
        self._attr_is_closing = False

    def close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        time = 255
        
        address, _ = self._sender_id
        
        msg = H5_3F_7F(time, 0x02, 1).encode_message(address)
        self.send_message(msg)
        
        self._attr_is_closing = True
        self._attr_is_opening = False

    def set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if self._time_closes is None or self._time_opens is None:
            return
        
        position = kwargs[ATTR_POSITION]
        
        if position == self._attr_current_cover_position:
            return
        elif position == 100:
            command = 0x01
            time = 255
        elif position == 0:
            command = 0x02
            time = 255
        elif position > self._attr_current_cover_position:
            command = 0x01
            time = min(int(((position - self._attr_current_cover_position) / 100.0) * self._time_opens), 255)
        elif position < self._attr_current_cover_position:
            command = 0x02
            time = min(int(((self._attr_current_cover_position - position) / 100.0) * self._time_closes), 255)

        address, _ = self._sender_id
        
        msg = H5_3F_7F(time, command, 1).encode_message(address)
        self.send_message(msg)
        
        if command == 0x01:
            self._attr_is_opening = True
            self._attr_is_closing = False
        elif command == 0x02:
            self._attr_is_closing = True
            self._attr_is_opening = False

    def stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        address, _ = self._sender_id

        msg = H5_3F_7F(0, 0x00, 1).encode_message(address)
        self.send_message(msg)
        
        self._attr_is_closing = False
        self._attr_is_opening = False

    def value_changed(self, msg):
        """Update the internal state of the cover."""
        try:
            decoded = self._dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return

        if self._dev_eep in [G5_3F_7F]:
            if decoded.state == 0x02: # down
                self._attr_is_closing = True
                self._attr_is_opening = False
            elif decoded.state == 0x50: # closed
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = True
                self._attr_current_cover_position = 0
            elif decoded.state == 0x01: # up
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif decoded.state == 0x70: # open
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = False
                self._attr_current_cover_position = 100
            elif decoded.time is not None and decoded.direction is not None and self._time_closes is not None and self._time_opens is not None:
                time_in_seconds = decoded.time / 10.0
                
                if direction == 0x01: # up
                    self._attr_current_cover_position = min(self._attr_current_cover_position + int(time_in_seconds / self._time_opens * 100.0), 100)
                else: # down
                    self._attr_current_cover_position = max(self._attr_current_cover_position - int(time_in_seconds / self._time_closes * 100.0), 0)
                    
                self._attr_is_closing = False
                self._attr_is_opening = False
            
            self.schedule_update_ha_state()
