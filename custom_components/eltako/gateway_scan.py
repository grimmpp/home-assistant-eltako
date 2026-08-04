"""Scan for serial ports which could host an EnOcean gateway.

`gateway.detect()` only returns a list of paths. For setting up a gateway that is not enough:
the user needs to know which stick is behind a port, which port is already in use and which
`device_type` fits. This module collects that information from the usb descriptors of
/dev/serial/by-id and offers it to the web ui.

Nothing is opened or written here - the scan is completely passive and therefore safe to run
while the gateways are connected.
"""

from __future__ import annotations

import glob
import os

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import *

LOG_PREFIX_SCAN = "Gateway Scan"

SERIAL_BY_ID_DIR = "/dev/serial/by-id"
SERIAL_BY_PATH_DIR = "/dev/serial/by-path"

# /dev/serial/by-id is created by udev and does NOT exist inside a docker container, where only
# the device nodes themselves are passed through. Therefore the devices are also globbed
# directly and the usb information is read from sysfs, which is available in the container.
DEVICE_GLOBS = ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/serial[0-9]*"]

# relative paths below /sys/class/tty/<device>/device which hold the usb descriptor
SYSFS_FIELDS = {
    'manufacturer': ["../../manufacturer", "../manufacturer", "../../../manufacturer"],
    'product': ["../../product", "../product", "../../../product"],
    'serial_number': ["../../serial", "../serial", "../../../serial"],
    'interface_name': ["../interface", "interface"],
}

# usb descriptor fragment -> (suggested device types, hint). The first type is the most likely.
# The descriptor cannot identify an Eltako device reliably (most use the same FTDI chip),
# so this is a hint and never an automatism.
KNOWN_DEVICES = [
    ("enocean programmer", [GatewayDeviceType.GatewayEltakoFAMUSB.value, GatewayDeviceType.EnOceanUSB300.value],
     "EnOcean USB stick / programmer - this descriptor is used by the Eltako FAM-USB (ESP2 at "
     "9600 baud) and by ESP3 sticks (57600 baud). Such devices expose TWO ports (if00/if01, e.g. "
     "...600 and ...601) and only the SECOND one carries the telegrams - a FAM-USB answers on "
     "if01. If the gateway stays disconnected, use the other port."),
    ("USB300", [GatewayDeviceType.EnOceanUSB300.value],
     "EnOcean USB300 transceiver (ESP3, 57600 baud)."),
    ("FT232R", [GatewayDeviceType.GatewayEltakoFGW14USB.value, GatewayDeviceType.GatewayEltakoFAM14.value,
                GatewayDeviceType.GatewayEltakoFAMUSB.value],
     "FTDI serial adapter - used by Eltako FGW14-USB and FAM14 (both ESP2 at 57600 baud) and by "
     "the FAM-USB (ESP2 at 9600 baud). The type cannot be detected from the usb descriptor."),
    ("FT2232", [GatewayDeviceType.GatewayEltakoFGW14USB.value],
     "FTDI dual port adapter. Only one of its ports is usually connected to the bus."),
    ("CP210", [GatewayDeviceType.ESP3.value],
     "Silicon Labs serial adapter, often used by ESP3 gateways."),
]


def _read_link(directory: str) -> dict[str, str]:
    """symlink name -> device path, e.g. usb-FTDI_...-if00-port0 -> /dev/ttyUSB0"""
    result = {}
    try:
        for name in os.listdir(directory):
            link = os.path.join(directory, name)
            try:
                result[name] = os.path.realpath(link)
            except OSError:
                continue
    except OSError:
        pass        # directory does not exist (no serial device at all)
    return result


SYSFS_TTY_DIR = "/sys/class/tty"


def _read_sysfs_info(device: str, sysfs_tty_dir: str = SYSFS_TTY_DIR) -> dict:
    """Read the usb descriptor of a tty device from sysfs (works inside a container)."""
    base = os.path.join(sysfs_tty_dir, os.path.basename(device), "device")
    if not os.path.exists(base):
        return {}

    info = {}
    for key, candidates in SYSFS_FIELDS.items():
        for candidate in candidates:
            # deliberately no normpath: '/sys/class/tty/ttyUSB0/device' is a symlink and
            # normpath would resolve '..' textually, which points to the wrong directory.
            path = os.path.join(base, candidate)
            try:
                with open(path, encoding='utf-8', errors='replace') as handle:
                    value = handle.read().strip()
                if value:
                    info[key] = value
                    break
            except OSError:
                continue
    return info


def _describe_descriptor(descriptor: str) -> tuple[list[str], str]:
    """Match against the usb text. by-id uses underscores, sysfs uses spaces - normalize both."""
    haystack = descriptor.lower().replace('_', ' ')
    for fragment, types, hint in KNOWN_DEVICES:
        if fragment.lower().replace('_', ' ') in haystack:
            return types, hint
    return [], ""


