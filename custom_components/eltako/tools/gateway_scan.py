"""Scan for serial ports which could host an EnOcean gateway.

`gateway.detect()` only returns a list of paths. For setting up a gateway that is not enough:
the user needs to know which stick is behind a port, which port is already in use and which
`device_type` fits. This module collects that information from the usb descriptors of
/dev/serial/by-id and offers it to the web ui.

Nothing is opened or written here - the scan is completely passive and therefore safe to run
while the gateways are connected. The `chip_id` and `base_id` of a port therefore never come
from the scan itself: they are what a stick answered the last time it was opened (by the plug
& play probe or by the identification below) and what is remembered for it. Reading them is
`tools/gateway_identity.py`, which also explains why they are the better identity.
"""

from __future__ import annotations

import glob
import os
from types import SimpleNamespace

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import (DATA_ELTAKO, DATA_PORT_FINGERPRINTS, DATA_PORT_FINGERPRINT_STORE,
                     DATA_PORT_STICK_IDS, DOMAIN, GatewayDeviceType, LOGGER, WS_GATEWAY_SCAN)
from . import gateway_identity
from eltakobus.gateway_scan import scan_serial_ports as _library_scan_serial_ports

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
     "EnOcean USB stick / programmer - this descriptor is used by the ELTAKO FAM-USB (ESP2 at "
     "9600 baud) and by ESP3 sticks (57600 baud). Such devices expose TWO ports (if00/if01, e.g. "
     "...600 and ...601) and only the SECOND one carries the telegrams - a FAM-USB answers on "
     "if01. If the gateway stays disconnected, use the other port."),
    ("USB300", [GatewayDeviceType.EnOceanUSB300.value],
     "EnOcean USB300 transceiver (ESP3, 57600 baud)."),
    # The current generation writes its product with spaces ('EnOcean USB 300 DD'), which the
    # fragment above does not cover - the normalization only turns underscores into spaces.
    ("USB 300", [GatewayDeviceType.EnOceanUSB300.value, GatewayDeviceType.ESP3.value],
     "EnOcean USB300 transceiver (ESP3, 57600 baud)."),
    ("USB 500", [GatewayDeviceType.ESP3.value],
     "EnOcean USB500 transceiver (ESP3, 57600 baud)."),
    # Anything else built by EnOcean: the manufacturer only ships ESP3 sticks, and knowing the
    # manufacturer is worth more than knowing the ftdi chip below - which is why this comes
    # first. The exact type is decided by the probe (it asks for the base id), so an unknown
    # EnOcean product reaches the probe instead of being skipped as 'no known gateway'.
    ("EnOcean", [GatewayDeviceType.ESP3.value, GatewayDeviceType.EnOceanUSB300.value],
     "EnOcean usb stick (ESP3, 57600 baud). The exact model is determined by the probe, which "
     "asks the stick for its base id."),
    ("FT232R", [GatewayDeviceType.GatewayEltakoFGW14USB.value, GatewayDeviceType.GatewayEltakoFAM14.value,
                GatewayDeviceType.GatewayEltakoFAMUSB.value],
     "FTDI serial adapter - used by ELTAKO FGW14-USB and FAM14 (both ESP2 at 57600 baud) and by "
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


# pyserial fills the fields it cannot answer with this placeholder instead of leaving them
# empty. Taking it for a real descriptor would be worse than knowing nothing: a port whose
# descriptor is known but fits no gateway is skipped by the probe (see
# `plug_and_play.ports_to_probe`), so 'n/a' would silently exclude exactly the ports the
# container exception is meant to cover - inside a container sysfs holds no usb information,
# but pyserial still lists every /dev/ttyUSB* with description 'n/a'.
PYSERIAL_UNKNOWN = 'n/a'


def _pyserial_value(port, *attributes) -> str | None:
    """First attribute of a pyserial port which carries real information."""
    for attribute in attributes:
        value = getattr(port, attribute, None)
        if value and value.strip().lower() != PYSERIAL_UNKNOWN:
            return value
    return None


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
                'manufacturer': _pyserial_value(port, 'manufacturer'),
                'product': _pyserial_value(port, 'product', 'description'),
                'serial_number': _pyserial_value(port, 'serial_number'),
                'interface_name': _pyserial_value(port, 'interface'),
            })
    except Exception as e:  # noqa: BLE001 - enumeration must never break the scan
        LOGGER.debug(f"[{LOG_PREFIX_SCAN}] pyserial enumeration failed: {e}")
    return ports


