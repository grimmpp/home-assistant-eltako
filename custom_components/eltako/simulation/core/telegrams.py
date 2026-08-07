"""Building the telegrams a simulated device sends.

A telegram is what makes the simulation indistinguishable from real hardware: it is encoded
from an EEP and its values exactly like a real device encodes its measurement, and it is turned
into a *received* telegram, so everything behind the gateway - entities, telegram log,
statistics, analysis - sees what it would see from a real device.
"""

from __future__ import annotations

import inspect

from eltakobus.eep import EEP
from eltakobus.message import ESP2Message, Regular4BSMessage, prettify

from .addressing import address_bytes
from .constants import (CENTRAL_COMMAND_FIELDS, DEFAULT_FIELD_VALUES, DEFAULT_STATE_BY_EEP,
                        ENUM_FIELDS, INTERNAL_STATE_PREFIX)
from .errors import SimulationError

# manufacturer id which a teach-in telegram carries (Eltako)
ELTAKO_MANUFACTURER_ID = 0x00B


def find_eep(eep: str):
    """The EEP class of 'A5-04-02'. Raises SimulationError if there is none."""
    try:
        return EEP.find(str(eep).upper())
    except Exception as e:      # noqa: BLE001 - the library raises KeyError/NotImplementedError
        raise SimulationError(f"'{eep}' is not a known EEP.") from e


def eep_fields(eep: str) -> list[str]:
    """Names of the values a telegram of this EEP carries (the constructor of its class)."""
    if str(eep).upper() == 'A5-38-08':
        return list(CENTRAL_COMMAND_FIELDS)
    eep_class = find_eep(eep)
    return [param.name for param in inspect.signature(eep_class.__init__).parameters.values()
            if param.name != 'self' and param.kind == param.POSITIONAL_OR_KEYWORD]


def default_state(eep: str) -> dict:
    """Start values for every field of an EEP.

    They are chosen so that a device which was just created sends a telegram its entity can
    really decode - a plain 0 is not a valid state for every profile (see DEFAULT_STATE_BY_EEP).
    """
    per_eep = DEFAULT_STATE_BY_EEP.get(str(eep).upper(), {})
    return {field: per_eep.get(field, DEFAULT_FIELD_VALUES.get(field, 0))
            for field in eep_fields(eep)}


### ---------------------------------------------------------------------------
### teach-in: how a device announces its profile
### ---------------------------------------------------------------------------

# What a device of this profile family sends when its teach-in button is pressed. Only 4BS names
# the profile in the telegram - that is a property of EnOcean, not of this simulation.
TEACH_IN_KINDS = {
    'A5': ('4bs', "A 4BS teach-in telegram which states the profile (function, type and "
                  "manufacturer). A receiver can identify the device from it without any doubt - "
                  "the telegram analysis marks such an EEP as 'confirmed'."),
    'D5': ('1bs', "A 1BS teach-in telegram (the LRN bit is cleared). 1BS carries no profile "
                  "numbers, so it is a 'learn me' signal, not a profile announcement."),
    'F6': ('rps', "RPS has no teach-in telegram at all: a receiver learns a rocker switch from a "
                  "normal button press. Therefore a press and its release are sent - exactly what "
                  "teaching in such a device does."),
}

# device EEPs of Eltako actuators. They are RPS on the wire (M5/G5) or 4BS (A5-38-08), but an
# actuator is never taught into anything - it is the one which learns a sender.
ACTUATOR_TEACH_IN_HINT = ("An actuator does not announce itself: the sender of the automation "
                          "system is taught into IT. Home Assistant does that with the teach-in "
                          "button of the device.")


def teach_in_kind(eep) -> str | None:
    """'4bs', '1bs', 'rps' - how a device of this profile announces itself, or None."""
    family = str(eep or '').upper().split('-')[0]
    # M5-38-08 and G5-3F-7F are Eltako's own names for RPS status telegrams
    family = {'M5': 'F6', 'G5': 'F6', 'H5': 'F6'}.get(family, family)
    kind = TEACH_IN_KINDS.get(family)
    return kind[0] if kind else None