def _pretty_name(descriptor: str) -> str:
    """'usb-EnOcean_GmbH_EnOcean_Programmer_V3.2_FT7YTP3Y-if01-port0' -> readable name."""
    name = descriptor
    for prefix in ("usb-",):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.replace("_", " ")


def _pyserial_ports() -> list[dict]:
    """Serial ports enumerated by pyserial - works on linux, macOS and windows."""
    try:
        from serial.tools import list_ports
    except ImportError:     # pragma: no cover - pyserial is a hard dependency
        return []

    ports = []
    try:
        for port in list_ports.comports():
            ports.append({
                'device': port.device,
                'manufacturer': getattr(port, 'manufacturer', None),
                'product': getattr(port, 'product', None) or getattr(port, 'description', None),
                'serial_number': getattr(port, 'serial_number', None),
                'interface_name': getattr(port, 'interface', None),
            })
    except Exception as e:  # noqa: BLE001 - enumeration must never break the scan
        LOGGER.debug(f"[{LOG_PREFIX_SCAN}] pyserial enumeration failed: {e}")
    return ports


def scan_serial_ports() -> list[dict]:
    """All serial ports incl. usb descriptor and a suggestion for the device type."""
    by_id = _read_link(SERIAL_BY_ID_DIR)
    by_path = _read_link(SERIAL_BY_PATH_DIR)

    ports: dict[str, dict] = {}

    def entry_for(device: str) -> dict:
        return ports.setdefault(os.path.realpath(device), {
            'device': device, 'by_id': None, 'by_path': None, 'descriptor': None,
            'name': os.path.basename(device), 'interface': None,
            'suggested_device_types': [], 'hint': "",
        })

    # 1) the device nodes themselves - the only source which also works inside a container
    for pattern in DEVICE_GLOBS:
        for device in glob.glob(pattern):
            entry_for(device)

    # 1b) pyserial enumeration - the globs and udev above are linux specific, this also
    # finds COM3 on windows and /dev/cu.usbserial-* on macOS (relevant for the standalone
    # runtime, which runs directly on the developer machine)
    for info in _pyserial_ports():
        entry = entry_for(info['device'])
        for key in ('manufacturer', 'product', 'serial_number', 'interface_name'):
            if info.get(key) and not entry.get(key):
                entry[key] = info[key]

    # 2) stable names from udev, if available
    for descriptor, device in by_id.items():
        entry = entry_for(device)
        entry['by_id'] = os.path.join(SERIAL_BY_ID_DIR, descriptor)
        entry['descriptor'] = descriptor
        entry['name'] = _pretty_name(descriptor)
        for part in descriptor.split('-'):
            if part.startswith('if'):
                entry['interface'] = part

    for descriptor, device in by_path.items():
        entry_for(device)['by_path'] = os.path.join(SERIAL_BY_PATH_DIR, descriptor)

    # 3) usb descriptor from sysfs (linux) and the resulting suggestion. The entry may
    # already carry manufacturer/product from the pyserial enumeration (macOS, windows).
    for entry in ports.values():
        info = _read_sysfs_info(entry['device'])
        entry.update({key: value for key, value in info.items()})

        if not entry.get('descriptor'):
            readable = " ".join(part for part in [entry.get('manufacturer'), entry.get('product'),
                                                  entry.get('serial_number')] if part)
            if readable:
                entry['name'] = readable
        if entry.get('interface_name') and not entry.get('interface'):
            entry['interface'] = entry['interface_name']

        # the suggestion is derived from every available text
        haystack = " ".join(str(value) for value in [entry.get('descriptor'), entry.get('product'),
                                                    entry.get('manufacturer'), entry.get('interface_name')] if value)
        types, hint = _describe_descriptor(haystack)
        entry['suggested_device_types'] = types
        entry['hint'] = hint

    return sorted(ports.values(), key=lambda port: port['device'])


def _get_configured_gateways(hass: HomeAssistant) -> dict[str, dict]:
    """serial path -> gateway which uses it."""
    from .websocket import get_gateways

    result = {}
    for gateway in get_gateways(hass):
        serial_path = getattr(gateway, 'serial_path', None)
        if not serial_path:
            continue
        connected = None
        try:
            connected = bool(gateway._bus.is_active())
        except Exception:   # noqa: BLE001
            pass
        result[os.path.realpath(serial_path)] = {
            'id': getattr(gateway, 'dev_id', None),
            'name': getattr(gateway, 'dev_name', None),
            'device_type': getattr(getattr(gateway, 'dev_type', None), 'value', None),
            'serial_path': serial_path,
            'baud_rate': getattr(gateway, 'baud_rate', None),
            'connected': connected,
        }
    return result


