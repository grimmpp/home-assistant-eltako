"""The starter set: what a fresh simulation contains.

Three gateways which cover the ways this integration talks to hardware - a LAN gateway, a USB
ESP3 stick and a FAM14 on the bus - and behind each of them the devices an installation
actually consists of: actuators for light, dimming, covers and heating/cooling, sensors for
temperature and humidity, motion, a 4-way wall switch and a window contact.
"""

from __future__ import annotations

from .addressing import is_bus_gateway_type
from .errors import SimulationError

# The gateways of the starter set. Each one is a *real* gateway type of the integration whose
# hardware is simulated, so everything behaves exactly like with the real device.
GATEWAY_PRESETS = [
    {'key': 'lan', 'device_type': 'mgw-lan', 'name': "Simulated LAN gateway",
     'description': "LAN gateway (ESP3, e.g. PioTek MGW): a wireless transceiver reached over "
                    "tcp. Its devices use wireless addresses of its base id range."},
    {'key': 'usb300', 'device_type': 'enocean-usb300', 'name': "Simulated USB300",
     'description': "USB stick (ESP3, e.g. EnOcean USB300): a wireless transceiver on a serial "
                    "port. Its devices use wireless addresses of its base id range."},
    {'key': 'fam14', 'device_type': 'fam14', 'name': "Simulated FAM14",
     'description': "Bus gateway (ESP2): its devices sit on the RS485 bus and therefore use "
                    "local addresses (00-00-00-xx) with senders at 00-00-B0-xx."},
]

# The devices every simulated gateway starts with. `hw_type` is the device on the bus,
# `hw_type_radio` the decentralized one - so one preset fits both kinds of gateway.
DEVICE_PRESETS = [
    {'key': 'light', 'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'name': "Light", 'hw_type': 'FSR14_4x', 'hw_type_radio': 'FSR61NP-230V',
     'description': "Switching relay - can be turned on and off."},
    {'key': 'dimmer', 'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'name': "Dimmable light", 'hw_type': 'FUD14', 'hw_type_radio': 'FUD61NP-230V',
     'description': "Dimmer - reports the brightness it was set to."},
    {'key': 'cover', 'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F',
     'name': "Cover", 'hw_type': 'FSB14', 'hw_type_radio': 'FSB61NP-230V',
     'description': "Shutter actuator - drives up and down."},
    {'key': 'climate', 'platform': 'climate', 'eep': 'A5-10-06', 'sender_eep': 'A5-10-06',
     'name': "Heating / cooling", 'hw_type': 'FHK14', 'hw_type_radio': 'FAE14SSR',
     'description': "Heating and cooling actuator - acknowledges the target temperature."},
    {'key': 'temperature', 'platform': 'sensor', 'eep': 'A5-04-02',
     'name': "Temperature and humidity", 'hw_type': 'FLGTF',
     'description': "Reports temperature and humidity."},
    {'key': 'motion', 'platform': 'binary_sensor', 'eep': 'A5-07-01',
     'name': "Motion", 'hw_type': 'FB55EB',
     'description': "Occupancy sensor - reports motion."},
    {'key': 'rocker', 'platform': 'binary_sensor', 'eep': 'F6-02-01',
     'name': "4-way wall switch", 'hw_type': 'F4T55E',
     'description': "Wall switch with four buttons - the triggered button is the value "
                    "'rocker_first_action' (0 = left bottom, 1 = left top, 2 = right bottom, "
                    "3 = right top)."},
    {'key': 'window', 'platform': 'binary_sensor', 'eep': 'F6-10-00',
     'name': "Window contact", 'hw_type': 'FTKE',
     'description': "Window/door contact - reports closed, open and tilted."},
]


def find_gateway_preset(key: str) -> dict:
    preset = next((preset for preset in GATEWAY_PRESETS if preset['key'] == str(key)), None)
    if preset is None:
        raise SimulationError(f"'{key}' is no known gateway preset. Available: "
                              f"{', '.join(preset['key'] for preset in GATEWAY_PRESETS)}.")
    return preset


def find_device_preset(key: str) -> dict:
    preset = next((preset for preset in DEVICE_PRESETS if preset['key'] == str(key)), None)
    if preset is None:
        raise SimulationError(f"'{key}' is no known device preset. Available: "
                              f"{', '.join(preset['key'] for preset in DEVICE_PRESETS)}.")
    return preset


def preset_hw_type(preset: dict, bus: bool) -> str | None:
    """The device of the catalog a preset imitates on this kind of gateway."""
    if bus:
        return preset.get('hw_type')
    return preset.get('hw_type_radio') or preset.get('hw_type')


def preset_device(gateway, preset: dict) -> dict:
    """One device of DEVICE_PRESETS, ready to be added to this simulated gateway."""
    return gateway.suggest_device(preset['platform'], preset['eep'], preset.get('sender_eep'),
                                 preset['name'], preset_hw_type(preset, gateway.is_bus_gateway))


def add_preset_devices(gateway, keys: list[str] = None, on_error=None) -> list:
    """Add the example devices to a simulated gateway (all of them by default)."""
    added = []
    for preset in DEVICE_PRESETS:
        if keys is not None and preset['key'] not in keys:
            continue
        try:
            added.append(gateway.add(preset_device(gateway, preset)))
        except SimulationError as e:
            if on_error:
                on_error(f"Cannot create the example device '{preset['key']}': {e}")
    return added


def describe_gateway_presets(existing_device_types=None) -> list[dict]:
    """The starter set, and whether a gateway of that type is already simulated."""
    existing = {str(device_type) for device_type in (existing_device_types or [])}
    return [{**preset, 'exists': preset['device_type'] in existing,
             'bus_gateway': is_bus_gateway_type(preset['device_type'])}
            for preset in GATEWAY_PRESETS]


def describe_device_presets() -> list[dict]:
    return [{'key': preset['key'], 'name': preset['name'], 'platform': preset['platform'],
             'eep': preset['eep'], 'description': preset.get('description', "")}
            for preset in DEVICE_PRESETS]
