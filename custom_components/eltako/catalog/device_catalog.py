"""Central catalog of known Eltako/EnOcean devices.

Single source of the device knowledge used by the integration:

* the device form of the web ui offers these devices as templates - selecting a device
  prefills its EEP and sender EEP (like the device list of the EnOcean Device Manager)
* the device page describes identified bus devices with it (see bus_members.py)

The catalog is served to the frontend through the form websocket (eltako/devices/form),
so the web ui never hardcodes device knowledge - it renders what this module delivers.

Ported from the EEP_MAPPING of the EnOcean Device Manager
(https://github.com/grimmpp/enocean-device-manager, eo_man/data/data_helper.py, MIT,
same author as this integration). One physical device can appear several times when it
speaks more than one EEP (e.g. FTS14EM inputs, F3Z14D meters, FLGTF air quality).
The first entry of a hw type is its primary use.

Entry fields:
    hw_type                device name as printed on the housing (FSR14_4x, FUD61NP-230V)
    brand                  manufacturer
    description            what the device is
    platform               home assistant platform of the template (None for gateways)
    eep                    EEP the device sends with
    sender_eep             EEP home assistant sends commands with (actuators only)
    pct14_function_group   where the sender id is entered when teaching in with PCT14
    pct14_key_function     key function of the teach-in entry
    address_count          bus positions / addresses the device occupies
    bus_device             True for devices mounted on the RS485 bus (series 14)
"""

from __future__ import annotations

from ..const import LOGGER  # noqa: F401 - imported for consistency with the other modules

GATEWAY_DOCS = 'https://github.com/grimmpp/home-assistant-eltako/tree/main/docs/gateways'

