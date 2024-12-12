"""Support for Eltako covers."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant import config_entries
from homeassistant.components.cover import CoverEntity, CoverEntityFeature, ATTR_POSITION, ATTR_TILT_POSITION
from homeassistant.const import CONF_DEVICE_CLASS, Platform, STATE_OPEN, STATE_OPENING, STATE_CLOSED, STATE_CLOSING
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .device import *
from . import config_helpers 
from .config_helpers import DeviceConf
from .gateway import EnOceanGateway
from .const import CONF_SENDER, CONF_TIME_CLOSES, CONF_TIME_OPENS, CONF_TIME_TILTS, DOMAIN, MANUFACTURER, LOGGER
from . import get_gateway_from_hass, get_device_config_for_gateway
import time

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako cover platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.COVER
    if platform in config:
        for entity_config in config[platform]:

            try:
                dev_conf = DeviceConf(entity_config, [CONF_DEVICE_CLASS, CONF_TIME_CLOSES, CONF_TIME_OPENS, CONF_TIME_TILTS])
                sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                entities.append(EltakoCover(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, 
                                            sender_config.id, sender_config.eep, 
                                            dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_TIME_CLOSES), dev_conf.get(CONF_TIME_OPENS), dev_conf.get(CONF_TIME_TILTS)))

            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)
                
        
    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)

class EltakoCover(EltakoEntity, CoverEntity, RestoreEntity):
    """Representation of an Eltako cover device."""

    def __init__(self, platform:str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP, device_class: str, time_closes, time_opens, time_tilts):
        """Initialize the Eltako cover device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._sender_id = sender_id
        self._sender_eep = sender_eep

        self._attr_device_class = device_class
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = None # means undefined state
        self._attr_current_cover_position = None
        self._attr_current_cover_tilt_position = None
        self._time_closes = time_closes
        self._time_opens = time_opens
        self._time_tilts = time_tilts
        
        self._attr_supported_features = (CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP)
        
        if time_tilts is not None:
            self._attr_supported_features |= CoverEntityFeature.SET_TILT_POSITION

        if time_closes is not None and time_opens is not None:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION


    def load_value_initially(self, latest_state: State):
        # LOGGER.debug(f"[cover {self.dev_id}] latest state: {latest_state.state}")
        # LOGGER.debug(f"[cover {self.dev_id}] latest state attributes: {latest_state.attributes}")                                                                                                 
        try:
            # Prüfen, ob die benötigten Attribute vorhanden sind
            self._attr_current_cover_position = latest_state.attributes.get('current_position', None)
            self._attr_current_cover_tilt_position = latest_state.attributes.get('current_tilt_position', None)

            if self._attr_current_cover_position is None or self._attr_current_cover_tilt_position is None:
                LOGGER.warning(f"[cover {self.dev_id}] Missing 'current_position' or 'current_tilt_position' in latest_state.attributes. Defaulting to None.")
            
            # Zustand basierend auf latest_state.state setzen
            if latest_state.state == STATE_OPEN:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = False
                self._attr_current_cover_position = 100
                self._attr_current_cover_tilt_position = 100
            elif latest_state.state == STATE_CLOSED:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = True
                self._attr_current_cover_position = 0
                self._attr_current_cover_tilt_position = 0
            elif latest_state.state == STATE_CLOSING:
                self._attr_is_opening = False
                self._attr_is_closing = True
                self._attr_is_closed = False
            elif latest_state.state == STATE_OPENING:
                self._attr_is_opening = True
                self._attr_is_closing = False
                self._attr_is_closed = False
            else:
                LOGGER.warning(f"[cover {self.dev_id}] Unknown state: {latest_state.state}")
            
        except KeyError as e:
            # Spezifischer Fehler bei fehlendem Schlüssel
            LOGGER.error(f"[cover {self.dev_id}] KeyError while accessing attributes: {e}")
            self._attr_current_cover_position = None
            self._attr_current_cover_tilt_position = None
            self._attr_is_opening = None
            self._attr_is_closing = None
            self._attr_is_closed = None  # means undefined state
        except Exception as e:
            # Allgemeiner Fehler
            LOGGER.error(f"[cover {self.dev_id}] Unexpected error in load_value_initially: {e}")
            self._attr_current_cover_position = None
            self._attr_current_cover_tilt_position = None
            self._attr_is_opening = None
            self._attr_is_closing = None
            self._attr_is_closed = None  # means undefined state
            raise e  # Optional: Fehler weiterwerfen, wenn es kritisch ist
        
        # Aktualisiere den Zustand in Home Assistant
        self.schedule_update_ha_state()
        LOGGER.debug(f"[cover {self.dev_id}] Value initially loaded: [" 
                     + f"is_opening: {self._attr_is_opening}, "
                     + f"is_closing: {self._attr_is_closing}, "
                     + f"is_closed: {self._attr_is_closed}, "
                     + f"current_position: {self._attr_current_cover_position}, "
                     + f"current_tilt_position: {self._attr_current_cover_tilt_position}, "
                     + f"state: {self.state}]")


    def open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        if self._time_opens is not None:
            time = self._time_opens + 1
        else:
            time = 255
        
        address, _ = self._sender_id
        
        if self._sender_eep == H5_3F_7F:
            msg = H5_3F_7F(time, 0x01, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warn("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
            return
        
        #TODO: ... setting state should be comment out
        # Don't set state instead wait for response from actor so that real state of light is displayed.
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_opening = True
            self._attr_is_closing = False
            
            self.schedule_update_ha_state()
    

    def close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        if self._time_closes is not None:
            time = self._time_closes + 1
        else:
            time = 255
        
        address, _ = self._sender_id
        
        if self._sender_eep == H5_3F_7F:
            msg = H5_3F_7F(time, 0x02, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warn("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
            return
        
        #TODO: ... setting state should be comment out
        # Don't set state instead wait for response from actor so that real state of light is displayed.
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_closing = True
            self._attr_is_opening = False

            self.schedule_update_ha_state()

    def set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        if self._time_closes is None or self._time_opens is None:
            return
        
        address, _ = self._sender_id
        position = kwargs[ATTR_POSITION]
        
        if position == self._attr_current_cover_position:
            return
        elif position == 100:
            direction = "up"
            time = self._time_opens + 1
        elif position == 0:
            direction = "down"
            time = self._time_closes + 1
        elif position > self._attr_current_cover_position:
            direction = "up"
            time = max(1,min(int(((position - self._attr_current_cover_position) / 100.0) * self._time_opens), 255))
            # try to prevent covers moving completely up or down when time = 0
        elif position < self._attr_current_cover_position:
            direction = "down"
            time = max(1,min(int(((self._attr_current_cover_position - position) / 100.0) * self._time_closes), 255))
            # try to prevent covers moving completely up or down when time = 0

        if self._sender_eep == H5_3F_7F:
            if direction == "up":
                command = 0x01
            elif direction == "down":
                command = 0x02
            
            msg = H5_3F_7F(time, command, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warn("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
            return
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            if direction == "up":
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif direction == "down":
                self._attr_is_closing = True
                self._attr_is_opening = False
                
            self.schedule_update_ha_state()
        

    def stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        address, _ = self._sender_id

        if self._sender_eep == H5_3F_7F:
            msg = H5_3F_7F(0, 0x00, 1).encode_message(address)
            self.send_message(msg)
        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_closing = False
            self._attr_is_opening = False

            self.schedule_update_ha_state()


    def value_changed(self, msg):
        """Update the internal state of the cover."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("Could not decode message: %s", str(e))
            return
        
        if self.dev_eep in [G5_3F_7F]:
            LOGGER.debug(f"[cover {self.dev_id}] G5_3F_7F - {decoded.__dict__}")

            ## is received as response when button pushed (command was sent) 
            ## this message is received directly when the cover starts to move
            ## when the cover results in completely open or close one of the following messages (open or closed) will appear
            if decoded.state == 0x02: # down
                self._attr_is_closing = True
                self._attr_is_opening = False
                self._attr_is_closed = False
            elif decoded.state == 0x50: # closed
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = True
                self._attr_current_cover_position = 0
                self._attr_current_cover_tilt_position = 0
            elif decoded.state == 0x01: # up
                self._attr_is_opening = True
                self._attr_is_closing = False
                self._attr_is_closed = False
            elif decoded.state == 0x70: # open
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = False
                self._attr_current_cover_position = 100
                self._attr_current_cover_tilt_position = 100

            ## is received when cover stops at the desired intermediate position
            ## if not close state is always open (close state should be reported with closed message above)
            elif decoded.time is not None and decoded.direction is not None and self._time_closes is not None and self._time_opens is not None:

                time_in_seconds = decoded.time / 10.0

                if decoded.direction == 0x01:  # up
                    # If the latest state is unknown, the cover position
                    # will be set to None, therefore we have to guess
                    # the initial position.
                    if self._attr_current_cover_position is None:
                        self._attr_current_cover_position = 0
                    
                    self._attr_current_cover_position = min(self._attr_current_cover_position + int(time_in_seconds / self._time_opens * 100.0), 100)
                    if self._time_tilts is not None:
                        self._attr_current_cover_tilt_position = min(self._attr_current_cover_tilt_position + int(decoded.time / self._time_tilts * 100.0), 100)

                else:  # down
                    # If the latest state is unknown, the cover position
                    # will be set to None, therefore we have to guess
                    # the initial position.
                    if self._attr_current_cover_position is None:
                        self._attr_current_cover_position = 100
                    
                    self._attr_current_cover_position = max(self._attr_current_cover_position - int(time_in_seconds / self._time_closes * 100.0), 0)
                    if self._time_tilts is not None:
                        self._attr_current_cover_tilt_position = max(self._attr_current_cover_tilt_position - int(decoded.time / self._time_tilts * 100.0), 0)

                if self._attr_current_cover_position == 0:
                    self._attr_is_closed = True
                    self._attr_is_opening = False
                    self._attr_is_closing = False
                else:
                    self._attr_is_closed = False
                    self._attr_is_opening = False
                    self._attr_is_closing = False

            
            LOGGER.debug(f"[cover {self.dev_id}] state: {self.state}, opening: {self.is_opening}, closing: {self.is_closing}, closed: {self.is_closed}, position: {self._attr_current_cover_position}")

            self.schedule_update_ha_state()


    def set_cover_tilt_position(self, **kwargs: Any) -> None:
        address, _ = self._sender_id
        tilt_position = kwargs[ATTR_TILT_POSITION]
        
        if tilt_position == self._attr_current_cover_tilt_position:
            return
        elif tilt_position > self._attr_current_cover_tilt_position:
            direction = "up"
            sleeptime = min((((tilt_position - self._attr_current_cover_tilt_position) / 100.0 * self._time_tilts / 10.0) ), 255.0)
        elif tilt_position < self._attr_current_cover_tilt_position:
            direction = "down"
            sleeptime = min((((self._attr_current_cover_tilt_position - tilt_position) / 100.0 * self._time_tilts / 10.0) ), 255.0)

        if self._sender_eep == H5_3F_7F:
            if direction == "up":
                command = 0x01
            elif direction == "down":
                command = 0x02
            
            msg = H5_3F_7F(0, command, 1).encode_message(address)
            self.send_message(msg)
            time.sleep(sleeptime)
            
            msg = H5_3F_7F(0, 0x00, 1).encode_message(address)
            self.send_message(msg)

        
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            if direction == "up":
                self._attr_is_opening = True
                self._attr_is_closing = False
            elif direction == "down":
                self._attr_is_closing = True
                self._attr_is_opening = False