def scan_serial_ports() -> list[dict]:
    """All serial ports, using the passive scanner from ``eltako14bus``.

    The library owns enumeration, udev links and descriptor hints. The integration
    only adds sysfs data, the UI-shaped dictionary and the remembered identity fields.
    """
    raw_ports = []
    for info in _pyserial_ports():
        raw_ports.append(SimpleNamespace(
            device=info.get('device'), manufacturer=info.get('manufacturer'),
            product=info.get('product'), description=info.get('product'),
            serial_number=info.get('serial_number'), interface=info.get('interface_name')))

    result = []
    for info in _library_scan_serial_ports(device_globs=DEVICE_GLOBS,
                                           by_id_dir=SERIAL_BY_ID_DIR,
                                           by_path_dir=SERIAL_BY_PATH_DIR,
                                           ports=raw_ports):
        entry = info.as_dict()
        entry.update({
            'descriptor': None,
            'name': os.path.basename(entry['device']),
            'interface': entry.get('interface'),
            'device_node': any(glob.glob(pattern) and entry['device'] in glob.glob(pattern)
                               for pattern in DEVICE_GLOBS),
            'chip_id': None, 'base_id': None, 'ids_remembered': False,
        })
        entry.update(_read_sysfs_info(entry['device']))
        if entry.get('by_id'):
            descriptor = os.path.basename(entry['by_id'])
            entry['descriptor'] = descriptor
            entry['name'] = _pretty_name(descriptor)
            entry['interface'] = entry.get('interface') or next(
                (part for part in descriptor.split('-') if part.startswith('if')), None)
        elif any(entry.get(key) for key in ('manufacturer', 'product', 'serial_number')):
            entry['name'] = ' '.join(str(entry[key]) for key in
                                     ('manufacturer', 'product', 'serial_number') if entry.get(key))
        haystack = ' '.join(str(entry.get(key)) for key in
                            ('descriptor', 'product', 'manufacturer', 'interface') if entry.get(key))
        types, hint = _describe_descriptor(haystack)
        entry['suggested_device_types'] = types or entry.get('suggested_device_types', [])
        entry['hint'] = hint or entry.get('hint', '')
        result.append(entry)
    return sorted(result, key=lambda port: port['device'])


def _get_configured_gateways(hass: HomeAssistant) -> dict[str, dict]:
    """serial path -> gateway which uses it.

    A simulated gateway is left out: its 'port' is a synthetic name which no scan can find, so
    it would show up as a gateway whose stick was unplugged.
    """
    from ..core.websocket import get_gateways

    result = {}
    for gateway in get_gateways(hass):
        serial_path = getattr(gateway, 'serial_path', None)
        if not serial_path or getattr(gateway, 'is_simulated', False):
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
            # the running gateway already asked its hardware for the base id, so this one is
            # current - no port has to be opened for it
            'base_id': _reported_base_id(gateway),
        }
    return result


def _reported_base_id(gateway) -> str | None:
    """Base id a running gateway reported, or None while it is still unknown."""
    base_id = getattr(gateway, 'base_id', None)
    address = base_id[0] if base_id else None
    if not address or not any(address):
        return None                     # '00-00-00-00' means: not answered (yet)
    return gateway_identity.format_id(address)