def scan(hass: HomeAssistant) -> dict:
    """Result of the scan for the web ui."""
    configured = _get_configured_gateways(hass)
    ports = scan_serial_ports()

    for port in ports:
        gateway = configured.get(os.path.realpath(port['device']))
        port['used_by'] = gateway
        port['free'] = gateway is None

    # gateways whose port is currently missing (stick unplugged or renamed)
    known_devices = {os.path.realpath(port['device']) for port in ports}
    missing = [gateway for path, gateway in configured.items()
               if path not in known_devices and not os.path.exists(path)]

    LOGGER.debug(f"[{LOG_PREFIX_SCAN}] Found {len(ports)} serial ports, "
                 f"{len([p for p in ports if p['free']])} free, {len(missing)} gateway(s) without port.")

    return {
        'ports': ports,
        'gateways_without_port': missing,
        'device_types': [t.value for t in GatewayDeviceType],
        'hint': "Add a gateway in your configuration.yaml and then create it in Home Assistant "
                "under Settings -> Devices & Services -> Add integration -> Eltako.",
    }


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

def register_websocket_commands(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_gateway_scan)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_GATEWAY_SCAN})
@websocket_api.async_response
async def ws_gateway_scan(hass: HomeAssistant, connection, msg) -> None:
    """Scanning reads the file system, so it runs in the executor."""
    result = await hass.async_add_executor_job(scan, hass)
    connection.send_result(msg['id'], result)


### ---------------------------------------------------------------------------
### automatic re-location of a gateway whose serial port was renumbered
### ---------------------------------------------------------------------------

# The kernel numbers /dev/ttyUSB* by the order of appearance. Re-plugging a stick can move a
# gateway from ttyUSB0 to ttyUSB4 - the configuration then points to a port which no longer
# exists (or worse, to a different stick) and the gateway silently receives nothing.
#
# Therefore the usb serial number of the stick behind a working port is remembered per
# gateway. When the configured port is missing, the stick is searched by that fingerprint.
# As a last resort a port is used whose usb descriptor matches the gateway type - but only
# if the candidate is unambiguous.

FINGERPRINT_STORE_KEY = f"{DOMAIN}_gateway_ports"
FINGERPRINT_STORE_VERSION = 1


def choose_port(ports: list[dict], configured_path: str, remembered_fingerprint: str | None,
                device_type: str) -> tuple[str, str | None]:
    """Pure decision logic: (path to use, reason if it differs from the configuration)."""
    import os as _os

    if _os.path.exists(configured_path):
        return configured_path, None

    # 1) the stick which was behind this gateway before, found by its usb serial number
    if remembered_fingerprint:
        matches = [port for port in ports
                   if port.get('serial_number') == remembered_fingerprint and port.get('free', True)]
        if len(matches) == 1:
            return matches[0]['device'], (f"Configured port {configured_path} does not exist. The stick "
                                          f"(usb serial {remembered_fingerprint}) was found on "
                                          f"{matches[0]['device']} instead.")

    # 2) exactly one free port whose usb descriptor matches the gateway type
    device_type_value = str(getattr(device_type, 'value', device_type))
    candidates = [port for port in ports if port.get('free', True)
                  and device_type_value in (port.get('suggested_device_types') or [])]
    if len(candidates) == 1:
        return candidates[0]['device'], (f"Configured port {configured_path} does not exist. Using "
                                         f"{candidates[0]['device']} ({candidates[0].get('name')}) - the only "
                                         f"free port matching gateway type '{device_type_value}'.")

    return configured_path, None


async def async_resolve_serial_path(hass: HomeAssistant, gateway_id: int, device_type,
                                    configured_path: str) -> str:
    """Return the serial path to use for this gateway, following the moved stick if needed."""
    from homeassistant.helpers.storage import Store

    if GatewayDeviceType.is_lan_gateway(device_type):
        return configured_path        # host names and ip addresses are no files

    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    store = domain_data.get(DATA_PORT_FINGERPRINT_STORE)
    if store is None:
        store = Store(hass, FINGERPRINT_STORE_VERSION, FINGERPRINT_STORE_KEY)
        domain_data[DATA_PORT_FINGERPRINT_STORE] = store

    fingerprints = domain_data.get(DATA_PORT_FINGERPRINTS)
    if fingerprints is None:
        stored = await store.async_load()
        fingerprints = dict((stored or {}).get('fingerprints', {}))
        domain_data[DATA_PORT_FINGERPRINTS] = fingerprints

    ports = await hass.async_add_executor_job(scan, hass)
    path, reason = choose_port(ports['ports'], configured_path,
                               fingerprints.get(str(gateway_id)), device_type)
    if reason:
        LOGGER.warning(f"[{LOG_PREFIX_SCAN}] Gateway {gateway_id}: {reason}")

    # remember the usb serial number of the stick which is now behind the port
    if os.path.exists(path):
        info = await hass.async_add_executor_job(_read_sysfs_info, path)
        serial_number = info.get('serial_number')
        if serial_number and fingerprints.get(str(gateway_id)) != serial_number:
            fingerprints[str(gateway_id)] = serial_number
            await store.async_save({'fingerprints': fingerprints})
            LOGGER.debug(f"[{LOG_PREFIX_SCAN}] Gateway {gateway_id}: remembered usb serial "
                         f"{serial_number} of {path}.")

    return path