def teach_in_description(eep) -> str:
    """What the teach-in button of this profile actually sends."""
    kind = teach_in_kind(eep)
    for family, (name, description) in TEACH_IN_KINDS.items():
        if name == kind:
            return description
    return ""


def has_teach_in_telegram(eep) -> bool:
    """True if a device of this profile can announce itself at all."""
    return teach_in_kind(eep) is not None


def public_state(state: dict) -> dict:
    """The state without the keys the simulation keeps for itself (e.g. '_on')."""
    return {key: value for key, value in (state or {}).items()
            if not str(key).startswith(INTERNAL_STATE_PREFIX)}


def coerce_number(value):
    """'21.5' -> 21.5, '0x70' -> 112, 'abc' -> 'abc' (the EEP decides what it accepts)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return text
    return value


def coerce_enum(eep_class, name: str, value):
    """Turn a plain number into the enum an EEP constructor expects (A5-10-06 mode/priority)."""
    enum_class = getattr(eep_class, ENUM_FIELDS.get(name, ''), None)
    if enum_class is None:
        return value
    try:
        number = int(coerce_number(value))
    except (TypeError, ValueError):
        return value
    if hasattr(enum_class, 'find_by_code'):
        # None is fine - the EEP falls back to its own default for an unknown code
        return enum_class.find_by_code(number)
    try:
        return enum_class(number)
    except ValueError:
        return value


def _build_central_command(address: bytes, fields: dict):
    """A5-38-08 from the flat fields of CENTRAL_COMMAND_FIELDS."""
    from eltakobus.eep import A5_38_08, CentralCommandDimming, CentralCommandSwitching

    value = lambda name, default=0: coerce_number((fields or {}).get(name, default))  # noqa: E731
    if value('command', 1) == 2:
        dimming = CentralCommandDimming(value('dimming_value'), value('ramping_time'),
                                        value('learn_button'), value('dimming_range', 1),
                                        value('store_final_value'), value('switching_command', 1))
        return A5_38_08(2, dimming=dimming).encode_message(address)
    switching = CentralCommandSwitching(value('time'), value('learn_button'), value('lock'),
                                        value('delay_or_duration'), value('switching_command'))
    return A5_38_08(1, switching=switching).encode_message(address)


def encode_eep_telegram(sender_id, eep: str, fields: dict = None) -> ESP2Message:
    """The telegram an EEP produces for the given field values, as it is *sent*.

    This is the generic encoder the simulation and the 'send telegram' form of the web ui share,
    so a hand written telegram and a simulated one are built in exactly the same way.
    """
    address = address_bytes(sender_id)
    eep_class = find_eep(eep)

    if eep_class.eep_string == 'A5-38-08':
        return _build_central_command(address, fields)

    args = {}
    for param in inspect.signature(eep_class.__init__).parameters.values():
        if param.name == 'self' or param.kind != param.POSITIONAL_OR_KEYWORD:
            continue
        value = coerce_number((fields or {}).get(param.name, 0))
        args[param.name] = coerce_enum(eep_class, param.name, value) \
            if param.name in ENUM_FIELDS else value
    return eep_class(**args).encode_message(address)


def as_incoming(msg: ESP2Message) -> ESP2Message:
    """Turn an encoded telegram into a received one.

    `EEP.encode_message()` builds a telegram which is *sent* (TRT, h_seq 3). What a gateway
    reads from its port is a received telegram (RRT, h_seq 0) - only with that byte does a
    simulated telegram look exactly like the telegram of a real device, in the entities as well
    as in the log and in the analysis.
    """
    body = bytearray(msg.body)
    body[0] = 11        # (0 << 5) + 11 = RRT
    return prettify(ESP2Message(bytes(body)))


def encode_state_telegram(address, eep: str, state: dict = None) -> ESP2Message:
    """The telegram a simulated device with this EEP sends for the given values."""
    values = dict(default_state(eep))
    values.update({key: value for key, value in public_state(state).items() if value is not None})
    return as_incoming(encode_eep_telegram(address, eep, values))


def encode_teach_in_telegram(address, eep: str,
                             manufacturer: int = ELTAKO_MANUFACTURER_ID) -> list[ESP2Message]:
    """The telegram(s) a device sends when its teach-in button is pressed.

    What that is depends on the profile family (see TEACH_IN_KINDS):

    * **4BS** (`A5-xx-xx`) - a real teach-in telegram which names function, type and manufacturer.
      A receiver identifies the device from it without any doubt.
    * **1BS** (`D5-xx-xx`) - a teach-in telegram with the LRN bit cleared. It carries no profile
      numbers; 1BS simply has none.
    * **RPS** (`F6-xx-xx`, and Eltako's `M5`/`G5` status telegrams) - RPS has no teach-in telegram.
      A receiver learns such a device from a button press, so the press and its release are sent.

    Returns a list, because the RPS case is two telegrams. Raises SimulationError for a profile
    which cannot announce itself at all.
    """
    kind = teach_in_kind(eep)
    parts = str(eep).upper().split('-')
    if kind is None or len(parts) != 3:
        raise SimulationError(f"A device with the profile '{eep}' cannot announce itself - "
                              f"only 4BS, 1BS and RPS profiles can.")

    if kind == '4bs':
        func = int(parts[1], 16)
        eep_type = int(parts[2], 16)
        data = bytes([
            (func << 2) | (eep_type >> 5),
            ((eep_type & 0x1F) << 3) | (manufacturer >> 8),
            manufacturer & 0xFF,
            0x80,           # LRN type 1, teach-in (variation 2)
        ])
        return [as_incoming(Regular4BSMessage(address_bytes(address), 0x00, data, True))]

    if kind == '1bs':
        # the LRN bit (DB0.3) is cleared in a teach-in telegram. The library has no class for it,
        # so the frame is built directly - it is a valid 1BS telegram, just not a 'regular' one.
        body = bytes([11, 0x06, 0x00, 0, 0, 0, *address_bytes(address), 0x00])
        return [as_incoming(ESP2Message(body))]

    # RPS: a press (energy bow set) and its release - what teaching in a rocker switch does
    press = encode_eep_telegram(address, 'F6-02-01',
                                {'rocker_first_action': 1, 'energy_bow': 1})
    release = encode_eep_telegram(address, 'F6-02-01',
                                  {'rocker_first_action': 1, 'energy_bow': 0})
    return [as_incoming(press), as_incoming(release)]


def encode_eltako_teach_in_telegram(address, payload) -> ESP2Message:
    """The ELTAKO teach-in telegram: a 4BS telegram with the payload of a *sender* profile.

    This is a different telegram than `encode_teach_in_telegram`, and it is used the other way
    round. The profile teach-in above is what a **sensor** sends to announce what it is; this one
    is what a **sender** sends so that an Eltako actuator takes it into its memory - the telegram
    the teach-in button of a device in Home Assistant produces (see catalog/teach_in.py, which
    holds the payload per sender EEP; the four data bytes are handed over, so the knowledge stays
    in one place).
    """
    data = bytes(payload or b'')
    if len(data) != 4:
        raise SimulationError(f"An Eltako teach-in telegram has four data bytes, got {len(data)}.")
    return as_incoming(Regular4BSMessage(address_bytes(address), 0x80, data, True))


def sender_of(msg) -> bytes | None:
    """Sender address of a telegram - the four bytes before the status byte of its body."""
    body = getattr(msg, 'body', b'')
    if len(body) < 5:
        return None
    return bytes(body[-5:-1])


def prettified(msg):
    """A telegram of its most specific class, so an EEP can decode it."""
    return prettify(msg) if type(msg) is ESP2Message else msg
