"""Support for Eltako covers."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from eltakobus.util import AddressExpression
from eltakobus.eep import EEP, G5_3F_7F, H5_3F_7F

from homeassistant import config_entries
from homeassistant.components.cover import CoverEntity, CoverEntityFeature, CoverState, ATTR_POSITION, ATTR_TILT_POSITION
from homeassistant.const import ATTR_ENTITY_ID, CONF_DEVICE_CLASS, Platform, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .core.entity import (EltakoEntity, RestoreEntity, State, log_entities_to_be_added,
                          validate_actuators_dev_and_sender_id)
from .const import (CONF_FAST_STATUS_CHANGE, CONF_INVERT_DIRECTION, DATA_ELTAKO, SERVICE_INVALIDATE_COVER_POSITION)
from .config import config_helpers
from .config.config_helpers import DeviceConf
from .core.gateway import EnOceanGateway
from .const import CONF_SENDER, CONF_TIME_CLOSES, CONF_TIME_OPENS, CONF_TIME_TILTS, LOGGER
from .core.integration import get_gateway_from_hass, get_device_config_for_gateway
import asyncio


async def _async_invalidate_cover_position(call: ServiceCall, hass: HomeAssistant) -> None:
    """Invalidate estimated positions for the selected Eltako covers."""
    # Eltako actuators report movement and elapsed runtime, but not an absolute
    # position. This service lets users discard an estimate after moving the
    # cover externally, so the next telegram can establish a new baseline.
    entities = (hass.data.get(DATA_ELTAKO) or {}).get('cover_entities', {})
    for entity_id in call.data[ATTR_ENTITY_ID]:
        entity = entities.get(entity_id)
        if entity is not None:
            entity.invalidate_position()

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
                dev_conf = DeviceConf(entity_config, [CONF_DEVICE_CLASS, CONF_INVERT_DIRECTION, CONF_TIME_CLOSES, CONF_TIME_OPENS, CONF_TIME_TILTS])
                sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                entities.append(EltakoCover(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep,
                                            sender_config.id, sender_config.eep,
                                            dev_conf.get(CONF_DEVICE_CLASS), dev_conf.get(CONF_TIME_CLOSES), dev_conf.get(CONF_TIME_OPENS), dev_conf.get(CONF_TIME_TILTS),
                                            dev_conf.area, dev_conf.get(CONF_INVERT_DIRECTION, False)))

            except Exception as e:   # noqa: BLE001 - one bad device configuration must not stop the platform
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)


    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
    # Keep a lookup by Home Assistant entity ID for the invalidation service.
    cover_entities = eltako_data.setdefault('cover_entities', {})
    cover_entities.update({entity.entity_id: entity for entity in entities})
    # The service is global to the integration, so register it only once when
    # more than one config entry contains covers.
    if not hass.services.has_service('eltako', SERVICE_INVALIDATE_COVER_POSITION):
        hass.services.async_register(
            'eltako', SERVICE_INVALIDATE_COVER_POSITION,
            lambda call: _async_invalidate_cover_position(call, hass),
            schema=vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_ids}),
        )
    async_add_entities(entities)

class EltakoCover(EltakoEntity, CoverEntity, RestoreEntity):
    """Representation of an Eltako cover device."""

    def __init__(self, platform:str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP, device_class: str, time_closes, time_opens, time_tilts, dev_area: str=None, invert_direction: bool=False):
        """Initialize the Eltako cover device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, dev_area=dev_area)
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
        self._invert_direction = bool(invert_direction)

        # Positions are estimated from the actuator's movement runtime. The
        # value remains unknown until a telegram or restored state provides a
        # usable starting point.
        self._attr_supported_features = (CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP)

        # Tilt control is available only when a tilt runtime is configured.
        if time_tilts is not None:
            self._attr_supported_features |= CoverEntityFeature.SET_TILT_POSITION

        # Intermediate positions require both full-travel runtimes to convert
        # a percentage into a movement duration.
        if time_closes is not None and time_opens is not None:
            self._attr_supported_features |= CoverEntityFeature.SET_POSITION


    def _to_physical_direction(self, direction: str) -> str:
        """Translate a logical Home Assistant direction to the actuator direction."""
        if not self._invert_direction:
            return direction
        return "down" if direction == "up" else "up"


    def _to_logical_direction(self, direction: str) -> str:
        """Translate an actuator direction to the logical Home Assistant direction."""
        return self._to_physical_direction(direction)


    def _set_moving_state(self, direction: str) -> None:
        """Set the logical moving state from a logical up/down direction."""
        if direction == "up":
            self._attr_is_opening = True
            self._attr_is_closing = False
        else:
            self._attr_is_opening = False
            self._attr_is_closing = True


    def load_value_initially(self, latest_state:State):
        # LOGGER.debug(f"[cover {self.dev_id}] latest state: {latest_state.state}")
        # LOGGER.debug(f"[cover {self.dev_id}] latest state attributes: {latest_state.attributes}")
        try:
            # Restore the numeric attributes first. They are more precise than
            # the generic open/closed state and must not be overwritten merely
            # because the cover was moving when Home Assistant restarted.
            # The attributes are not available if the cover was unavailable or unknown before the
            # restart. The state below is authoritative anyway, so a missing position is no error.
            self._attr_current_cover_position = latest_state.attributes.get('current_position')
            self._attr_current_cover_tilt_position = latest_state.attributes.get('current_tilt_position')

            if latest_state.state == CoverState.OPEN:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = False
                if self._attr_current_cover_position is None:
                    self._attr_current_cover_position = 100
                if self._attr_current_cover_tilt_position is None:
                    self._attr_current_cover_tilt_position = 100
            elif latest_state.state == CoverState.CLOSED:
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = True
                if self._attr_current_cover_position is None:
                    self._attr_current_cover_position = 0
                if self._attr_current_cover_tilt_position is None:
                    self._attr_current_cover_tilt_position = 0
            elif latest_state.state == CoverState.CLOSING:
                self._attr_is_opening = False
                self._attr_is_closing = True
                self._attr_is_closed = False
            elif latest_state.state == CoverState.OPENING:
                self._attr_is_opening = True
                self._attr_is_closing = False
                self._attr_is_closed = False
            elif latest_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                # nothing to restore. The cover reports its position with its next telegram.
                LOGGER.debug(f"[cover {self.dev_id}] No state to restore ('{latest_state.state}').")
            else:
                LOGGER.warning(f"[cover {self.dev_id}] Cannot restore unexpected state '{latest_state.state}'.")

        except Exception as e:   # noqa: BLE001 - a state restored from a previous run may no longer fit
            self._attr_current_cover_position = None
            self._attr_current_cover_tilt_position = None
            self._attr_is_opening = None
            self._attr_is_closing = None
            self._attr_is_closed = None # means undefined state
            LOGGER.warning(f"[cover {self.dev_id}] Cannot restore last state '{latest_state.state}': {e}")

        self.schedule_update_ha_state()
        LOGGER.debug(f"[cover {self.dev_id}] value initially loaded: ["
                     + f"is_opening: {self.is_opening}, "
                     + f"is_closing: {self.is_closing}, "
                     + f"is_closed: {self.is_closed}, "
                     + f"current_position: {self._attr_current_cover_position}, "
                     + f"current_tilt_position: {self._attr_current_cover_tilt_position}, "
                     + f"state: {self.state}]")

    def invalidate_position(self) -> None:
        """Forget estimated positions after an external movement."""
        # No absolute position is available from the bus, so clear both
        # estimates. The next status telegram will initialize them again.
        self._attr_current_cover_position = None
        self._attr_current_cover_tilt_position = None
        self._attr_is_opening = False
        self._attr_is_closing = False
        self._attr_is_closed = None
        self.schedule_update_ha_state()

    def open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        # Driving beyond the configured full runtime reaches the end stop and
        # gives the actuator a known reference for subsequent estimates.
        # One second more than the configured runtime, so that the cover really reaches its end
        # position (and therefore recalibrates itself). 255 is the maximum the telegram can
        # carry - a bigger value would make the encoding fail.
        if self._time_opens is not None:
            time = min(self._time_opens + 1, 255)
        else:
            time = 255

        address, _ = self._sender_id

        if self._sender_eep == H5_3F_7F:
            command = 0x01 if self._to_physical_direction("up") == "up" else 0x02
            msg = H5_3F_7F(time, command, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
            return

        #TODO: ... setting state should be comment out
        # Don't set state instead wait for response from actor so that real state of light is displayed.
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_is_opening = True
            self._attr_is_closing = False

            self.schedule_update_ha_state()


    def close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        # As with opening, the extra second makes the closed end position a
        # reliable reference; the protocol field is limited to 255.
        if self._time_closes is not None:
            time = min(self._time_closes + 1, 255)
        else:
            time = 255

        address, _ = self._sender_id

        if self._sender_eep == H5_3F_7F:
            command = 0x01 if self._to_physical_direction("down") == "up" else 0x02
            msg = H5_3F_7F(time, command, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
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

        if self._attr_current_cover_position is None and position not in (0, 100):
            # Without a known position no runtime can be calculated. Only the end positions can
            # be reached blindly - they also recalibrate the position.
            LOGGER.warning(f"[cover {self.dev_id}] Current position is unknown. Only 0 or 100 can be "
                           f"set until the actuator reported a position (requested: {position}).")
            return

        if position == self._attr_current_cover_position:
            return
        elif position == 100:
            # drive into the end position (full runtime + 1s), see open_cover
            direction = "up"
            time = min(self._time_opens + 1, 255)
        elif position == 0:
            direction = "down"
            time = min(self._time_closes + 1, 255)
        elif position > self._attr_current_cover_position:
            direction = "up"
            # Convert the percentage difference into the actuator's runtime.
            time = max(1,min(int(((position - self._attr_current_cover_position) / 100.0) * self._time_opens), 255))
            # try to prevent covers moving completely up or down when time = 0
        elif position < self._attr_current_cover_position:
            direction = "down"
            time = max(1,min(int(((self._attr_current_cover_position - position) / 100.0) * self._time_closes), 255))
            # try to prevent covers moving completely up or down when time = 0

        if self._sender_eep == H5_3F_7F:
            physical_direction = self._to_physical_direction(direction)
            if physical_direction == "up":
                command = 0x01
            else:
                command = 0x02

            msg = H5_3F_7F(time, command, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
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
        except Exception as e:   # noqa: BLE001 - a malformed telegram must not kill the entity
            LOGGER.warning("Could not decode message: %s", str(e))
            return

        if self.dev_eep in [G5_3F_7F]:
            LOGGER.debug(f"[cover {self.dev_id}] G5_3F_7F - {decoded.__dict__}")

            # Status telegrams announce direction or an end position. They do
            # not contain an absolute intermediate position.
            ## is received as response when button pushed (command was sent)
            ## this message is received directly when the cover starts to move
            ## when the cover results in completely open or close one of the following messages (open or closed) will appear
            if decoded.state == 0x02: # down
                self._set_moving_state(self._to_logical_direction("down"))
                self._attr_is_closed = False
            elif decoded.state == 0x50: # closed
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = not self._invert_direction
                self._attr_current_cover_position = 0 if not self._invert_direction else 100
                self._attr_current_cover_tilt_position = 0 if not self._invert_direction else 100
            elif decoded.state == 0x01: # up
                self._set_moving_state(self._to_logical_direction("up"))
                self._attr_is_closed = False
            elif decoded.state == 0x70: # open
                self._attr_is_opening = False
                self._attr_is_closing = False
                self._attr_is_closed = self._invert_direction
                self._attr_current_cover_position = 100 if not self._invert_direction else 0
                self._attr_current_cover_tilt_position = 100 if not self._invert_direction else 0

            ## is received when cover stops at the desired intermediate position
            ## if not close state is always open (close state should be reported with closed message above)
            elif decoded.time is not None and decoded.direction is not None and self._time_closes is not None and self._time_opens is not None:

                # Integrate the reported movement time into the last estimate.
                # This is intentionally an estimate until an end-stop telegram
                # resets the position to exactly 0 or 100.
                time_in_seconds = decoded.time / 10.0

                physical_direction = "up" if decoded.direction == 0x01 else "down"
                if self._to_logical_direction(physical_direction) == "up":
                    # If the latest state is unknown, the cover position
                    # will be set to None, therefore we have to guess
                    # the initial position.
                    if self._attr_current_cover_position is None:
                        self._attr_current_cover_position = 0

                    self._attr_current_cover_position = min(self._attr_current_cover_position + int(time_in_seconds / self._time_opens * 100.0), 100)
                    if self._time_tilts is not None:
                        self._attr_current_cover_tilt_position = min(self._attr_current_cover_tilt_position + int(decoded.time / self._time_tilts * 100.0), 100)

                else:  # logical down
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


    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        """Tilt the slats: start the movement and stop it after the calculated time.

        Runs in the event loop, so the wait between the move and the stop telegram must not
        block (a sync set_cover_tilt_position with time.sleep() would block a worker thread
        for the whole tilt time).
        """
        address, _ = self._sender_id
        tilt_position = kwargs[ATTR_TILT_POSITION]

        if self._time_tilts is None:
            return

        if self._attr_current_cover_tilt_position is None:
            # The tilt position is unknown (e.g. after a restart without restored state).
            # The slats are moved from the assumed end position of the requested direction,
            # which also re-calibrates the position.
            self._attr_current_cover_tilt_position = 0 if tilt_position > 0 else 100
            LOGGER.debug(f"[cover {self.dev_id}] Tilt position unknown - assuming "
                         f"{self._attr_current_cover_tilt_position} as starting point.")

        if tilt_position == self._attr_current_cover_tilt_position:
            return
        elif tilt_position > self._attr_current_cover_tilt_position:
            direction = "up"
            tilt_difference = tilt_position - self._attr_current_cover_tilt_position
        else:
            direction = "down"
            tilt_difference = self._attr_current_cover_tilt_position - tilt_position

        # The actuator has no absolute tilt command: run in the right direction
        # for the calculated duration, then send stop. time_tilts is configured
        # in 0.1-second units while asyncio.sleep() expects seconds.
        sleeptime = tilt_difference / 100.0 * self._time_tilts / 10.0

        if self._sender_eep == H5_3F_7F:
            physical_direction = self._to_physical_direction(direction)
            if physical_direction == "up":
                command = 0x01
            else:
                command = 0x02

            msg = H5_3F_7F(0, command, 1).encode_message(address)
            self.send_message(msg)
            await asyncio.sleep(sleeptime)

            msg = H5_3F_7F(0, 0x00, 1).encode_message(address)
            self.send_message(msg)

        else:
            LOGGER.warning("[%s %s] Sender EEP %s not supported.", Platform.COVER, str(self.dev_id), self._sender_eep.eep_string)
            return


        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            # The stop telegram was already sent above, so the cover is standing still again.
            # The tilt position itself is deliberately not set here: the actuator reports the
            # runtime of the movement afterwards and value_changed derives the position from
            # it - setting it here as well would count the movement twice.
            self._attr_is_opening = False
            self._attr_is_closing = False

            self.schedule_update_ha_state()
