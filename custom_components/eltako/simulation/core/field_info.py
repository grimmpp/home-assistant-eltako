"""What the values of a telegram mean - so that the right ones can be sent.

The fields of an EEP are the parameters of its constructor in the `eltakobus` library, and their
names alone do not say what to put in: `state`, `command`, `movement` or `dimming_range` are
plain numbers whose meaning is spread over the encoders of the library and the entity platforms
of this integration. A form which only offers `mode = 112` is a form nobody can fill in.

This module says per field what it is: a choice with named options, a number with a unit and a
range, or a flag. The web ui builds selects and number inputs from it (the send fields of every
device on the control page), and every value in here is the one the encoder of that profile
really writes into the telegram - the tables are taken from the encoders themselves, see the
comments at the single entries.

No dependency on Home Assistant, like everything in `simulation/core` - see the package
documentation.
"""

from __future__ import annotations

import inspect

from .constants import CENTRAL_COMMAND_FIELDS, ENUM_FIELDS

# --------------------------------------------------------------------------------------------
# choices: (EEP, field) -> [(value, label)]
#
# The value is what goes into the telegram. Where the label names a physical state ("on",
# "closed") it is the state *after* the telegram, as the receiving entity decodes it.
# --------------------------------------------------------------------------------------------

CHOICES: dict[tuple[str, str], list[tuple[int, str]]] = {
    # _EltakoSwitchingCommand: data[0] = 0x50 | state << 5
    ('M5-38-08', 'state'): [(1, "on"), (0, "off")],

    # _CentralCommand: data[0] = command. 1 switches, 2 dims - and which of the other fields
    # are read depends on it (see RELEVANT_FIELDS below).
    ('A5-38-08', 'command'): [(1, "switch"), (2, "dim")],
    ('A5-38-08', 'switching_command'): [(1, "on"), (0, "off")],
    # DB0.2 of the dimming variant: how the dimming value is to be read
    ('A5-38-08', 'dimming_range'): [(0, "value is 0-255"), (1, "value is 0-100 %")],
    ('A5-38-08', 'lock'): [(0, "not locked"), (1, "locked")],
    ('A5-38-08', 'delay_or_duration'): [(0, "the time is a switch-off delay"),
                                        (1, "the time is a switch-on duration")],
    ('A5-38-08', 'store_final_value'): [(0, "do not store"), (1, "store as the new default")],

    # _EltakoShutterCommand: data[2] = command. The values the cover platform sends.
    ('H5-3F-7F', 'command'): [(0x01, "up"), (0x02, "down"), (0x00, "stop")],

    # _EltakoShutterStatus: the RPS telegram an actuator reports its position with, and the
    # 4BS telegram with which it reports how long it really travelled.
    ('G5-3F-7F', 'state'): [(0x70, "top end position"), (0x50, "bottom end position"),
                            (0x01, "started to move up"), (0x02, "started to move down")],
    ('G5-3F-7F', 'direction'): [(0x01, "up"), (0x02, "down"), (0x00, "none")],

    # _SingleInputContact: data[0] bit 0
    ('D5-00-01', 'contact'): [(1, "closed"), (0, "open")],

    # _WindowHandle: the upper nibble is the position (WindowHandlePosition.get_position)
    ('F6-10-00', 'movement'): [(0xF0, "closed"), (0xE0, "open"), (0xD0, "tilted")],
}

# rocker switches: the same four actions in every application style
for _rocker_eep in ('F6-02-01', 'F6-02-02'):
    CHOICES[(_rocker_eep, 'rocker_first_action')] = [
        (1, "left rocker, top"), (0, "left rocker, bottom"),
        (3, "right rocker, top"), (2, "right rocker, bottom")]
    CHOICES[(_rocker_eep, 'rocker_second_action')] = [
        (1, "left rocker, top"), (0, "left rocker, bottom"),
        (3, "right rocker, top"), (2, "right rocker, bottom")]
    CHOICES[(_rocker_eep, 'energy_bow')] = [(1, "pressed"), (0, "released")]
    CHOICES[(_rocker_eep, 'second_action')] = [(0, "only one rocker"), (1, "a second rocker too")]

# choices which mean the same for every profile
COMMON_CHOICES: dict[str, list[tuple[int, str]]] = {
    # every 4BS/1BS telegram: 1 = a data telegram, 0 = a teach-in telegram. A receiver ignores
    # the values of a telegram with 0 - the teach-in has its own buttons.
    'learn_button': [(1, "data telegram"), (0, "teach-in telegram")],
    'day_night': [(0, "day"), (1, "night")],
    'rain_indication': [(0, "dry"), (1, "rain")],
    'hemisphere': [(0, "north"), (1, "south")],
    'pir_status': [(1, "movement"), (0, "no movement")],
    'occupancy_button': [(1, "pressed"), (0, "not pressed")],
    'identifier': [(1, "wind, dawn, temperature, rain"), (2, "the three sun sensors")],
}

# --------------------------------------------------------------------------------------------
# numbers: unit, range and what they mean
# --------------------------------------------------------------------------------------------

NUMBERS: dict[str, dict] = {
    'temperature': {'unit': "°C", 'min': -20, 'max': 60, 'step': 0.5},
    'current_temp': {'unit': "°C", 'min': 0, 'max': 40, 'step': 0.5},
    'target_temp': {'unit': "°C", 'min': 0, 'max': 40, 'step': 0.5},
    'humidity': {'unit': "%", 'min': 0, 'max': 100},
    'illumination': {'unit': "lx", 'min': 0, 'max': 2000},
    'dawn_sensor': {'unit': "lx", 'min': 0, 'max': 999},
    'wind_speed': {'unit': "m/s", 'min': 0, 'max': 70},
    'supply_voltage': {'unit': "V", 'min': 0, 'max': 5, 'step': 0.1},
    'support_voltage': {'unit': "V", 'min': 0, 'max': 5, 'step': 0.1},
    'meter_reading': {'min': 0},
    'divisor': {'min': 0, 'max': 3, 'help': "the reading is divided by 10^divisor"},
    'measurement_channel': {'min': 0, 'max': 15},
}

