"""How a simulated actuator reacts to a command.

Switching a simulated light really has to turn the entity on - otherwise the simulation only
proves that a telegram can be sent. So the command the automation system sends is decoded
(`decode_command`) and the actuator answers with the status telegram its real counterpart would
send (`answer_command`).

Two tables, both open for more devices:

* **senders** - what a command telegram means, per sender EEP (`SENDER_DECODERS`). A dimming
  command of A5-38-08 carries a brightness, a rocker telegram of F6-02-01 carries a button.
* **actuators** - what the device reports afterwards, per device EEP (one `Actuator` subclass
  each). A relay reports on/off, a dimmer its brightness, a cover the end position it reached,
  a heating actuator the target value it acknowledges.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eltakobus.message import ESP2Message

from .constants import ACTUATOR_PLATFORMS
from .telegrams import encode_state_telegram, find_eep


@dataclass
class Command:
    """What a command telegram of the automation system asks for.

    Only the fields the profile carries are set: a rocker switch says on/off, a shutter command
    says a direction, a temperature controller says a target value.
    """

    on: bool = False
    brightness: int | None = None                # 0..100 %
    direction: str | None = None                 # 'up' | 'down' | 'stop'
    target_temperature: float | None = None
    mode: int | None = None                      # A5-10-06 HeaterMode
    raw: dict = field(default_factory=dict)      # everything the decoder saw, for logging


### ---------------------------------------------------------------------------
### what a command telegram means (by sender EEP)
### ---------------------------------------------------------------------------

def _decode_central_command(decoded, previous_on: bool) -> Command | None:
    if decoded.command == 0x01:
        return Command(on=bool(decoded.switching.switching_command))
    if decoded.command == 0x02:
        value = decoded.dimming.dimming_value
        # dimming_range 0 = 0..100 %, 1 = 0..255
        percent = int(value if decoded.dimming.dimming_range == 0 else round(value / 255.0 * 100.0))
        return Command(on=bool(decoded.dimming.switching_command) and percent > 0,
                       brightness=percent)
    return None


def _decode_rocker(decoded, previous_on: bool) -> Command | None:
    # A rocker sender presses and releases; only the press carries a command. Top (action 1/3)
    # switches on, bottom (0/2) switches off - see switch.py and light.py of the integration.
    if not decoded.energy_bow:
        return None
    return Command(on=decoded.rocker_first_action in (1, 3))


def _decode_shutter_command(decoded, previous_on: bool) -> Command | None:
    direction = {0x01: 'up', 0x02: 'down', 0x00: 'stop'}.get(decoded.command)
    if direction is None:
        return None
    return Command(direction=direction,
                   on=previous_on if direction == 'stop' else direction == 'up')


def _decode_temperature_control(decoded, previous_on: bool) -> Command | None:
    mode = decoded.mode.value
    return Command(on=mode != 0x10,     # 0x10 = off
                   target_temperature=decoded.target_temperature, mode=mode)


SENDER_DECODERS = {
    'A5-38-08': _decode_central_command,
    'F6-02-01': _decode_rocker,
    'F6-02-02': _decode_rocker,
    'H5-3F-7F': _decode_shutter_command,
    'A5-10-06': _decode_temperature_control,
}


def decode_command(sender_eep: str, msg: ESP2Message, previous_on: bool = False) -> Command | None:
    """The command a telegram carries, or None if it carries none (e.g. a button release)."""
    eep = str(sender_eep).upper()
    decoder = SENDER_DECODERS.get(eep)
    if decoder is None:
        return None
    return decoder(find_eep(eep).decode_message(msg), previous_on)


### ---------------------------------------------------------------------------
### what the actuator reports afterwards (by device EEP)
### ---------------------------------------------------------------------------

class Actuator:
    """Behaviour of one kind of simulated actuator.

    A subclass declares which device EEP it serves and turns a command into the values that
    device reports. Returning None means: this command changes nothing that can be reported.
    """

    eep: str = ""

    def report(self, state: dict, command: Command) -> dict | None:
        """The new values of the device, or None if there is nothing to report."""
        raise NotImplementedError


class RelayActuator(Actuator):
    """A switching relay (FSR14, FSR61, ...): reports on or off."""

    eep = 'M5-38-08'

    def report(self, state: dict, command: Command) -> dict | None:
        return {'state': 1 if command.on else 0}


class DimmerActuator(Actuator):
    """A dimmer (FUD14, FUD61, ...): reports its brightness in percent."""

    eep = 'A5-38-08'

    def report(self, state: dict, command: Command) -> dict | None:
        brightness = command.brightness
        if brightness is None:
            brightness = 100 if command.on else 0
        return {'command': 2, 'dimming_value': int(brightness), 'ramping_time': 0,
                'dimming_range': 0, 'store_final_value': 0, 'learn_button': 1,
                'switching_command': 1 if command.on and brightness > 0 else 0}


class CoverActuator(Actuator):
    """A shutter actuator (FSB14, FSB61, ...): reports the end position it reached.

    A real actuator reports the start of the movement and then its end position (or, when it is
    stopped in between, the runtime it travelled). The simulation drives to the end position -
    an intermediate one cannot be derived without the travel times of the actuator.
    """

    eep = 'G5-3F-7F'

    OPEN = 0x70
    CLOSED = 0x50

    def report(self, state: dict, command: Command) -> dict | None:
        if command.direction == 'up':
            return {'state': self.OPEN, 'time': 0, 'direction': 0}
        if command.direction == 'down':
            return {'state': self.CLOSED, 'time': 0, 'direction': 0}
        return None     # stop: there is no position to report


class HeatingActuator(Actuator):
    """A heating/cooling actuator (FHK14, FAE14, ...): acknowledges the target temperature."""

    eep = 'A5-10-06'

    ACTUATOR_RESPONSE_PRIORITY = 0x0F

    def report(self, state: dict, command: Command) -> dict | None:
        return {'target_temp': command.target_temperature or 0,
                'mode': command.mode if command.mode is not None else 0x70,
                'priority': self.ACTUATOR_RESPONSE_PRIORITY}


ACTUATORS: dict[str, Actuator] = {actuator.eep: actuator for actuator in
                                  (RelayActuator(), DimmerActuator(), CoverActuator(),
                                   HeatingActuator())}


def find_actuator(eep) -> Actuator | None:
    """The behaviour of a device EEP, or None if this EEP cannot be controlled."""
    return ACTUATORS.get(str(eep or '').upper())


def can_be_controlled(eep) -> bool:
    return find_actuator(eep) is not None


def answer_command(device, msg: ESP2Message, sender_eep: str = None) -> tuple[ESP2Message, dict] | None:
    """The status telegram a simulated actuator reports after a command.

    `device` is a `SimulatedDevice` (or anything with the same attributes). `sender_eep` is the
    profile of the sender the telegram came from - a device can be controlled by more than one
    (the sender of the automation system plus everything which was taught into it), and a wall
    switch speaks a different profile than a central command. Without it the sender of the
    automation system is assumed.

    Returns `(telegram, new state)`, or None when the telegram carries no command for this
    device. The new state is meant to be stored on the device, so a simulated actuator keeps its
    position: a cover which was closed stays closed until the next command.
    """
    sender_eep = sender_eep or getattr(device, 'sender_eep', None)
    platform = getattr(device, 'platform', None)
    if not sender_eep or platform not in ACTUATOR_PLATFORMS:
        return None

    actuator = find_actuator(getattr(device, 'eep', None))
    if actuator is None:
        return None

    state = dict(getattr(device, 'state', None) or {})
    command = decode_command(sender_eep, msg, previous_on=bool(state.get('_on')))
    if command is None:
        return None

    reported = actuator.report(state, command)
    if reported is None:
        return None

    state.update(reported)
    state['_on'] = bool(command.on)
    return encode_state_telegram(device.address, device.eep, state), state


def describe_actuators() -> list[dict]:
    """Which device EEPs the simulation can control, and with which sender EEPs."""
    return [{'eep': eep, 'behaviour': type(actuator).__name__,
             'description': (type(actuator).__doc__ or '').strip().split('\n')[0]}
            for eep, actuator in sorted(ACTUATORS.items())]