def scan(hass: HomeAssistant) -> dict:
    """Result of the scan for the web ui."""
    configured = _get_configured_gateways(hass)
    ports = scan_serial_ports()
    domain_data = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {})
    sticks = domain_data.get(DATA_PORT_STICK_IDS) or {}
    identities = domain_data.get(DATA_PORT_FINGERPRINTS) or {}

    for port in ports:
        gateway = configured.get(os.path.realpath(port['device']))
        port['used_by'] = gateway
        port['free'] = gateway is None
        _apply_known_ids(port, gateway, sticks, identities)

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
                "under Settings -> Devices & Services -> Add integration -> ELTAKO.",
    }


### ---------------------------------------------------------------------------
### the identity of a stick
### ---------------------------------------------------------------------------

# The ids by which a stick is recognized again, strongest first:
#
# * `chip_id` - the id of the EnOcean transceiver, assigned in the factory and unchangeable.
#   Only an ESP3 stick reports it, and only when its port is opened (`gateway_identity`).
# * `base_id` - also from the factory, reported by every transceiver, but shared by all
#   devices on the bus of a FAM14, so it identifies a radio stick and not a bus gateway.
# * `usb_serial` - the serial number of the FTDI/CP210x chip in front of the gateway. Readable
#   without opening anything, but missing on cheap adapters, identical for both interfaces of
#   a two port stick, and gone when the adapter is replaced. Therefore last.
IDENTITY_FIELDS = ('chip_id', 'base_id', 'usb_serial')


def stick_key(port: dict) -> str | None:
    """Key under which the ids of a stick are remembered: usb serial number and interface.

    The interface belongs in the key because a stick with two ports (if00/if01) reports the
    same usb serial number for both of them while only one of them carries the telegrams.
    """
    port = port or {}
    serial_number = port.get('serial_number') or port.get('usb_serial')
    if not serial_number:
        return None                     # without a usb serial number nothing can be keyed
    return f"{serial_number}/{port.get('interface') or ''}"


def identity_of_port(port: dict) -> dict:
    """The ids of a scan entry, named the way the stored identity names them."""
    port = port or {}
    return {'chip_id': port.get('chip_id'), 'base_id': port.get('base_id'),
            'usb_serial': port.get('serial_number') or port.get('usb_serial'),
            'interface': port.get('interface')}


def _normalize_identity(stored) -> dict:
    """The first version of the store held a plain usb serial number and nothing else."""
    if isinstance(stored, str):
        return {'usb_serial': stored}
    return {key: value for key, value in (stored or {}).items() if value}


def _interfaces_differ(identity: dict, port_ids: dict) -> bool:
    return bool(identity.get('interface') and port_ids.get('interface')
                and identity['interface'] != port_ids['interface'])


def identity_match(identity, port: dict) -> str | None:
    """Name of the id which proves that this port carries the remembered stick - or None."""
    identity = _normalize_identity(identity)
    port_ids = identity_of_port(port)
    for field in IDENTITY_FIELDS:
        if not identity.get(field) or identity[field] != port_ids.get(field):
            continue
        if field == 'usb_serial' and _interfaces_differ(identity, port_ids):
            continue                    # the same stick, but its other interface
        return field
    return None


def identity_conflict(identity, port: dict) -> str | None:
    """Name of an id which proves that this port carries a *different* stick - or None."""
    identity = _normalize_identity(identity)
    if identity_match(identity, port):
        return None                     # something matches, so this is our stick
    port_ids = identity_of_port(port)
    for field in IDENTITY_FIELDS:
        if identity.get(field) and port_ids.get(field) and identity[field] != port_ids[field]:
            return field
    return None


def _port_of_path(ports: list[dict], path: str) -> dict | None:
    """The scan entry which belongs to a path (both resolved, a device node can be a symlink)."""
    if not path:
        return None
    target = os.path.realpath(path)
    for port in ports:
        if os.path.realpath(str(port.get('device') or '')) == target:
            return port
    return None