# numbers whose unit or range belongs to one profile only
PROFILE_NUMBERS: dict[tuple[str, str], dict] = {
    # _CentralCommand: data[1..2] = time * 10, so 0.1 s steps up to 6553.5 s
    ('A5-38-08', 'time'): {'unit': "s", 'min': 0, 'max': 6553.5, 'step': 0.1,
                           'help': "switch-off delay or switch-on duration - which one is "
                                   "decided by the field below"},
    ('A5-38-08', 'dimming_value'): {'min': 0, 'max': 255,
                                    'help': "0-100 when the range below says percent"},
    ('A5-38-08', 'ramping_time'): {'unit': "s", 'min': 0, 'max': 255,
                                   'help': "0 = jump to the value without dimming"},
    # _EltakoShutterCommand: data[1] = time in 100 ms steps, one byte
    ('H5-3F-7F', 'time'): {'unit': "0.1 s", 'min': 0, 'max': 255,
                           'help': "how long the cover travels - 255 = 25.5 s"},
    ('G5-3F-7F', 'time'): {'unit': "0.1 s", 'min': 0, 'max': 65535,
                           'help': "how long it really travelled"},
}

# Which fields a profile actually reads, depending on the value of another one. The central
# command writes completely different bytes for switching and for dimming - offering all ten
# fields at once is offering eight which do nothing.
CONDITIONAL_FIELDS: dict[str, dict] = {
    'A5-38-08': {
        'field': 'command',
        'relevant': {
            1: ['command', 'switching_command', 'time', 'delay_or_duration', 'lock',
                'learn_button'],
            2: ['command', 'switching_command', 'dimming_value', 'ramping_time',
                'dimming_range', 'store_final_value', 'learn_button'],
        },
    },
    'A5-13-01': {
        'field': 'identifier',
        'relevant': {
            1: ['identifier', 'dawn_sensor', 'temperature', 'wind_speed', 'day_night',
                'rain_indication', 'learn_button'],
            2: ['identifier', 'sun_west', 'sun_south', 'sun_east', 'hemisphere', 'learn_button'],
        },
    },
}


def _enum_options(eep_class, field: str) -> list[dict] | None:
    """Options of a field which takes an enum of the EEP class (A5-10-06 mode and priority).

    The enums carry their own text: `DefaultEnum` has a description, a plain `Enum` only its
    name. `find_by_code` decides which number belongs to a member, so the *code* is what has to
    go into the form - not the position in the enum.
    """
    enum_class = getattr(eep_class, ENUM_FIELDS.get(field, ''), None)
    if enum_class is None:
        return None

    # Several members can share one code (A5-10-06: 'Auto' and 'Thermostat' are both 0x0E) -
    # the telegram cannot tell them apart, so neither may the form pretend it can. They become
    # one option whose label names both.
    labels: dict = {}
    for member in enum_class:
        code = getattr(member, 'code', None)
        value = code if code is not None else member.value
        label = getattr(member, 'description', None) or member.name.replace('_', ' ').title()
        labels.setdefault(value, []).append(label)
    return [{'value': value, 'label': ' / '.join(names)} for value, names in labels.items()]


def describe_field(eep: str, field: str, eep_class=None) -> dict:
    """What this field of this profile is: a choice, a number with a unit, or a plain number."""
    eep = str(eep).upper()
    descriptor = {'name': field, 'kind': 'number'}

    options = _enum_options(eep_class, field) if eep_class is not None else None
    if options is None:
        choices = CHOICES.get((eep, field)) or COMMON_CHOICES.get(field)
        options = [{'value': value, 'label': label} for value, label in choices] if choices \
            else None

    if options:
        descriptor['kind'] = 'choice'
        descriptor['options'] = options
        return descriptor

    descriptor.update(PROFILE_NUMBERS.get((eep, field)) or NUMBERS.get(field) or {})
    return descriptor


def describe_fields(eep: str, fields: list[str], eep_class=None) -> list[dict]:
    """The description of every field of a profile, in the order of the form."""
    return [describe_field(eep, field, eep_class) for field in fields]


def conditional_fields(eep: str) -> dict | None:
    """Which fields are read for which value of the deciding field - None if all always are."""
    return CONDITIONAL_FIELDS.get(str(eep).upper())


def relevant_fields(eep: str, values: dict, fields: list[str] = None) -> list[str]:
    """The fields which really end up in the telegram for these values.

    Used by the tests and by the command line; the web ui does the same with the descriptor.
    """
    condition = conditional_fields(eep)
    if condition is None:
        return list(fields or [])
    try:
        key = int(float((values or {}).get(condition['field'], 0)))
    except (TypeError, ValueError):
        key = 0
    return list(condition['relevant'].get(key, fields or []))


def field_names_of(eep_class) -> list[str]:
    """The fields of an EEP class: the parameters of its constructor."""
    if getattr(eep_class, 'eep_string', None) == 'A5-38-08':
        return list(CENTRAL_COMMAND_FIELDS)
    return [param.name for param in inspect.signature(eep_class.__init__).parameters.values()
            if param.name != 'self' and param.kind == param.POSITIONAL_OR_KEYWORD]