DEVICE_CATALOG: list[dict] = [
    # gateways (no platform - they are added as gateway, not as device). `gateway_type`
    # matches GatewayDeviceType of this integration.
    {'hw_type': 'FAM14', 'brand': 'ELTAKO', 'description': 'Bus Gateway', 'bus_device': True,
     'gateway_type': 'fam14', 'docs': GATEWAY_DOCS},
    {'hw_type': 'FGW14_USB', 'brand': 'ELTAKO', 'description': 'Bus Gateway', 'bus_device': True,
     'gateway_type': 'fgw14usb', 'docs': GATEWAY_DOCS},
    {'hw_type': 'FTD14', 'brand': 'ELTAKO', 'description': 'Bus Gateway', 'bus_device': True,
     'gateway_type': 'ftd14', 'docs': GATEWAY_DOCS},
    {'hw_type': 'FGW14', 'brand': 'ELTAKO', 'description': 'Bus Gateway', 'bus_device': True},
    {'hw_type': 'FAM-USB', 'brand': 'ELTAKO', 'description': 'USB Gateway (ESP2)',
     'gateway_type': 'fam-usb', 'docs': GATEWAY_DOCS},
    {'hw_type': 'USB300', 'brand': 'EnOcean', 'description': 'USB Gateway (ESP3)',
     'gateway_type': 'enocean-usb300', 'docs': GATEWAY_DOCS},
    {'hw_type': 'MGW (LAN)', 'brand': 'PioTek', 'description': 'LAN Gateway (ESP3)',
     'gateway_type': 'lan', 'docs': GATEWAY_DOCS},
    {'hw_type': 'MGW (USB)', 'brand': 'PioTek', 'description': 'USB Gateway (ESP3)',
     'gateway_type': 'esp3-gateway', 'docs': GATEWAY_DOCS},

    # wired inputs (bus)
    {'hw_type': 'FTS14EM', 'brand': 'ELTAKO', 'description': 'Wired inputs (switches, contacts)',
     'platform': 'binary_sensor', 'eep': 'F6-02-01', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FTS14EM', 'brand': 'ELTAKO', 'description': 'Wired rocker switch (US style)',
     'platform': 'binary_sensor', 'eep': 'F6-02-02', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FTS14EM', 'brand': 'ELTAKO', 'description': 'Wired window handle',
     'platform': 'binary_sensor', 'eep': 'F6-10-00', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FTS14EM', 'brand': 'ELTAKO', 'description': 'Wired contact sensor',
     'platform': 'binary_sensor', 'eep': 'D5-00-01', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FTS14EM', 'brand': 'ELTAKO', 'description': 'Wired occupancy sensor',
     'platform': 'binary_sensor', 'eep': 'A5-08-01', 'address_count': 1, 'bus_device': True},

    # wireless pushbuttons
    {'hw_type': 'FT55', 'brand': 'ELTAKO', 'description': 'Wireless 4-way pushbutton',
     'platform': 'binary_sensor', 'eep': 'F6-02-01', 'address_count': 1},
    {'hw_type': 'F4T55E', 'brand': 'ELTAKO', 'description': 'Wireless 4-way pushbutton (E-Design55)',
     'platform': 'binary_sensor', 'eep': 'F6-02-01', 'address_count': 1},
    {'hw_type': 'FMH1W', 'brand': 'ELTAKO', 'description': 'Wireless single button',
     'platform': 'binary_sensor', 'eep': 'F6-01-01', 'address_count': 1},

    # window and door contacts
    {'hw_type': 'FFTE', 'brand': 'ELTAKO', 'description': 'Window/door contact',
     'platform': 'binary_sensor', 'eep': 'F6-10-00', 'address_count': 1},
    {'hw_type': 'FTKE', 'brand': 'ELTAKO', 'description': 'Window/door contact',
     'platform': 'binary_sensor', 'eep': 'F6-10-00', 'address_count': 1},
    {'hw_type': 'FTK', 'brand': 'ELTAKO', 'description': 'Window/door contact',
     'platform': 'binary_sensor', 'eep': 'F6-10-00', 'address_count': 1},
    {'hw_type': 'FSM60B', 'brand': 'ELTAKO', 'description': 'Digital input with battery status',
     'platform': 'binary_sensor', 'eep': 'A5-30-01', 'address_count': 1},

    # occupancy
    {'hw_type': 'FB55EB', 'brand': 'ELTAKO', 'description': 'Occupancy sensor',
     'platform': 'binary_sensor', 'eep': 'A5-07-01', 'address_count': 1},

    # metering (bus)
    {'hw_type': 'FSDG14', 'brand': 'ELTAKO', 'description': 'Electricity Meter',
     'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'F3Z14D', 'brand': 'ELTAKO', 'description': 'Electricity/Gas/Water Meter',
     'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 3, 'bus_device': True},
    {'hw_type': 'F3Z14D', 'brand': 'ELTAKO', 'description': 'Gas Meter',
     'platform': 'sensor', 'eep': 'A5-12-02', 'address_count': 3, 'bus_device': True},
    {'hw_type': 'F3Z14D', 'brand': 'ELTAKO', 'description': 'Water Meter',
     'platform': 'sensor', 'eep': 'A5-12-03', 'address_count': 3, 'bus_device': True},
    {'hw_type': 'FWZ14_65A', 'brand': 'ELTAKO', 'description': 'Electricity Meter',
     'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 1, 'bus_device': True},

    # weather stations
    {'hw_type': 'FWG14MS', 'brand': 'ELTAKO', 'description': 'Weather Station Gateway',
     'platform': 'sensor', 'eep': 'A5-13-01', 'address_count': 1, 'bus_device': True},
    {'hw_type': 'MS', 'brand': 'ELTAKO', 'description': 'Weather Station',
     'platform': 'sensor', 'eep': 'A5-13-01', 'address_count': 1},
    {'hw_type': 'WMS', 'brand': 'ELTAKO', 'description': 'Weather Station',
     'platform': 'sensor', 'eep': 'A5-13-01', 'address_count': 1},
    {'hw_type': 'FWS61', 'brand': 'ELTAKO', 'description': 'Weather Station',
     'platform': 'sensor', 'eep': 'A5-13-01', 'address_count': 1},

    # temperature and humidity
    {'hw_type': 'FLGTF', 'brand': 'ELTAKO', 'description': 'Temperature and Humidity Sensor',
     'platform': 'sensor', 'eep': 'A5-04-02', 'address_count': 1},
    {'hw_type': 'FLGTF', 'brand': 'ELTAKO', 'description': 'Air Quality, Temperature and Humidity Sensor',
     'platform': 'sensor', 'eep': 'A5-09-0C', 'address_count': 1},
    {'hw_type': 'FLT58', 'brand': 'ELTAKO', 'description': 'Temperature and Humidity Sensor',
     'platform': 'sensor', 'eep': 'A5-04-02', 'address_count': 1},
    {'hw_type': 'FFT60', 'brand': 'ELTAKO', 'description': 'Temperature and Humidity Sensor',
     'platform': 'sensor', 'eep': 'A5-04-02', 'address_count': 1},
    {'hw_type': 'FTFSB', 'brand': 'ELTAKO', 'description': 'Temperature and Humidity Sensor',
     'platform': 'sensor', 'eep': 'A5-04-02', 'address_count': 1},

    # light sensors
    {'hw_type': 'FHD60SB', 'brand': 'ELTAKO', 'description': 'Twilight and daylight sensor',
     'platform': 'sensor', 'eep': 'A5-06-01', 'address_count': 1},

    # occupancy with light and temperature
    {'hw_type': 'FABH65S', 'brand': 'ELTAKO', 'description': 'Light, temperature and occupancy sensor',
     'platform': 'sensor', 'eep': 'A5-08-01', 'address_count': 1},
    {'hw_type': 'FBH65', 'brand': 'ELTAKO', 'description': 'Light, temperature and occupancy sensor',
     'platform': 'sensor', 'eep': 'A5-08-01', 'address_count': 1},
    {'hw_type': 'FBH65S', 'brand': 'ELTAKO', 'description': 'Light, temperature and occupancy sensor',
     'platform': 'sensor', 'eep': 'A5-08-01', 'address_count': 1},
    {'hw_type': 'FBH65TF', 'brand': 'ELTAKO', 'description': 'Light, temperature and occupancy sensor',
     'platform': 'sensor', 'eep': 'A5-08-01', 'address_count': 1},

    # thermostats (as sensor)
    {'hw_type': 'FUTH', 'brand': 'ELTAKO', 'description': 'Temperature sensor and controller',
     'platform': 'sensor', 'eep': 'A5-10-06', 'address_count': 1},
    {'hw_type': 'FUTH', 'brand': 'ELTAKO', 'description': 'Temperature and humidity sensor and controller',
     'platform': 'sensor', 'eep': 'A5-10-12', 'address_count': 1},
    {'hw_type': 'FTR78S', 'brand': 'ELTAKO', 'description': 'Thermostat',
     'platform': 'sensor', 'eep': 'A5-10-03', 'address_count': 1},

    # dimmers (bus)
    {'hw_type': 'FUD14', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 3, 'pct14_key_function': 32, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FUD14_800W', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 3, 'pct14_key_function': 32, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FSG14_1_10V', 'brand': 'ELTAKO', 'description': 'Dimming for electr. ballasts (1-10V)',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 3, 'pct14_key_function': 32, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FDG14', 'brand': 'ELTAKO', 'description': 'Dali Gateway',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 1, 'pct14_key_function': 32, 'address_count': 16, 'bus_device': True},
    {'hw_type': 'FD2G14', 'brand': 'ELTAKO', 'description': 'Dali Gateway',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 1, 'pct14_key_function': 32, 'address_count': 16, 'bus_device': True},

    # relays (bus)
    {'hw_type': 'FMZ14', 'brand': 'ELTAKO', 'description': 'Relay (multifunction)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'F6-02-01',
     'pct14_function_group': 1, 'pct14_key_function': 1, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FSR14', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FSR14_1x', 'brand': 'ELTAKO', 'description': 'Relay (1 channel)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 1, 'bus_device': True},
    {'hw_type': 'FSR14_2x', 'brand': 'ELTAKO', 'description': 'Relay (2 channels)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 2, 'bus_device': True},
    {'hw_type': 'FSR14_4x', 'brand': 'ELTAKO', 'description': 'Relay (4 channels)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 4, 'bus_device': True},
    {'hw_type': 'FSR14M_2x', 'brand': 'ELTAKO', 'description': 'Relay (2 channels, with metering)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 2, 'bus_device': True},
    # metering feature of the FSR14M_2x (eo_man: 'FSR14M_2x-feature')
    {'hw_type': 'FSR14M_2x', 'brand': 'ELTAKO', 'description': 'Relay power meter',
     'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 2, 'bus_device': True},
    {'hw_type': 'F4SR14_LED', 'brand': 'ELTAKO', 'description': 'Relay for LED (4 channels)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08',
     'pct14_function_group': 2, 'pct14_key_function': 51, 'address_count': 4, 'bus_device': True},

    # covers (bus)
    {'hw_type': 'FSB14', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F',
     'pct14_function_group': 2, 'pct14_key_function': 31, 'address_count': 2, 'bus_device': True},

    # heating and cooling (bus)
    {'hw_type': 'FHK14', 'brand': 'ELTAKO', 'description': 'Heating/Cooling',
     'platform': 'climate', 'eep': 'A5-10-06', 'sender_eep': 'A5-10-06',
     'pct14_function_group': 3, 'pct14_key_function': 65, 'address_count': 2, 'bus_device': True},
    {'hw_type': 'F4HK14', 'brand': 'ELTAKO', 'description': 'Heating/Cooling (4 channels)',
     'platform': 'climate', 'eep': 'A5-10-06', 'sender_eep': 'A5-10-06',
     'pct14_function_group': 3, 'pct14_key_function': 65, 'address_count': 4, 'bus_device': True},
    {'hw_type': 'FAE14SSR', 'brand': 'ELTAKO', 'description': 'Heating/Cooling',
     'platform': 'climate', 'eep': 'A5-10-06', 'sender_eep': 'A5-10-06',
     'pct14_function_group': 3, 'pct14_key_function': 65, 'address_count': 2, 'bus_device': True},

    # other bus modules (no template - kept for the device page)
    {'hw_type': 'FMSR14', 'brand': 'ELTAKO', 'description': 'Multisensor relay', 'bus_device': True},
    {'hw_type': 'FSU14', 'brand': 'ELTAKO', 'description': 'Clock/timer module', 'bus_device': True},

    # decentralized relays
    {'hw_type': 'FMZ61', 'brand': 'ELTAKO', 'description': 'Relay (multifunction)',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'F6-02-01', 'address_count': 1},
    {'hw_type': 'FSR61-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSR61NP-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSR61/8-24V UC', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSR61G-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSR61LN-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 2},
    {'hw_type': 'FLC61NP-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FR62-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FR62NP-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FL62-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FL62NP-230V', 'brand': 'ELTAKO', 'description': 'Relay',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSSA-230V', 'brand': 'ELTAKO', 'description': 'Socket switch actuator',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSVA-230V-10A', 'brand': 'ELTAKO', 'description': 'Socket switch actuator',
     'platform': 'light', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FSVA-230V-10A', 'brand': 'ELTAKO', 'description': 'Socket switch actuator (power meter)',
     'platform': 'sensor', 'eep': 'A5-12-01', 'address_count': 1},

    # decentralized dimmers
    {'hw_type': 'FUD61NP-230V', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FUD61NPN-230V', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FD62NP-230V', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},
    {'hw_type': 'FD62NPN-230V', 'brand': 'ELTAKO', 'description': 'Light dimmer',
     'platform': 'light', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08', 'address_count': 1},

    # decentralized covers
    {'hw_type': 'FSB61-230V', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'address_count': 1},
    {'hw_type': 'FSB61NP-230V', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'address_count': 1},
    {'hw_type': 'FJ62/12-36V DC', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'address_count': 1},
    {'hw_type': 'FJ62NP-230V', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'address_count': 1},
    {'hw_type': 'FSUD-230V', 'brand': 'ELTAKO', 'description': 'Cover',
     'platform': 'cover', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'address_count': 1},
]

# hw type -> primary catalog entry (first occurrence wins - it is the primary use)
_PRIMARY_BY_HW_TYPE: dict[str, dict] = {}
for _entry in DEVICE_CATALOG:
    _PRIMARY_BY_HW_TYPE.setdefault(_entry['hw_type'], _entry)


#: how the brand is written wherever a text is shown to a user. The `eltakobus` library spells it
#: 'Eltako' in its profile descriptions; those descriptions end up in the device form, on the help
#: page and in the generated documentation, so they are adjusted while they are rendered - the
#: library itself and every identifier stay untouched.
BRAND = 'ELTAKO'


def as_display_text(text: str | None) -> str:
    """A text of the library, written the way the ui writes the brand."""
    return (text or '').replace('Eltako', BRAND)


def normalize_hw_type(name: str | None) -> str:
    """Device name of any tool -> comparable key ('FSR14-4x', 'fsr14 4x' -> 'FSR14_4X').

    Other tools write the same device differently than the housing does: PCT14 exports
    'FSR14-4x' and 'FUD14/800W', the EnOcean Device Manager 'FSR14_4x'. Separators are
    therefore all the same character and the case is dropped.
    """
    key = str(name or '').strip().upper()
    for character in ('-', ' ', '/', '.'):
        key = key.replace(character, '_')
    return key


# normalized hw type -> primary catalog entry
_PRIMARY_BY_NORMALIZED: dict[str, dict] = {}
for _entry in DEVICE_CATALOG:
    _PRIMARY_BY_NORMALIZED.setdefault(normalize_hw_type(_entry['hw_type']), _entry)


def find_hw_type(name: str | None) -> dict:
    """Primary catalog entry of a device name written by another tool (PCT14, eo_man).

    Falls back to the part before the first variant separator, so a device which only
    differs in a detail the catalog does not distinguish is still found
    ('FUD14/800W' -> FUD14_800W if known, otherwise FUD14).
    """
    key = normalize_hw_type(name)
    if not key:
        return {}
    entry = _PRIMARY_BY_NORMALIZED.get(key)
    if entry is not None:
        return entry
    base = normalize_hw_type(str(name).split('/')[0])
    return _PRIMARY_BY_NORMALIZED.get(base, {})


# gateway type of this integration (GatewayDeviceType) -> catalog entry of that gateway
_GATEWAY_BY_TYPE: dict[str, dict] = {}
for _entry in DEVICE_CATALOG:
    if _entry.get('gateway_type'):
        _GATEWAY_BY_TYPE.setdefault(_entry['gateway_type'], _entry)


def describe_gateway_type(gateway_type: str | None) -> dict:
    """Catalog entry of a gateway type, e.g. 'fam14' -> the FAM14 entry."""
    if not gateway_type:
        return {}
    return _GATEWAY_BY_TYPE.get(str(gateway_type), {})


def describe_hw_type(hw_type: str | None) -> dict:
    """Primary catalog entry of a hw type (e.g. for a bus device identified by discovery)."""
    if not hw_type:
        return {}
    return _PRIMARY_BY_HW_TYPE.get(hw_type, {})


def get_device_templates(platform: str, supported_eeps: list[str] = None,
                         supported_sender_eeps: list[str] = None) -> list[dict]:
    """Device templates of one platform for the device form of the web ui.

    A template carries everything the form prefills when the device is selected. Templates
    whose EEP the platform schema does not support are dropped (safety net - the catalog
    must never offer something the validation would reject).
    """
    templates = []
    for entry in DEVICE_CATALOG:
        if entry.get('platform') != platform or not entry.get('eep'):
            continue
        if supported_eeps is not None and entry['eep'] not in supported_eeps:
            continue
        sender_eep = entry.get('sender_eep')
        if sender_eep and supported_sender_eeps is not None and sender_eep not in supported_sender_eeps:
            sender_eep = None

        label = f"{entry['hw_type']} - {entry['description']}"
        same_hw = [e for e in DEVICE_CATALOG if e['hw_type'] == entry['hw_type']
                   and e.get('platform') == platform and e.get('eep')]
        if len(same_hw) > 1:
            label += f" ({entry['eep']})"

        template = {
            'value': f"{entry['hw_type']}|{entry['eep']}",
            'label': label,
            'hw_type': entry['hw_type'],
            'description': entry['description'],
            'eep': entry['eep'],
        }
        if sender_eep:
            template['sender_eep'] = sender_eep
        if entry.get('pct14_function_group'):
            template['pct14_function_group'] = entry['pct14_function_group']
            template['pct14_key_function'] = entry['pct14_key_function']
        if entry.get('address_count'):
            template['address_count'] = entry['address_count']
        templates.append(template)

    templates.sort(key=lambda t: t['label'])
    return templates