def _apply_known_ids(port: dict, gateway: dict | None, sticks: dict, identities: dict) -> None:
    """Fill chip_id/base_id of a port with what is known about the stick behind it.

    Nothing is opened for this, see the module docstring: the base id of a running gateway is
    what it reported after connecting, everything else was read the last time the port was
    open and is marked with `ids_remembered`.
    """
    remembered = dict(sticks.get(stick_key(port) or '') or {})

    if gateway and gateway.get('base_id'):
        port['base_id'] = gateway['base_id']
    elif remembered.get('base_id'):
        port['base_id'] = remembered['base_id']
        port['ids_remembered'] = True

    if remembered.get('chip_id'):
        port['chip_id'] = remembered['chip_id']
        port['ids_remembered'] = True
    elif gateway is not None:
        # the stick of a running gateway must not be opened again, so its chip id can only
        # come from what was stored for that gateway
        stored = _normalize_identity(identities.get(str(gateway.get('id'))))
        if stored.get('chip_id'):
            port['chip_id'] = stored['chip_id']
            port['ids_remembered'] = True


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
# gateway from ttyUSB0 to ttyUSB4, and two sticks which are plugged in the other way round
# after a maintenance simply trade their ports. The configuration then points to a port which
# no longer exists - or, worse, to a *different* stick, in which case both gateways silently
# receive nothing that belongs to them.
#
# Therefore the identity of the stick behind a working port is remembered per gateway
# (chip id, base id and usb serial number, see IDENTITY_FIELDS). At every start the port is
# resolved by that identity instead of by its name, so nobody has to reconfigure anything
# after a reboot in which the ports came up differently:
#
#   1. the configured port exists and carries our stick     -> use it (the normal case)
#   2. it exists but carries a different one                -> use the port where ours sits
#   3. it is gone                                           -> use the port where ours sits
#   4. nothing is known                                     -> the single free port whose usb
#                                                              descriptor fits the type
#
# Steps 2 and 3 need an id which really belongs to the gateway. The usb serial number is read
# passively and often answers already; if it does not (no serial number on the chip, both
# interfaces of a two port stick carry the same one, no sysfs inside a container) the free
# candidate ports are opened and asked for their chip id - `_async_identify_ports`.

FINGERPRINT_STORE_KEY = f"{DOMAIN}_gateway_ports"
FINGERPRINT_STORE_VERSION = 1

# how many ports are opened at most while one gateway looks for its stick. Every question
# costs up to two seconds, and this runs during the setup of the gateway.
MAX_PORTS_TO_IDENTIFY = 4


def choose_port(ports: list[dict], configured_path: str, remembered,
                device_type: str) -> tuple[str, str | None]:
    """Pure decision logic: (path to use, reason worth logging).

    `remembered` is the identity stored for this gateway - a dict with any of the
    IDENTITY_FIELDS, or a plain usb serial number as the first version of the store wrote it.
    A reason is also returned when the path stays as configured but the port carries a stick
    which is not ours: that is the case a silent gateway is explained by.
    """
    identity = _normalize_identity(remembered)
    configured = _port_of_path(ports, configured_path)

    if os.path.exists(configured_path):
        if configured is None or not identity:
            return configured_path, None            # nothing to compare it with
        if identity_match(identity, configured):
            return configured_path, None            # our stick is where it belongs

        conflict = identity_conflict(identity, configured)
        if not conflict:
            return configured_path, None            # neither proven right nor proven wrong

        found = _unique_identity_match(ports, identity, exclude=configured_path)
        if found:
            port, field = found
            return port['device'], (
                f"{configured_path} carries another stick now ({_id_text(conflict, configured)} "
                f"instead of {identity[conflict]}). This gateway belongs to "
                f"{_id_text(field, port)}, which sits on {port['device']} - using that one. "
                f"The configuration does not have to be changed.")
        return configured_path, (
            f"{configured_path} carries another stick ({_id_text(conflict, configured)}, expected "
            f"{identity[conflict]}) and the stick of this gateway was not found on a free port. "
            f"Keeping the configured port - reception can stay empty in this state.")

    # the configured port is gone: 1) the stick which was behind this gateway, found by its ids
    found = _unique_identity_match(ports, identity)
    if found:
        port, field = found
        return port['device'], (f"Configured port {configured_path} does not exist. The stick "
                                f"({_id_text(field, port)}) was found on {port['device']} instead.")

    # 2) exactly one free port whose usb descriptor matches the gateway type
    device_type_value = str(getattr(device_type, 'value', device_type))
    candidates = [port for port in ports if port.get('free', True)
                  and device_type_value in (port.get('suggested_device_types') or [])]
    if len(candidates) == 1:
        return candidates[0]['device'], (f"Configured port {configured_path} does not exist. Using "
                                         f"{candidates[0]['device']} ({candidates[0].get('name')}) - the only "
                                         f"free port matching gateway type '{device_type_value}'.")

    return configured_path, None


