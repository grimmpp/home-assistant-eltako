"""The simulation itself - EnOcean gateways and devices which do not exist.

This package has **no Home Assistant import**. It only needs `eltakobus` and the standard
library, so it can be moved into a library of its own (or used from a script or a test) without
touching a line of its logic:

    from custom_components.eltako.simulation import core as sim

    model = sim.SimulationModel()
    gateway = model.add_gateway(2, 'fam14')                  # a simulated FAM14
    sim.add_preset_devices(gateway)                          # the example devices
    sensor = gateway.find('00-00-00-05')
    sensor.apply_state({'temperature': 21.5, 'humidity': 45})
    telegram = sensor.state_telegram()                       # -> inject it into a gateway

Where things live:

    constants.py    names, platform table, default values
    errors.py       SimulationError
    addressing.py   which address a gateway and its devices get
    telegrams.py    encoding the telegram a device sends (state and teach-in)
    field_info.py   what the values of a telegram mean: choices, units, ranges
    devices.py      SimulatedDevice - one virtual device
    actuators.py    how an actuator reacts to a command (one class per kind)
    model.py        SimulatedGateway and SimulationModel - the whole simulation as data
    presets.py      the starter set: LAN gateway, USB300, FAM14 and their devices

Everything around it - storage, the gateway object of the integration, the websocket api of the
web ui, the command line - lives one level up in `simulation/`.
"""

from .actuators import (ACTUATORS, SENDER_DECODERS, Actuator, Command, CoverActuator,      # noqa: F401
                        DimmerActuator, HeatingActuator, RelayActuator, answer_command,
                        can_be_controlled, decode_command, describe_actuators, find_actuator)
from .addressing import (address_bytes, address_to_int, default_base_id, device_address,  # noqa: F401
                         index_of_address, int_to_address, is_bus_gateway_type,
                         is_simulator_serial_path, next_free_index, normalize_address,
                         sender_address, serial_path, validate_hosted_address,
                         wireless_address_range)
from .constants import (ACTUATOR_PLATFORMS, ACTUATOR_RESPONSE_DELAY, BUS_GATEWAY_TYPES,   # noqa: F401
                        CENTRAL_COMMAND_FIELDS, DEFAULT_FIELD_VALUES, DEFAULT_STATE_BY_EEP,
                        ENUM_FIELDS, INTERVAL_SUGGESTIONS, LOCAL_SENDER_OFFSET,
                        MAX_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS, SIMULATED_PLATFORMS,
                        SIMULATOR_BASE_ID_PREFIX, SIMULATOR_DEFAULT_NAME,
                        SIMULATOR_SERIAL_PATH_PREFIX)
from .devices import SimulatedDevice                                                      # noqa: F401
from .errors import SimulationError                                                       # noqa: F401
from .field_info import (CHOICES, COMMON_CHOICES, CONDITIONAL_FIELDS, conditional_fields,  # noqa: F401
                         describe_field, describe_fields, field_names_of, relevant_fields)
from .model import SimulatedGateway, SimulationModel                                      # noqa: F401
from .presets import (DEVICE_PRESETS, GATEWAY_PRESETS, add_preset_devices,                # noqa: F401
                      describe_device_presets, describe_gateway_presets, find_device_preset,
                      find_gateway_preset, preset_device, preset_hw_type)
from .telegrams import (TEACH_IN_KINDS, as_incoming, default_state, eep_fields,             # noqa: F401
                        encode_eep_telegram, encode_eltako_teach_in_telegram,
                        encode_state_telegram, encode_teach_in_telegram,
                        find_eep, has_teach_in_telegram, prettified, public_state, sender_of,
                        teach_in_description, teach_in_kind)
