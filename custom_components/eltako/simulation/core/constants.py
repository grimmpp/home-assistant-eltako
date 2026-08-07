"""Names, tables and default values of the simulation.

Everything in here is data. It has no dependency on Home Assistant on purpose - see the
package documentation of `simulation/core`.
"""

from __future__ import annotations

import re

SIMULATOR_DEFAULT_NAME = "Simulator"

# 'serial port' of a simulated gateway. It is no file and is never opened - the name only has
# to be stable and unique: it identifies the gateway in the device registry and in its entry.
SIMULATOR_SERIAL_PATH_PREFIX = "simulator-"

# Base id a simulated gateway reports: FF-C0-<gateway>-00. A wireless base id starts with FF,
# and FF-C0-xx-xx is used by no Eltako hardware - so a simulated address is recognizable.
SIMULATOR_BASE_ID_PREFIX = "FF-C0"

# Sender ids of devices on a (simulated) bus are counted from this offset - the same convention
# the EnOcean Device Manager and the plug & play detection of this integration use.
LOCAL_SENDER_OFFSET = 0xB000

# how long a simulated actuator "needs" before it reports its new state
ACTUATOR_RESPONSE_DELAY = 0.05

# Range of the interval a device may repeat its telegram with. One second is the fastest which
# still is a measurement and not a flood; a day is the slowest which is still worth simulating
# (a real battery sensor reports every few minutes).
MIN_INTERVAL_SECONDS = 1
MAX_INTERVAL_SECONDS = 86400

# intervals the web ui offers as suggestions
INTERVAL_SUGGESTIONS = [5, 15, 30, 60, 300, 900]

ADDRESS_PATTERN = re.compile(r'^[0-9A-F]{2}(-[0-9A-F]{2}){3}$')

# Platforms a virtual device can be created for. An actuator is controlled by the automation
# system and therefore needs the sender address that system sends its commands with.
SIMULATED_PLATFORMS = {
    'sensor': {'label': "Sensor", 'actuator': False},
    'binary_sensor': {'label': "Binary sensor", 'actuator': False},
    'light': {'label': "Light", 'actuator': True},
    'switch': {'label': "Switch", 'actuator': True},
    'cover': {'label': "Cover", 'actuator': True},
    'climate': {'label': "Climate", 'actuator': True},
}

ACTUATOR_PLATFORMS = frozenset(platform for platform, info in SIMULATED_PLATFORMS.items()
                               if info['actuator'])

# gateway types which sit on an RS485 bus - their devices use local addresses (00-00-00-xx)
BUS_GATEWAY_TYPES = frozenset({'fam14', 'fgw14usb', 'ftd14'})

# Values a new device starts with. `learn_button` = 1 marks a telegram as a data telegram -
# several EEPs (e.g. A5-38-08) ignore a telegram without it, so a device which is created and
# triggered right away has to send it. The rest are plausible measurements.
DEFAULT_FIELD_VALUES = {
    'learn_button': 1,
    'temperature': 21,
    'humidity': 45,
    'current_temp': 20,
    'target_temp': 21,
    'mode': 0x70,           # A5-10-06 HeaterMode.NORMAL
    'priority': 0x0F,       # A5-10-06 ControllerPriority.ACTUATOR_ACK
    'energy_bow': 1,        # a rocker telegram without it is the 'button released' one
    'divisor': 1,           # A5-12-xx: the meter reading is divided by 10^divisor
    'illumination': 300,
    'supply_voltage': 3,
    'support_voltage': 3,
    'support_volrage_availability': 1,      # spelling of the eltakobus library
}

# Values which only make sense for one profile. A default of 0 is not always a state a device
# can report at all: a window handle encodes its position in the upper nibble of `movement`
# (0xF0 closed, 0xC0/0xE0 open, 0xD0 tilted) and nothing else can be decoded, and the central
# command has to say whether it switches (1) or dims (2). Without these a freshly created
# device would send a telegram which the receiving entity has to discard.
DEFAULT_STATE_BY_EEP = {
    'F6-10-00': {'movement': 0xF0},                 # window handle: closed
    'A5-38-08': {'command': 1, 'switching_command': 0, 'dimming_range': 0},   # switching, off
    'G5-3F-7F': {'state': 0x70},                    # cover: open
    # a weather station sends two kinds of telegram; only 'identifier' says which one, and
    # without it (0) the library cannot encode anything at all. 1 is the one with wind, dawn,
    # temperature and rain - 2 would be the three sun sensors.
    'A5-13-01': {'identifier': 1, 'dawn_sensor': 100, 'temperature': 20, 'wind_speed': 2},
}

# fields of an EEP constructor which take an enum of the EEP class instead of a plain number
ENUM_FIELDS = {'mode': 'HeaterMode', 'priority': 'ControllerPriority'}

# A5-38-08 (central command) takes nested objects in its constructor - these are the flat
# fields both of its variants are built from: command 1 switches, command 2 dims.
CENTRAL_COMMAND_FIELDS = ['command', 'switching_command', 'time', 'delay_or_duration', 'lock',
                          'dimming_value', 'ramping_time', 'dimming_range', 'store_final_value',
                          'learn_button']

# keys of a device state which are internal to the simulation (they are no telegram field)
INTERNAL_STATE_PREFIX = '_'