def _id_text(field: str, port: dict) -> str:
    """'chip id 01-93-8B-2C' - how an id is named in a log line."""
    return f"{field.replace('_', ' ')} {identity_of_port(port).get(field)}"


def _unique_identity_match(ports: list[dict], identity,
                           exclude: str = None) -> tuple[dict, str] | None:
    """The one free port which carries the remembered stick, and the id which proves it.

    The strongest id decides. If two ports claim the same one, nothing is returned - a wrong
    port is worse than a gateway which stays on the port it was configured with.
    """
    identity = _normalize_identity(identity)
    excluded = os.path.realpath(exclude) if exclude else None

    for field in IDENTITY_FIELDS:
        if not identity.get(field):
            continue
        wanted = {field: identity[field], 'interface': identity.get('interface')}
        matches = [port for port in ports
                   if port.get('free', True)
                   and os.path.realpath(str(port.get('device') or '')) != excluded
                   and identity_match(wanted, port) == field]
        if len(matches) == 1:
            return matches[0], field
        if matches:
            LOGGER.warning(f"[{LOG_PREFIX_SCAN}] {len(matches)} ports report the same "
                           f"{field.replace('_', ' ')} {identity[field]} - not guessing.")
            return None
    return None


def _could_be_this_gateway(port: dict, device_type) -> bool:
    """A free port which the usb descriptor does not rule out for this gateway type.

    A port without any descriptor qualifies: inside a container sysfs holds no usb
    information, which is exactly the situation in which the chip id has to do the work.
    """
    if not port.get('free', True):
        return False        # a running gateway receives on it - opening it would interrupt that
    suggested = port.get('suggested_device_types') or []
    return not suggested or str(getattr(device_type, 'value', device_type)) in suggested


def _identification_would_help(chosen: str, configured_path: str, identity: dict,
                               ports: list[dict], device_type) -> bool:
    """Whether opening ports can decide what the usb descriptors could not."""
    if not gateway_identity.can_identify(device_type):
        return False        # a FAM14/FGW14-USB has no id of its own to compare
    if not (identity.get('chip_id') or identity.get('base_id')):
        return False        # nothing was ever read from this gateway - no id to look for
    if chosen != configured_path:
        return False        # already resolved, the usb serial number was enough
    port = _port_of_path(ports, chosen)
    if port is None:
        return True         # the configured port is gone
    return identity_match(identity, port) is None


async def _async_identify_ports(hass: HomeAssistant, ports: list[dict], configured_path: str,
                                identity: dict, device_type) -> bool:
    """Ask the candidate sticks for their chip id, in place. True if anything answered.

    The port of a *running* gateway is never opened, `_could_be_this_gateway` keeps those out.
    The port of a gateway which is only configured is fair game: it is not open yet, and it is
    exactly where a stick that traded places has to be looked for.
    """
    baud_rate = gateway_identity.baud_rate_of(device_type)
    candidates = [port for port in ports if _could_be_this_gateway(port, device_type)]
    # the configured port first - in the normal case the answer comes from there and no other
    # port has to be opened at all
    target = os.path.realpath(configured_path or '')
    candidates.sort(key=lambda port: os.path.realpath(str(port.get('device') or '')) != target)

    answered = False
    for port in candidates[:MAX_PORTS_TO_IDENTIFY]:
        found = await hass.async_add_executor_job(gateway_identity.read_identity,
                                                 port['device'], device_type, baud_rate)
        if not found:
            continue
        port.update({key: value for key, value in found.items() if key in ('chip_id', 'base_id')})
        port['ids_remembered'] = False
        answered = True
        LOGGER.debug(f"[{LOG_PREFIX_SCAN}] {port['device']} reports chip id {found.get('chip_id')} "
                     f"/ base id {found.get('base_id')}.")
        if identity_match(identity, port):
            break               # ours - no reason to open anything else
    return answered


def _remember_sticks(sticks: dict, ports: list[dict]) -> None:
    """Store the ids a stick answered with, keyed by its usb serial number."""
    for port in ports:
        key = stick_key(port)
        ids = {field: port.get(field) for field in ('chip_id', 'base_id') if port.get(field)}
        if not key or not ids:
            continue
        sticks[key] = {**(sticks.get(key) or {}), **ids, 'device': port.get('device')}


def _merge_identity(identity: dict, port: dict, path: str) -> dict:
    """What is known about the stick of this gateway after it was resolved to `path`.

    An id which the port did not report is kept: the chip id is only read when it is needed,
    so forgetting it on every start would defeat its purpose. A stale id cannot cause a wrong
    decision - relocating requires a match, and the id of a stick which is gone matches
    nothing.
    """
    port_ids = identity_of_port(port)

    # a different serial chip and nothing which proves that the EnOcean hardware behind it is
    # still the same one: the stick was replaced, so what was known about the old one is wrong
    if (port_ids.get('usb_serial') and identity.get('usb_serial')
            and port_ids['usb_serial'] != identity['usb_serial'] and not port_ids.get('chip_id')):
        identity = {}

    merged = dict(identity)
    merged.update({field: value for field, value in port_ids.items() if value})
    merged['device'] = path
    return {key: value for key, value in merged.items() if value}


async def _async_load_identities(hass: HomeAssistant) -> tuple:
    """(store, identity per gateway, ids per stick). Read once, then kept in hass.data."""
    from homeassistant.helpers.storage import Store

    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    store = domain_data.get(DATA_PORT_FINGERPRINT_STORE)
    if store is None:
        store = Store(hass, FINGERPRINT_STORE_VERSION, FINGERPRINT_STORE_KEY)
        domain_data[DATA_PORT_FINGERPRINT_STORE] = store

    identities = domain_data.get(DATA_PORT_FINGERPRINTS)
    sticks = domain_data.get(DATA_PORT_STICK_IDS)
    if identities is None or sticks is None:
        stored = await store.async_load() or {}
        identities = dict(stored.get('fingerprints') or {})
        sticks = dict(stored.get('sticks') or {})
        domain_data[DATA_PORT_FINGERPRINTS] = identities
        domain_data[DATA_PORT_STICK_IDS] = sticks
    return store, identities, sticks


async def _async_save_identities(hass: HomeAssistant, store, identities: dict, sticks: dict) -> None:
    # 'fingerprints' is the key the first version of this store used - kept, so an installation
    # which updates does not forget which stick belonged to which gateway
    await store.async_save({'fingerprints': identities, 'sticks': sticks})


async def _async_port_info(hass: HomeAssistant, path: str) -> dict:
    """The scan entry of one path - the usb information a stick is keyed by.

    `_read_sysfs_info` alone would be cheaper, but it only answers on linux outside of a
    container. The (still passive) scan also covers macOS and windows, where pyserial is the
    only source of the usb serial number.
    """
    ports = await hass.async_add_executor_job(scan_serial_ports)
    return _port_of_path(ports, path) or {'device': path}


async def async_resolve_serial_path(hass: HomeAssistant, gateway_id: int, device_type,
                                    configured_path: str) -> str:
    """Return the serial path to use for this gateway, following its stick if needed."""
    if GatewayDeviceType.is_lan_gateway(device_type):
        return configured_path        # host names and ip addresses are no files

    store, identities, sticks = await _async_load_identities(hass)
    identity = _normalize_identity(identities.get(str(gateway_id)))
    sticks_before = dict(sticks)

    ports = (await hass.async_add_executor_job(scan, hass))['ports']
    path, reason = choose_port(ports, configured_path, identity, device_type)

    # The usb descriptors did not prove anything: ask the sticks themselves, their chip id is
    # the only id which really belongs to them.
    if _identification_would_help(path, configured_path, identity, ports, device_type):
        if await _async_identify_ports(hass, ports, configured_path, identity, device_type):
            _remember_sticks(sticks, ports)
            path, reason = choose_port(ports, configured_path, identity, device_type)

    if reason:
        LOGGER.warning(f"[{LOG_PREFIX_SCAN}] Gateway {gateway_id}: {reason}")

    # remember the stick which is behind the port that is used now
    chosen = _port_of_path(ports, path)
    if chosen is None and os.path.exists(path):
        chosen = await _async_port_info(hass, path)
    if chosen:
        _remember_sticks(sticks, [chosen])
        updated = _merge_identity(identity, chosen, path)
        if updated != identity or sticks != sticks_before:
            identities[str(gateway_id)] = updated
            await _async_save_identities(hass, store, identities, sticks)
            LOGGER.debug(f"[{LOG_PREFIX_SCAN}] Gateway {gateway_id}: remembered {updated} "
                         f"for {path}.")

    return path


async def async_remember_stick_identities(hass: HomeAssistant, detected: dict,
                                          ports_by_device: dict) -> None:
    """Store the ids the plug & play probe read from the free sticks.

    A probe is the only moment at which a stick nobody uses says who it is, so this is where
    the chip id of a gateway that is about to be created comes from - and what the passive
    port scan shows for a port afterwards.
    """
    reported = {device: detection for device, detection in (detected or {}).items()
                if (detection or {}).get('chip_id') or (detection or {}).get('base_id')}
    if not reported:
        return          # a FAM14/FGW14-USB reports no id - nothing to remember, nothing to load

    store, identities, sticks = await _async_load_identities(hass)
    before = dict(sticks)

    for device, detection in reported.items():
        port = dict((ports_by_device or {}).get(device) or {'device': device})
        port.update({key: detection.get(key) for key in ('chip_id', 'base_id')})
        _remember_sticks(sticks, [port])

    if sticks != before:
        await _async_save_identities(hass, store, identities, sticks)


async def async_remember_base_id(hass: HomeAssistant, gateway_id: int, base_id: str,
                                 serial_path: str) -> None:
    """Remember the base id a running gateway reported for its port.

    This costs nothing: the gateway asks its hardware for the base id after every connect
    anyway (`EnOceanGateway.query_for_base_id_and_version`), and for a gateway whose port must
    not be opened a second time it is the only id which can be had at all.
    """
    if not base_id or base_id == gateway_identity.EMPTY_BASE_ID:
        return
    if not serial_path or not os.path.exists(serial_path):
        return      # a LAN gateway has no port whose stick could be remembered

    store, identities, sticks = await _async_load_identities(hass)
    identity = _normalize_identity(identities.get(str(gateway_id)))
    port = {**(await _async_port_info(hass, serial_path)), 'base_id': base_id}

    before_identity, before_sticks = dict(identity), dict(sticks)
    _remember_sticks(sticks, [port])
    identity = _merge_identity(identity, port, serial_path)

    if identity != before_identity or sticks != before_sticks:
        identities[str(gateway_id)] = identity
        await _async_save_identities(hass, store, identities, sticks)
        LOGGER.debug(f"[{LOG_PREFIX_SCAN}] Gateway {gateway_id}: remembered base id {base_id} "
                     f"of {serial_path}.")
