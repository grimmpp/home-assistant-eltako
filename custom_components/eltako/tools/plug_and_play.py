"""Plug & play: detect connected gateways and add the devices behind them automatically.

Answers the question "how do I notice that a new device was plugged in?" in three steps,
each of which only uses information which is unambiguous:

1. **Gateway**   Two sources:
   * **serial** - every port which is not used by a configured gateway is probed actively
     (`probe_ports`). The probe identifies a FAM14 (its adapter echoes what is written to
     it), an ESP3 stick like the USB300 and a FAM-USB (both answer a base id request). An
     FGW14-USB cannot be proven - the test matches every port which is reachable and does
     not echo - so it is only *suggested* and never created automatically.
   * **network** - LAN gateways which announce themselves via mDNS are picked up
     (`async_discover_mdns_gateways`): a service which states its own type and name is a
     positive identification, so those are created. The only exception is the ESP2 reverse
     bridge which this integration publishes itself.
   (Both tables are ported from the SerialPortDetector and the LanServiceDetector of the
   EnOcean Device Manager, same author, MIT.)

2. **Bus**       A newly created bus gateway (FAM14, FGW14-USB) gets its bus read once:
   discovery of every position plus the complete memory of every device
   (`bus_members.start_bus_scan_thread`). That is the same paced scan the button "scan bus &
   read memory" of the device page runs.

3. **Devices**   Everything which the scan identified without any doubt is added to the
   configuration like a device created in the web ui - so it can be edited and removed again
   (`device_config`). Four sources, in decreasing order of certainty:
      * device of a simulated gateway (it states its platform, EEP and sender - see
        `simulation.derive_candidates`; a simulated bus is not read, there is no memory)
      * bus position with a known model (discovery reply + device catalog)
      * sender found in the memory of a bus actuator (its key function names the EEP)
      * address which sent a 4BS teach-in telegram (the telegram states the EEP)
   Everything else (a position which is not identified, a model which several device classes
   share, an EEP which was only guessed from the data bytes) is reported as "needs a
   decision" and stays a manual step on the device page.

Nothing is written into any device: the sender ids of added actuators still have to be
taught in (button "check & teach in HA senders" on the device page). Reading the bus locks
it for a few minutes, therefore the bus of a gateway is only read once - the periodic check
skips a bus which was scanned before, and reading it again is an explicit action.

Switched on with the general setting `plug_and_play` (checkbox in the web ui) and triggered
by hand with the button on the overview page (websocket `eltako/plug_and_play/run`).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback

from ..const import (CONF_BASE_ID, CONF_DEVICE_TYPE, CONF_EEP, CONF_GATEWAY, CONF_GATEWAY_ADDRESS,
                     CONF_GATEWAY_DESCRIPTION, CONF_GATEWAY_PORT, CONF_PLUG_AND_PLAY,
                     CONF_PLUG_AND_PLAY_INTERVAL, CONF_SENDER, CONF_SERIAL_PATH, DATA_ELTAKO,
                     DATA_PLUG_AND_PLAY, DOMAIN, ELTAKO_CONFIG, GatewayDeviceType, LOGGER, SOURCE_UI_GATEWAY,
                     WS_PLUG_AND_PLAY_PROBE, WS_PLUG_AND_PLAY_RUN, WS_PLUG_AND_PLAY_STATUS)
from ..config import config_helpers
from ..catalog.device_catalog import describe_gateway_type
from . import gateway_identity

LOG_PREFIX_PNP = "Plug & Play"

### ---------------------------------------------------------------------------
### probing of the serial ports
### ---------------------------------------------------------------------------

# A port which is no gateway cannot be distinguished from a gateway which does not answer, so
# every test costs its full timeout. The timeouts and the requests themselves live in
# `gateway_identity` - the probe asks the same questions whose answers identify a stick.
PROBE_CONNECT_TIMEOUT = gateway_identity.CONNECT_TIMEOUT

# gateway types which the probe can prove. An FGW14-USB is missing on purpose: its test
# matches every reachable port which does not echo, so it is a suggestion, not a detection.
CONFIDENT_GATEWAY_TYPES = {
    GatewayDeviceType.GatewayEltakoFAM14.value,
    GatewayDeviceType.GatewayEltakoFAMUSB.value,
    GatewayDeviceType.ESP3.value,
    GatewayDeviceType.EnOceanUSB300.value,
}

# platforms whose devices are controlled by Home Assistant and therefore need a sender
SENDER_PLATFORMS = {Platform.LIGHT.value, Platform.SWITCH.value, Platform.COVER.value,
                    Platform.CLIMATE.value}

# bus positions which are occupied by a gateway module - they are added as gateway, not as device
GATEWAY_DEVICE_CLASSES = {'FAM14', 'FGW14_USB', 'FGW14', 'FTD14'}

# Home Assistant sender ids of bus devices are counted from this offset. Same convention as
# the configuration generator of the EnOcean Device Manager and as config_import.py, so an
# imported and an auto detected configuration use the same addresses.
LOCAL_SENDER_OFFSET = 0xB000


def local_sender_id(bus_address: int) -> str:
    """Sender id Home Assistant uses for a bus position, e.g. 4 -> '00-00-B0-04'."""
    return f"00-00-{(LOCAL_SENDER_OFFSET + int(bus_address)) >> 8:02X}-" \
           f"{(LOCAL_SENDER_OFFSET + int(bus_address)) & 0xFF:02X}"


def local_address(bus_address: int) -> str:
    """Local address of a bus position, e.g. 4 -> '00-00-00-04'."""
    return f"00-00-00-{int(bus_address):02X}"


def _is_usb_port(port: dict) -> bool:
    """A FAM-USB is a usb stick - probing it on a built-in serial port only costs a timeout."""
    device = str(port.get('device') or '')
    if 'usb' in device.lower() or 'acm' in device.lower():
        return True
    return bool(port.get('serial_number') or port.get('manufacturer') or port.get('by_id'))


async def _async_detect_gateway(device: str, baud_rate: int, is_usb_port: bool = True) -> dict | None:
    """Probe one serial port with one baud rate. None, or what was found:

        {'device_type', 'baud_rate', 'chip_id', 'base_id', ...}

    The ids are a by-product of the probe and the reason it is worth reading them here: the
    port is open anyway, and asking for the base id is what proves an ESP3 stick or a FAM-USB
    in the first place. A gateway which cannot report an id of its own (FAM14, FGW14-USB)
    simply carries none - see `gateway_identity`.

    The order of the tests must not be changed:
      * an ESP3 stick answers a base id request only at 57600 baud
      * only the adapter of a FAM14 echoes back what is written to it - the cheapest test
      * a FAM-USB works with 9600 baud only and has to be tested before the FGW14, whose
        test matches every port which does not echo
    """
    import serial

    from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
    from eltakobus.serial import RS485SerialInterfaceV2

    def found(device_type: str, identity: dict = None) -> dict:
        return {'device_type': device_type, 'baud_rate': baud_rate, **(identity or {})}

    communicator = None
    try:
        # opening the port with pyserial is the cheapest check whether it exists at all
        probe = serial.Serial(device, baudrate=baud_rate, timeout=0.2)
        probe.close()

        if baud_rate == 57600:
            communicator = ESP3SerialCommunicator(device, auto_reconnect=False)
            gateway_identity.start_communicator(communicator)
            if communicator.is_serial_connected.wait(PROBE_CONNECT_TIMEOUT):
                identity = await gateway_identity.async_read_esp3_identity(communicator)
                if identity.get('base_id'):
                    return found(GatewayDeviceType.ESP3.value, identity)
            # no ESP3 gateway - the port can still be a FAM14 or an FGW14-USB
            gateway_identity.stop_communicator(communicator)
            communicator = None

        communicator = RS485SerialInterfaceV2(device, baud_rate=baud_rate, delay_message=0.2,
                                              auto_reconnect=False)
        gateway_identity.start_communicator(communicator)
        if not communicator.is_serial_connected.wait(PROBE_CONNECT_TIMEOUT):
            return None

        if communicator.suppress_echo:
            return found(GatewayDeviceType.GatewayEltakoFAM14.value)

        if baud_rate == 9600:
            if not is_usb_port:
                LOGGER.debug(f"[{LOG_PREFIX_PNP}] {device} has no usb descriptor - "
                             f"skipping the FAM-USB test.")
            else:
                base_id = await gateway_identity.async_read_esp2_base_id(communicator)
                if base_id not in (None, gateway_identity.EMPTY_BASE_ID):
                    return found(GatewayDeviceType.GatewayEltakoFAMUSB.value, {'base_id': base_id})

        if baud_rate == 57600:
            # reachable, no echo, no ESP3 answer: an FGW14-USB behaves like this - but so does
            # every other serial device. Only a suggestion, see CONFIDENT_GATEWAY_TYPES.
            return found(GatewayDeviceType.GatewayEltakoFGW14USB.value)

        return None
    except Exception as e:  # noqa: BLE001 - a port which is no gateway is the normal case
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] {device} is no gateway with {baud_rate} baud: {e}")
        return None
    finally:
        gateway_identity.stop_communicator(communicator)


def probe_ports(ports: list[dict]) -> dict[str, dict]:
    """Probe a list of ports (entries of gateway_scan) -> {device: detection}.

    Runs the whole probing in an event loop of its own, therefore it must NOT be called in
    the event loop of Home Assistant - `async_probe_ports` moves it into the executor.
    9600 baud is checked first, see _async_detect_gateway.
    """
    async def run() -> dict[str, dict]:
        detected: dict[str, dict] = {}
        for baud_rate in (9600, 57600):
            for port in ports:
                device = str(port.get('device') or '')
                if not device or device in detected:
                    continue
                detection = await _async_detect_gateway(device, baud_rate, _is_usb_port(port))
                if detection is None:
                    continue
                detected[device] = detection
                LOGGER.info(f"[{LOG_PREFIX_PNP}] {detection['device_type']} detected on {device} "
                            f"({baud_rate} baud"
                            f"{', chip id ' + detection['chip_id'] if detection.get('chip_id') else ''}"
                            f"{', base id ' + detection['base_id'] if detection.get('base_id') else ''}).")
        return detected

    return asyncio.run(run())


async def async_probe_ports(hass: HomeAssistant, ports: list[dict]) -> dict[str, dict]:
    return await hass.async_add_executor_job(probe_ports, ports)


### ---------------------------------------------------------------------------
### which ports are worth probing
### ---------------------------------------------------------------------------

def _has_usb_descriptor(port: dict) -> bool:
    return bool(port.get('descriptor') or port.get('product') or port.get('manufacturer')
                or port.get('by_id'))


def _could_carry_a_gateway(port: dict) -> bool:
    """Whether a port without any usb information is worth opening at all.

    Only relevant for ports which carry no descriptor - with one, the rules below decide. A
    linux device node (`/dev/ttyUSB*`, `ttyACM*`, `ttyAMA*`) qualifies even when it says
    nothing about itself, because that is exactly the situation inside a container: the node
    is passed through, sysfs is not.

    Everything else at this point comes from the pyserial enumeration on a developer machine,
    where macOS lists its built-in services as serial ports - `/dev/cu.Bluetooth-Incoming-Port`
    and `/dev/cu.debug-console` are openable, silent and would therefore be reported as an
    FGW14-USB, which is noise rather than a finding.
    """
    return bool(port.get('device_node')) or _is_usb_port(port)


def ports_to_probe(scan: dict, configured_paths: set[str]) -> list[dict]:
    """Ports which may be opened by the probe.

    Four rules, all of them protecting something which is already working:

    * a port which one of our gateways uses is never touched - opening it would interrupt its
      reception. `scan['ports']` marks the ports of the *running* gateways, `configured_paths`
      additionally covers gateways which are configured but not set up yet.
    * a port whose usb descriptor is known but does not fit any Eltako/EnOcean gateway is
      skipped. Home Assistant installations usually carry more sticks (Zigbee, Z-Wave, ...)
      and those belong to another integration.
    * a port without any usb descriptor is probed **if it could carry a gateway** - inside a
      container only the device nodes are passed through, so the descriptor of a FAM14 is
      simply not readable there. A built-in port of the host machine is not probed, see
      `_could_carry_a_gateway`.

    A port which another program holds open cannot be opened a second time (pyserial locks it
    exclusively), so a stick which is in use is skipped by the probe itself as well.
    """
    import os

    claimed = {os.path.realpath(path) for path in configured_paths if path}

    candidates = []
    for port in (scan.get('ports') or []):
        if not port.get('free', True):
            continue
        if os.path.realpath(str(port.get('device') or '')) in claimed:
            continue
        if _has_usb_descriptor(port):
            if not port.get('suggested_device_types'):
                LOGGER.debug(f"[{LOG_PREFIX_PNP}] {port.get('device')} "
                             f"({port.get('name')}) is no known gateway descriptor - not probed.")
                continue
        elif not _could_carry_a_gateway(port):
            LOGGER.debug(f"[{LOG_PREFIX_PNP}] {port.get('device')} carries no usb information "
                         f"and is no device node - not probed.")
            continue
        candidates.append(port)
    return candidates


def configured_serial_paths(hass: HomeAssistant) -> set[str]:
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    return {str(gateway.get(CONF_SERIAL_PATH)) for gateway in (config.get(CONF_GATEWAY) or [])
            if gateway.get(CONF_SERIAL_PATH)}


# gateway types without an entry in the device catalog, so a detected gateway always has a
# readable name in the report
GATEWAY_LABELS = {
    GatewayDeviceType.EUL_LAN.value: 'EUL LAN Gateway',
    GatewayDeviceType.MGW_LAN.value: 'MGW LAN Gateway',
    GatewayDeviceType.LAN_ESP2.value: 'ESP2 LAN Gateway',
    GatewayDeviceType.VirtualNetworkAdapter.value: 'ESP2 network bridge',
}


def _label_of(device_type: str) -> tuple[str, str]:
    """(name, description) of a gateway type - from the device catalog if it knows it."""
    catalog = describe_gateway_type(device_type)
    return (catalog.get('hw_type') or GATEWAY_LABELS.get(device_type) or device_type,
            catalog.get('description') or "")


# ESP3 models which the probe cannot tell apart. It proves "an ESP3 gateway answered the base
# id request" and nothing more - every ESP3 stick answers it the same way. Which model it is
# stands in the usb descriptor, so the two sources complete each other.
ESP3_MODELS = {GatewayDeviceType.EnOceanUSB300.value}


def refine_esp3_model(device_type: str, port: dict = None) -> str:
    """Replace the generic ESP3 type by the model the usb descriptor names.

    Without this a USB300 ends up as 'esp3-gateway', which the device catalog knows as the
    PioTek 'MGW (USB)' - a different manufacturer's product, and a name nobody recognizes on
    their own stick. Both types behave identically (57600 baud, same ESP3 communicator), so
    this only affects what the gateway is called and which hardware it is shown as.

    Only the generic type is refined: a probe result which already names a model stays as it
    is, and a descriptor which suggests no ESP3 model at all leaves it generic - which is the
    honest answer for an ESP3 stick this integration has no catalog entry for.
    """
    if device_type != GatewayDeviceType.ESP3.value:
        return device_type

    for suggestion in (port or {}).get('suggested_device_types') or []:
        if suggestion in ESP3_MODELS:
            return suggestion
    return device_type


def describe_candidate(device: str, detection: dict, port: dict = None) -> dict:
    """One gateway detected on a serial port, ready for the report and for creating it."""
    device_type = refine_esp3_model(detection['device_type'], port)
    hw_type, description = _label_of(device_type)
    return {
        'connection': 'serial',
        'serial_path': device,
        'device_type': device_type,
        'baud_rate': detection.get('baud_rate'),
        'hw_type': hw_type,
        'description': description,
        'port_name': (port or {}).get('name'),
        # the ids the stick reported while it was open. They are what identifies the hardware
        # itself - the usb serial number below only identifies the serial chip in front of it.
        'chip_id': detection.get('chip_id'),
        'base_id': detection.get('base_id'),
        'usb_serial': (port or {}).get('serial_number'),
        # only a gateway which the probe could prove is created automatically
        'confident': device_type in CONFIDENT_GATEWAY_TYPES,
        'reason': "Answered the probe." if device_type in CONFIDENT_GATEWAY_TYPES else
                  "The port is reachable and does not echo - an FGW14-USB behaves like this, "
                  "but so does any other serial device. Please confirm the type.",
    }


### ---------------------------------------------------------------------------
### LAN gateways which announce themselves via mDNS
### ---------------------------------------------------------------------------

# mDNS service types which are browsed, and the fragment of the service *name* which tells
# which gateway is behind it. Same table as the LanServiceDetector of the EnOcean Device
# Manager uses, so both find the same gateways.
MDNS_SERVICE_TYPES = ['_bsc-sc-socket._tcp.local.', '_tcm515._tcp.local.']

MDNS_NAME_TO_GATEWAY_TYPE = {
    'SmartConn': GatewayDeviceType.LAN.value,                   # PioTek MGW / BSC SmartConnect
    'EUL': GatewayDeviceType.EUL_LAN.value,
    'Virtual-Network-Gateway-Adapter': GatewayDeviceType.LAN_ESP2.value,
}

# A gateway which announces its own service type and name identifies itself - that is a much
# better proof than the FGW14-USB test, so those are created automatically. The reverse bridge
# is the exception: it is published *by this integration* (virtual_network_gateway.py) for the
# EnOcean Device Manager, so creating a gateway for it would connect Home Assistant to itself.
MDNS_SUGGEST_ONLY = {GatewayDeviceType.LAN_ESP2.value}

# how long the mDNS browser listens for announcements
MDNS_BROWSE_SECONDS = 4.0


def gateway_type_of_mdns_name(name: str) -> str | None:
    """Gateway type behind an mDNS service name, e.g. 'SmartConn-1234._bsc...' -> 'lan'."""
    for fragment, device_type in MDNS_NAME_TO_GATEWAY_TYPE.items():
        if fragment.lower() in str(name or '').lower():
            return device_type
    return None


def browse_mdns_services(zeroconf, seconds: float = MDNS_BROWSE_SECONDS) -> list[dict]:
    """Services of the known types which announce themselves right now.

    Blocking (the browser needs a moment to collect the answers and reading the service info
    is synchronous), so it must run in the executor. The Zeroconf instance belongs to Home
    Assistant and is therefore never closed here.
    """
    import socket
    import time

    from zeroconf import ServiceBrowser

    found: dict[str, dict] = {}

    class Listener:
        def add_service(self, zc, service_type, name):
            try:
                info = zc.get_service_info(service_type, name)
                if info is None or not info.addresses:
                    return
                found[name] = {
                    'name': name, 'service_type': service_type, 'port': info.port,
                    'address': socket.inet_ntoa(info.addresses[0]),
                    'hostname': str(info.server or '').rstrip('.'),
                }
            except Exception as e:  # noqa: BLE001 - a service which does not answer is normal
                LOGGER.debug(f"[{LOG_PREFIX_PNP}] Cannot read the mDNS service {name}: {e}")

        def update_service(self, zc, service_type, name):
            self.add_service(zc, service_type, name)

        def remove_service(self, zc, service_type, name):
            found.pop(name, None)

    browsers = [ServiceBrowser(zeroconf, service_type, Listener())
                for service_type in MDNS_SERVICE_TYPES]
    try:
        time.sleep(seconds)
    finally:
        for browser in browsers:
            try:
                browser.cancel()
            except Exception as e:  # noqa: BLE001
                LOGGER.debug(f"[{LOG_PREFIX_PNP}] Cannot stop the mDNS browser: {e}")

    return list(found.values())


def configured_lan_endpoints(hass: HomeAssistant) -> set[str]:
    """'host:port' and 'host' of every configured LAN gateway (lower case)."""
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    endpoints = set()
    for gateway in (config.get(CONF_GATEWAY) or []):
        address = str(gateway.get(CONF_GATEWAY_ADDRESS) or '').strip().lower().rstrip('.')
        if not address:
            continue
        endpoints.add(address)
        port = gateway.get(CONF_GATEWAY_PORT)
        if port:
            endpoints.add(f"{address}:{port}")
    return endpoints


def describe_mdns_candidate(service: dict) -> dict | None:
    """One announced service as a gateway candidate. None if it is nothing we support."""
    device_type = gateway_type_of_mdns_name(service.get('name'))
    if device_type is None:
        return None

    hw_type, description = _label_of(device_type)
    suggest_only = device_type in MDNS_SUGGEST_ONLY
    return {
        'connection': 'lan',
        'device_type': device_type,
        # the ip address is what a gateway is reached at; the host name is only shown
        'address': service.get('address'),
        'port': service.get('port'),
        'hostname': service.get('hostname'),
        'service_name': service.get('name'),
        'hw_type': hw_type,
        'description': description,
        'confident': not suggest_only,
        'reason': (f"Announced itself via mDNS as '{service.get('name')}'."
                   if not suggest_only else
                   "This is the ESP2 network bridge which this integration publishes itself for "
                   "the EnOcean Device Manager - connecting Home Assistant to it would be a "
                   "loop. Add it only if it belongs to another installation."),
    }


def mdns_candidates(services: list[dict], configured: set[str]) -> list[dict]:
    """Candidates of the announced services, without the ones which are configured already."""
    candidates = []
    seen = set()
    for service in services or []:
        candidate = describe_mdns_candidate(service)
        if candidate is None:
            continue
        address = str(candidate.get('address') or '').lower()
        hostname = str(candidate.get('hostname') or '').lower()
        endpoints = {address, hostname, f"{address}:{candidate.get('port')}",
                     f"{hostname}:{candidate.get('port')}"}
        if endpoints & configured:
            LOGGER.debug(f"[{LOG_PREFIX_PNP}] {candidate['service_name']} is already "
                         f"configured - skipped.")
            continue
        key = f"{address}:{candidate.get('port')}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


async def async_discover_mdns_gateways(hass: HomeAssistant) -> list[dict]:
    """LAN gateways which announce themselves via mDNS (zeroconf/bonjour).

    Uses the Zeroconf instance of Home Assistant, so no second socket is opened.
    """
    try:
        from homeassistant.components import zeroconf as ha_zeroconf

        instance = await ha_zeroconf.async_get_instance(hass)
        services = await hass.async_add_executor_job(browse_mdns_services, instance)
    except Exception as e:  # noqa: BLE001 - without zeroconf the serial detection still works
        LOGGER.warning(f"[{LOG_PREFIX_PNP}] Cannot browse for mDNS services: {e}")
        return []

    candidates = mdns_candidates(services, configured_lan_endpoints(hass))
    for candidate in candidates:
        LOGGER.info(f"[{LOG_PREFIX_PNP}] {candidate['hw_type']} announced via mDNS: "
                    f"{candidate['address']}:{candidate['port']} "
                    f"({candidate['service_name']})")
    return candidates


### ---------------------------------------------------------------------------
### which devices can be added without any doubt
### ---------------------------------------------------------------------------

def derive_bus_candidates(members: list[dict], configured: dict) -> dict:
    """Devices of the bus positions of one or more gateways.

    A position is only taken over when its model was identified beyond doubt: the discovery
    reply named a model, that model maps to exactly one device class (`model_candidates` is
    empty) and the device catalog knows the platform and the EEP of it. Multi channel devices
    (e.g. an FSR14-4x) result in one device per channel.

    `configured` is the result of device_config.get_configured_addresses().
    """
    candidates = []
    skipped = []

    by_gateway = configured.get('by_gateway') or {}

    for member in members:
        gateway_id = member.get('gateway_id')
        position = member.get('bus_address')
        known = {str(address).upper() for address in by_gateway.get(gateway_id, set())}

        if member.get('parent_bus_address'):
            continue        # channel of the device above, handled with its parent
        if member.get('is_fam') or str(member.get('device_class') or '') in GATEWAY_DEVICE_CLASSES:
            continue        # a gateway module is added as gateway, not as device
        if not member.get('device_class'):
            skipped.append({'gateway_id': gateway_id, 'address': local_address(position),
                            'reason': "The position did not answer the discovery yet - "
                                      "its model is unknown."})
            continue
        if member.get('model_candidates'):
            skipped.append({'gateway_id': gateway_id, 'address': local_address(position),
                            'device_class': member['device_class'],
                            'reason': f"The model is used by several device classes "
                                      f"({member['model_candidates']}) - please pick one."})
            continue
        platform = member.get('suggested_platform')
        eep = member.get('suggested_eep')
        if not platform or not eep:
            skipped.append({'gateway_id': gateway_id, 'address': local_address(position),
                            'device_class': member['device_class'],
                            'reason': f"The device catalog has no template for "
                                      f"{member['device_class']}."})
            continue

        channels = int(member.get('channel_count') or 1)
        for channel in range(channels):
            address = local_address(position + channel)
            if address.upper() in known:
                continue
            name = member['device_class'] if channels == 1 \
                else f"{member['device_class']} ch{channel + 1}"
            device = {CONF_ID: address, CONF_EEP: eep, CONF_NAME: name}
            if platform in SENDER_PLATFORMS:
                sender_eep = member.get('suggested_sender_eep')
                if not sender_eep:
                    skipped.append({'gateway_id': gateway_id, 'address': address,
                                    'device_class': member['device_class'],
                                    'reason': "The catalog knows no sender EEP for this "
                                              "actuator - it cannot be controlled."})
                    continue
                device[CONF_SENDER] = {CONF_ID: local_sender_id(position + channel),
                                       CONF_EEP: sender_eep}
            candidates.append({'gateway_id': gateway_id, 'platform': platform, 'device': device,
                               'source': 'bus_position', 'device_class': member['device_class']})

    return {'candidates': candidates, 'skipped': skipped}


def derive_memory_candidates(members: list[dict], configured: dict) -> dict:
    """Senders which were found in the memory of a bus actuator.

    Their key function names the EEP (see bus_members.classify_taught_in_sensor), which is
    far more reliable than guessing it from telegram data. Senders of Home Assistant itself
    (role 'ha_sender') are skipped - they are no devices.
    """
    candidates = []
    skipped = []
    seen = set()
    known_all = {str(address).upper() for address in (configured.get('all') or set())}

    for member in members:
        gateway_id = member.get('gateway_id')
        for sensor in (member.get('taught_in') or []):
            address = str(sensor.get('sensor_id') or '').upper()
            if not address or sensor.get('role') == 'ha_sender' or address in seen:
                continue
            if address in known_all:
                seen.add(address)
                continue
            platform = sensor.get('suggested_platform')
            eep = sensor.get('suggested_eep')
            if not platform or not eep:
                skipped.append({'gateway_id': gateway_id, 'address': address,
                                'reason': f"The key function "
                                          f"'{sensor.get('key_function_name')}' does not name "
                                          f"an EEP - the profile has to be chosen manually."})
                seen.add(address)
                continue
            if platform in SENDER_PLATFORMS:
                continue    # an actuator is taken over at its bus position, not here
            seen.add(address)
            candidates.append({
                'gateway_id': gateway_id, 'platform': platform, 'source': 'device_memory',
                'device': {CONF_ID: address, CONF_EEP: eep,
                           CONF_NAME: sensor.get('suggested_name') or f"Sensor {address}"},
            })

    return {'candidates': candidates, 'skipped': skipped}


def derive_telegram_candidates(unknown_devices: list[dict], configured: dict) -> dict:
    """Addresses which send telegrams but are not configured.

    Only a 4BS teach-in telegram states the EEP of a device ('confirmed', see
    telegram_suggestions.py). Everything which was merely derived from the message type or
    the data bytes stays a manual decision.
    """
    candidates = []
    skipped = []
    known_all = {str(address).upper() for address in (configured.get('all') or set())}

    for device in unknown_devices or []:
        address = str(device.get('address') or '').upper()
        suggested = device.get('suggested') or {}
        if not address or address in known_all:
            continue
        if suggested.get('confidence') != 'confirmed':
            skipped.append({'address': address, 'reason':
                            f"The EEP is only a guess "
                            f"({suggested.get('eep') or 'no candidate'}, "
                            f"{suggested.get('confidence') or 'unknown'}) - it has to be confirmed."})
            continue
        platform = suggested.get('platform')
        if platform in SENDER_PLATFORMS or not platform:
            skipped.append({'address': address, 'reason':
                            "The device sends a known profile, but it is an actuator - it needs "
                            "a sender address which has to be taught in."})
            continue
        gateway_ids = device.get('gateway_ids') or []
        candidates.append({
            'gateway_id': gateway_ids[0] if gateway_ids else None,
            'platform': platform, 'source': 'teach_in_telegram',
            'device': {CONF_ID: address, CONF_EEP: suggested['eep'],
                       CONF_NAME: suggested.get('hw_type') or f"Device {address}"},
        })

    return {'candidates': candidates, 'skipped': skipped}


def merge_candidates(*results: dict) -> dict:
    """Merge the candidates of all sources, keeping the first (most reliable) one per address."""
    candidates = []
    skipped = []
    seen = set()
    for result in results:
        for candidate in result.get('candidates') or []:
            key = (candidate.get('gateway_id'), str(candidate['device'][CONF_ID]).upper())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
        skipped.extend(result.get('skipped') or [])
    return {'candidates': candidates, 'skipped': skipped}


### ---------------------------------------------------------------------------
### the run
### ---------------------------------------------------------------------------

# a gateway which was just created needs a moment until its connection is up
GATEWAY_SETUP_TIMEOUT = 30
# reading the memory of every bus device can take minutes
BUS_SCAN_TIMEOUT = 600
# after the scan the taught-in senders are parsed from the memory images
BUS_SCAN_SETTLE = 3
# how often the devices which are already identified are adopted while a bus is still being
# read (see _adopt_while_scanning). Each pass which finds something writes the options of the
# config entry once per gateway, so this is a compromise between "appears at once" and "does
# not rewrite the configuration every second".
ADOPT_INTERVAL = 5


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# The three stages of a run. The web ui draws them as a flow and highlights the active one,
# so it needs a machine readable name next to the readable text of `step`.
STAGE_PORTS = 'ports'           # probing the serial ports for a gateway
STAGE_BUS = 'bus'               # reading the bus of a bus gateway
STAGE_DEVICES = 'devices'       # deriving and adding the devices
STAGES = [STAGE_PORTS, STAGE_BUS, STAGE_DEVICES]


def get_state(hass: HomeAssistant) -> dict:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    return domain_data.setdefault(DATA_PLUG_AND_PLAY, {
        'running': False, 'step': None, 'stage': None, 'started_at': None,
        'last_run': None, 'last_report': None, 'scanned_gateways': [], 'unsubscribe': None,
    })


def _set_step(hass: HomeAssistant, stage: str | None, step: str | None) -> None:
    state = get_state(hass)
    state['stage'] = stage
    state['step'] = step
    if step:
        LOGGER.info(f"[{LOG_PREFIX_PNP}] {step}")


async def async_detect_gateways(hass: HomeAssistant, include_mdns: bool = True) -> dict:
    """Stage 1 on its own: which gateways are there? Creates nothing, reads no bus.

    `async_run` answers "set up what is connected", which is the right thing in a house but
    the wrong thing when the question is only *whether the detection recognizes this stick*:
    a run creates config entries and reads the bus of every new bus gateway, which locks it
    for minutes. This is the read-only half - it opens the free ports, asks them, and reports
    what it found. Safe to call repeatedly.

    Used by the websocket command `eltako/plug_and_play/probe`, by the CLI (`detect`) and by
    the tests. The result carries the same candidate dicts `async_run` would act on, so a
    caller can feed one straight into `build_gateway`.
    """
    from .gateway_scan import async_remember_stick_identities, scan as scan_ports

    scan = await hass.async_add_executor_job(scan_ports, hass)
    probe_list = ports_to_probe(scan, configured_serial_paths(hass))
    ports_by_device = {str(port.get('device')): port for port in probe_list}

    # the serial probe and the mDNS browse know nothing of each other and each occupies its
    # own executor thread - run them at the same time, so the fixed browse window of
    # MDNS_BROWSE_SECONDS hides inside the seconds the probe takes anyway
    detected, lan_candidates = await asyncio.gather(
        async_probe_ports(hass, probe_list) if probe_list
        else asyncio.sleep(0, result={}),
        async_discover_mdns_gateways(hass) if include_mdns
        else asyncio.sleep(0, result=[]),
    )

    # a probe is the only moment at which a stick nobody uses says who it is - remember the
    # ids, so the passive port scan can show them and a gateway created from this candidate
    # can be found again after the ports were renumbered
    await async_remember_stick_identities(hass, detected, ports_by_device)

    candidates = [describe_candidate(device, detection, ports_by_device.get(device))
                  for device, detection in detected.items()]
    candidates.extend(lan_candidates)

    return {
        'ports_scanned': len(scan.get('ports') or []),
        'ports_probed': len(probe_list),
        'ports_skipped': [port['device'] for port in (scan.get('ports') or [])
                          if port.get('device') not in ports_by_device],
        'mdns_found': len(lan_candidates),
        'gateways_detected': candidates,
        # a candidate which is only suggested needs a human to confirm its type - an
        # FGW14-USB cannot be told apart from any other silent serial device
        'gateways_suggested': [c for c in candidates if not c['confident']],
    }


async def async_run(hass: HomeAssistant, rescan_bus: bool = False,
                    add_devices: bool = True, detect_gateways: bool = True) -> dict:
    """One complete plug & play pass. Returns the report.

    rescan_bus reads the bus of every bus gateway again, also of those which were scanned
    before. Without it only a bus which was never scanned is read - locking the bus for
    minutes must not happen behind the back of the user over and over again.

    detect_gateways=False skips the port probe and the creation of gateways and starts at the
    bus. That is what the automatic scan of a newly set up bus gateway uses
    (async_auto_scan_bus): the gateway is already there, and probing the ports would create
    gateways the user never asked for.
    """
    from ..observation import bus_members
    from ..config import device_config
    from .. import simulation
    from ..core.websocket import get_gateways

    state = get_state(hass)
    if state.get('running'):
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] A detection is already running - skipped.")
        return dict(state.get('last_report') or {}, skipped='already_running')

    state.update({'running': True, 'started_at': _utc_now_iso(),
                  'stage': STAGE_PORTS if detect_gateways else STAGE_BUS,
                  'step': "Scanning serial ports" if detect_gateways else "Reading the bus"})
    report = {
        'started_at': state['started_at'], 'finished_at': None, 'rescan_bus': bool(rescan_bus),
        'gateways_detected': [], 'gateways_added': [], 'gateways_suggested': [],
        'buses_read': [], 'devices_added': [], 'devices_skipped': [], 'warnings': [],
    }
    # published while it is still being filled: the web ui polls the status every few seconds
    # and shows the stages of a running detection filling up (`finished_at` tells them apart)
    state['last_report'] = report

    try:
        if detect_gateways:
            ### 1) which gateway is plugged in or announces itself on the network?
            # one call for both sources - `async_detect_gateways` probes the free serial ports and
            # browses mDNS **in parallel**, so this stage costs max(probe, browse), not their sum
            _set_step(hass, STAGE_PORTS, "Probing the free serial ports and listening for "
                                         "LAN gateways (mDNS) in parallel")
            detection = await async_detect_gateways(hass)
            candidates = list(detection['gateways_detected'])
            report['ports_probed'] = detection['ports_probed']
            report['mdns_found'] = detection['mdns_found']

            report['gateways_detected'] = list(candidates)
            report['gateways_suggested'] = [candidate for candidate in candidates
                                            if not candidate['confident']]

            ### 2) create the gateways which were identified beyond doubt
            for candidate in candidates:
                if not candidate['confident']:
                    continue
                where = candidate.get('serial_path') or \
                    f"{candidate.get('address')}:{candidate.get('port')}"
                _set_step(hass, STAGE_PORTS, f"Creating gateway {candidate['hw_type']} on {where}")
                try:
                    created = await _async_create_gateway(hass, candidate)
                    report['gateways_added'].append(created)
                except vol.Invalid as e:
                    report['warnings'].append(f"{candidate['hw_type']} on {where}: {e}")

        ### 3) read the bus of the bus gateways - every bus in parallel: each one is its own
        ### serial or tcp connection with its own lock, they cannot talk over each other. The
        ### wall clock of this stage is the slowest bus, not the sum of all of them.
        gateways = get_gateways(hass)
        bus_targets = [gateway for gateway in gateways
                       if GatewayDeviceType.is_bus_gateway(gateway.dev_type)
                       # a simulated bus has no device memory to read; its devices are known
                       # anyway (they are taken over as candidates in the next step)
                       and not getattr(gateway, 'is_simulated', False)
                       and (rescan_bus or not _bus_was_read(hass, bus_members, gateway.dev_id))]
        if bus_targets:
            names = ", ".join(str(gateway.dev_id) for gateway in bus_targets)
            _set_step(hass, STAGE_BUS, f"Reading the bus of gateway(s) {names} "
                                       f"(this can take a few minutes)")
            watcher = asyncio.ensure_future(
                _watch_bus_progress(hass, bus_members, [g.dev_id for g in bus_targets]))
            # every position which answered is adopted while the other positions are still
            # being read - see _adopt_while_scanning
            adopter = asyncio.ensure_future(_adopt_while_scanning(hass, report, add_devices))
            try:
                reads = await asyncio.gather(
                    *[_async_read_bus(hass, bus_members, gateway) for gateway in bus_targets])
            finally:
                watcher.cancel()
                adopter.cancel()
            for gateway, read in zip(bus_targets, reads):
                report['buses_read'].append(read)
                if read.get('finished'):
                    scanned = state.setdefault('scanned_gateways', [])
                    if gateway.dev_id not in scanned:
                        scanned.append(gateway.dev_id)
                else:
                    report['warnings'].append(f"The bus scan of gateway {gateway.dev_id} did "
                                              f"not finish within {BUS_SCAN_TIMEOUT} s.")

        ### 4) add every device which is identified without any doubt. Most of them are already
        ### in by now (they were adopted during the scan); this pass catches what became clear
        ### only with the last memory row and everything outside the bus.
        _set_step(hass, STAGE_DEVICES, "Collecting the devices which can be identified")
        await _async_collect_and_add(hass, report, add_devices)

        ### 5) teach the sender addresses of Home Assistant into the actuators which were just
        ### found. Without them an actuator does not react to a single command - and the moment
        ### to write them is exactly this one: the devices are configured now, the FAM14 which
        ### can write is connected now, and the bus is free again. Runs last on purpose, and
        ### only for the buses which were really read in this run.
        read_now = [read['gateway_id'] for read in report['buses_read'] if read.get('finished')]
        if add_devices and read_now:
            await _async_teach_in_after_scan(hass, report, read_now)

        report['finished_at'] = _utc_now_iso()
        LOGGER.info(f"[{LOG_PREFIX_PNP}] Finished: {len(report['gateways_added'])} gateway(s) and "
                    f"{len(report['devices_added'])} device(s) added, "
                    f"{len(report['devices_skipped'])} device(s) need a decision, "
                    f"{len(report['warnings'])} warning(s).")
        return report
    except Exception as e:  # noqa: BLE001 - a failed detection must never break the integration
        LOGGER.error(f"[{LOG_PREFIX_PNP}] Detection failed: {e}", exc_info=True)
        report['finished_at'] = _utc_now_iso()
        report['warnings'].append(f"The detection failed: {e}")
        return report
    finally:
        # The buses are free again, so the gateways whose reload was postponed while they were
        # being read get it now - that is what turns the devices which were added during the
        # scan into entities. Still *before* running=False: a reload sets the gateway up again,
        # and the automatic bus scan of a new gateway steps aside while a detection runs.
        from ..core.integration import async_flush_pending_reloads
        await async_flush_pending_reloads(hass)
        state.update({'running': False, 'step': None, 'stage': None,
                      'last_run': _utc_now_iso(), 'last_report': report})


async def _async_collect_and_add(hass: HomeAssistant, report: dict, add_devices: bool) -> int:
    """Derive the devices from everything which is known *right now* and add the new ones.

    Called repeatedly: every few seconds while a bus is being read and once at the end of the
    run. Adding twice is impossible without any bookkeeping here - `get_configured_addresses`
    is read again on every pass, so a device which is already in the configuration is not a
    candidate anymore. Returns how many devices were added in this pass.
    """
    from ..observation import bus_members
    from ..config import device_config
    from .. import simulation

    registry = bus_members.get_registry(hass)
    if registry is not None:
        await registry.async_parse_taught_in()
    members = registry.get_members(hass) if registry is not None else []
    configured = device_config.get_configured_addresses(hass)

    merged = merge_candidates(
        # a simulated device states everything about itself, so it comes first
        simulation.derive_candidates(hass, configured),
        derive_bus_candidates(members, configured),
        derive_memory_candidates(members, configured),
        derive_telegram_candidates(_unknown_devices(hass), configured),
    )
    # what still needs a human decision is a snapshot of this pass, not a sum of all passes -
    # a device which was unclear a minute ago may be identified by now
    report['devices_skipped'] = merged['skipped']

    if not add_devices:
        report['devices_pending'] = merged['candidates']
        return 0

    added, warnings = await _async_add_devices(hass, device_config, merged['candidates'])
    report['devices_added'].extend(added)
    report['warnings'].extend(warnings)
    return len(added)


async def _async_teach_in_after_scan(hass: HomeAssistant, report: dict,
                                     gateway_ids: list) -> None:
    """Write the Home Assistant sender ids into the actuators of the buses which were read.

    A bus actuator only reacts to senders which are in its memory, so a device which was just
    added would be listed in Home Assistant and do nothing when it is switched. Reading and
    programming both need the FAM14, and it is connected right now - asking the user to press
    a second button afterwards would be a trap for exactly the installation this search is for.

    Errors are collected as warnings: an actuator whose memory is full or which does not
    answer must not turn a successful search into a failed one.
    """
    from ..observation import bus_members
    from ..core.websocket import get_gateways

    _set_step(hass, STAGE_DEVICES, "Teaching the Home Assistant senders into the actuators")
    report['senders_taught_in'] = []

    for gateway in get_gateways(hass):
        if gateway.dev_id not in gateway_ids:
            continue
        try:
            results = await bus_members.async_teach_in_senders(hass, gateway)
        except Exception as e:  # noqa: BLE001 - the search itself was fine
            report['warnings'].append(f"The senders could not be taught into the actuators of "
                                      f"gateway {gateway.dev_id}: {e}")
            LOGGER.error(f"[{LOG_PREFIX_PNP}] Teach-in after the scan of gateway "
                         f"{gateway.dev_id} failed: {e}", exc_info=True)
            continue

        _note_teach_in_results(report, f"gateway {gateway.dev_id}", results)

        ### and the gateways the installation may be operated with later. A wireless gateway
        ### only transmits senders out of its own base id range, and only the FAM14 which is
        ### connected right now can write them into an actuator - so the moment to do it is
        ### this one, not when somebody unplugs the FAM14 and wonders why nothing switches.
        for target in _programmable_radio_gateways(hass):
            try:
                answer = await bus_members.async_program_gateway_senders(hass, gateway, target)
            except Exception as e:  # noqa: BLE001
                report['warnings'].append(f"The senders of '{target.dev_name}' could not be "
                                          f"programmed into the actuators of gateway "
                                          f"{gateway.dev_id}: {e}")
                LOGGER.error(f"[{LOG_PREFIX_PNP}] Programming '{target.dev_name}' on gateway "
                             f"{gateway.dev_id} failed: {e}", exc_info=True)
                continue
            if answer.get('error'):
                report['warnings'].append(f"'{target.dev_name}' was not programmed: "
                                          f"{answer.get('message')}")
                continue
            _note_teach_in_results(report, f"'{target.dev_name}'", answer.get('results') or [])


def _programmable_radio_gateways(hass: HomeAssistant) -> list:
    """The connected wireless gateways whose senders are worth writing into the actuators.

    Only connected ones, and only those which reported a base id: without it there is no
    address to hand out, and a gateway which is configured but not plugged in cannot be the
    one the installation is about to be operated with.
    """
    from ..const import GatewayDeviceType
    from ..core.websocket import get_gateways

    targets = []
    for gateway in get_gateways(hass):
        if GatewayDeviceType.is_bus_gateway(gateway.dev_type):
            continue
        try:
            if not gateway._bus.is_active():
                continue
            if not gateway.base_id or gateway.base_id[0][0] != 0xFF:
                continue
        except Exception:   # noqa: BLE001 - a gateway which is not initialized is not a target
            continue
        targets.append(gateway)
    return targets


def _note_teach_in_results(report: dict, who: str, results: list[dict]) -> None:
    """Sort one write run into the report: what was written, what refused."""
    written = [r for r in results if r.get('result') == 'written']
    failed = [r for r in results if r.get('result') in ('error', 'unsupported', 'out_of_range')]
    report['senders_taught_in'].extend(written)
    if failed:
        report['warnings'].append(
            f"{len(failed)} actuator(s) did not take the sender of {who}: "
            + ", ".join(f"{r.get('address')} ({r.get('message') or r.get('result')})"
                        for r in failed[:5]))
    LOGGER.info(f"[{LOG_PREFIX_PNP}] {who}: {len(written)} sender(s) written, "
                f"{len(results) - len(written) - len(failed)} already taught in, "
                f"{len(failed)} refused.")


async def _adopt_while_scanning(hass: HomeAssistant, report: dict, add_devices: bool) -> None:
    """Add the devices which are already identified while the bus is still being read.

    Reading a bus takes minutes: a FAM14 with 30 actuators is asked position by position and
    then memory row by memory row. Waiting for the last row before writing anything meant that
    a user watched a progress bar for minutes with an empty device list, and a scan which was
    interrupted (a timeout, a restart) left nothing at all behind.

    So every position which has answered is adopted as soon as it is unambiguous. What the
    scan adds later - the senders taught into a device, which are only known once its memory
    was read - simply appears in one of the next passes.

    Deliberately not after every single position: adding rewrites the options of the config
    entry, so the passes are paced and each of them adds everything which became clear since
    the last one, in one write per gateway.

    The gateway is *not* reloaded meanwhile (core/integration.async_reload_entry postpones
    that while the bus is busy) - a reload would close the serial port under the running scan.
    """
    try:
        while True:
            await asyncio.sleep(ADOPT_INTERVAL)
            try:
                count = await _async_collect_and_add(hass, report, add_devices)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - the scan must not die with the adoption
                LOGGER.warning(f"[{LOG_PREFIX_PNP}] Could not adopt the devices found so far: {e}",
                               exc_info=True)
                continue
            if count:
                LOGGER.info(f"[{LOG_PREFIX_PNP}] {count} device(s) added while the bus is still "
                            f"being read ({len(report['devices_added'])} in this run so far).")
    except asyncio.CancelledError:
        pass


def _unknown_devices(hass: HomeAssistant) -> list[dict]:
    """Addresses which sent telegrams but are not configured (empty if recording is off)."""
    from ..observation.enocean_logger import get_telegram_logger

    logger = get_telegram_logger(hass)
    if logger is None:
        return []
    try:
        return logger.get_statistics().get('unknown_devices') or []
    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] Cannot read the telegram statistics: {e}")
        return []


def build_gateway(candidate: dict, gateway_id: int) -> dict:
    """Configuration of a detected gateway: a serial one carries its port, a LAN one its host."""
    gateway = {
        CONF_ID: gateway_id,
        CONF_DEVICE_TYPE: candidate['device_type'],
        CONF_BASE_ID: '00-00-00-00',    # FAM14 and ESP3 gateways report it themselves
        CONF_NAME: candidate['hw_type'],
    }
    if candidate.get('connection') == 'lan':
        gateway[CONF_GATEWAY_ADDRESS] = candidate['address']
        if candidate.get('port'):
            gateway[CONF_GATEWAY_PORT] = candidate['port']
    else:
        gateway[CONF_SERIAL_PATH] = candidate['serial_path']
    return gateway


async def _async_create_gateway(hass: HomeAssistant, candidate: dict) -> dict:
    """Store a detected gateway and create its config entry, so it is set up right away."""
    from ..config import gateway_config

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    gateway = build_gateway(candidate, gateway_config.get_next_free_id(hass, config))
    validated = await gateway_config.async_add_gateway(hass, gateway)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={'source': SOURCE_UI_GATEWAY},
        data={CONF_GATEWAY_DESCRIPTION: gateway_config.get_description(validated),
              CONF_SERIAL_PATH: gateway_config.get_serial_path(validated)},
    )

    created = {'id': validated[CONF_ID], 'device_type': candidate['device_type'],
               'connection': candidate.get('connection', 'serial'),
               'serial_path': gateway_config.get_serial_path(validated),
               'name': candidate['hw_type'],
               'config_entry_created': result.get('type') == 'create_entry'}
    # Only a bus gateway is waited for: its bus is read in the next step, which needs a live
    # connection. Waiting for a transceiver or a LAN gateway would only stall the run if it is
    # not reachable - its entities appear on their own as soon as it connects.
    device_type = GatewayDeviceType.find(str(candidate['device_type']))
    if created['config_entry_created'] and GatewayDeviceType.is_bus_gateway(device_type):
        created['connected'] = await _async_wait_for_gateway(hass, validated[CONF_ID])
    LOGGER.info(f"[{LOG_PREFIX_PNP}] Created gateway {created['name']} (id {created['id']}) "
                f"on {created['serial_path']}.")
    return created


async def async_auto_scan_bus(hass: HomeAssistant, gateway) -> dict | None:
    """Read the bus of a bus gateway which Home Assistant sees for the first time.

    A FAM14 or FGW14-USB does not tell anybody what sits on its bus: the actuators and the
    senders taught into them are only known once the device memories were read. So a bus
    gateway which was never scanned is scanned once, on its own - otherwise the simple view
    shows an empty page next to a gateway which is connected, and the only way out is a button
    the user has to find first.

    Exactly once, and only where it is harmless:

    * only for a real bus gateway (a transceiver has no bus, a simulated one no memory)
    * not when the bus was already read - by an earlier scan, by plug & play or by hand
    * not when a detection is running anyway: that one reads the bus itself
    * the attempt is remembered **before** it starts and persisted, so a bus which does not
      answer is not locked for BUS_SCAN_TIMEOUT again after every restart

    Reading is deliberately left to `async_run` (without the port probe): the web ui shows its
    progress and its report already, and whatever the scan reveals beyond doubt is adopted the
    same way a detection started by hand would adopt it.
    """
    from ..observation import bus_members

    gateway_id = getattr(gateway, 'dev_id', None)
    if gateway_id is None:
        return None
    if not GatewayDeviceType.is_bus_gateway(getattr(gateway, 'dev_type', None)):
        return None
    if getattr(gateway, 'is_simulated', False):
        return None

    registry = bus_members.get_registry(hass)
    if registry is None:
        return None
    if registry.was_auto_scanned(gateway_id):
        return None
    if _bus_was_read(hass, bus_members, gateway_id):
        # nothing to do, but do not try again on the next restart either
        registry.mark_auto_scanned(gateway_id)
        return None

    # a scan needs a live connection; if the gateway never comes up nothing is marked, so a
    # later restart with working hardware still gets its scan
    if not await _async_wait_for_gateway(hass, gateway_id):
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] Gateway {gateway_id} is not connected - the automatic "
                     f"bus scan is postponed.")
        return None

    if get_state(hass).get('running'):
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] A detection is already running - it reads the bus of "
                     f"gateway {gateway_id} itself.")
        return None

    registry.mark_auto_scanned(gateway_id)
    LOGGER.info(f"[{LOG_PREFIX_PNP}] Gateway {gateway_id} is a bus gateway whose bus was never "
                f"read - reading it once now. This takes a few minutes and the devices on the "
                f"bus do not react while it runs.")
    return await async_run(hass, detect_gateways=False)


async def _async_wait_for_gateway(hass: HomeAssistant, gateway_id: int) -> bool:
    """Wait until the gateway object exists and its connection is up."""
    from ..core.websocket import get_gateways

    for _ in range(GATEWAY_SETUP_TIMEOUT):
        gateway = next((g for g in get_gateways(hass) if g.dev_id == gateway_id), None)
        if gateway is not None:
            try:
                if gateway._bus.is_active():
                    return True
            except Exception:   # noqa: BLE001 - not fully initialized yet
                pass
        await asyncio.sleep(1)
    return False


def _bus_was_read(hass: HomeAssistant, bus_members, gateway_id: int) -> bool:
    """True if the memory of this bus was already read (in this run or in an earlier session)."""
    if gateway_id in (get_state(hass).get('scanned_gateways') or []):
        return True
    registry = bus_members.get_registry(hass)
    if registry is None:
        return False
    return any(member.get('scanned_at') for member in registry.get_members(hass)
               if member.get('gateway_id') == gateway_id)


async def _watch_bus_progress(hass: HomeAssistant, bus_members, gateway_ids: list[int]) -> None:
    """Mirror the progress of the running scans into the step text, once a second.

    The overview page shows `step` live, so this is all it takes for "how far is it?" -
    several parallel scans become one line ("gateway 1: position 11/14, memory 23/56 ·
    gateway 3: position 2/8"). Cancelled by the caller when the last scan is done.
    """
    try:
        while True:
            await asyncio.sleep(1)
            parts = []
            for gateway_id in gateway_ids:
                progress = bus_members.get_scan_progress(gateway_id)
                if progress:
                    parts.append(f"gateway {gateway_id}: "
                                 f"{bus_members.describe_scan_progress(progress)}")
            if parts:
                _set_step(hass, STAGE_BUS, f"Reading the bus - {' · '.join(parts)}")
    except asyncio.CancelledError:
        pass


async def _async_read_bus(hass: HomeAssistant, bus_members, gateway) -> dict:
    """Discovery plus complete memory of every device of one bus. Blocks the bus while running."""
    registry = bus_members.get_registry(hass)
    positions = sorted({member['bus_address']
                        for member in (registry.get_members(hass) if registry else [])
                        if member['gateway_id'] == gateway.dev_id})
    if not positions:
        positions = list(range(1, 65))      # a fresh bus was not polled yet

    # only one operation may talk on the bus at a time - a scan which is refused here is not an
    # error, it means somebody else (a scan started by hand, a teach-in) already has it
    if not bus_members.start_bus_scan_thread(hass, gateway, positions):
        return {'gateway_id': gateway.dev_id, 'finished': False, 'reason': 'already_running',
                'busy_with': getattr(gateway, 'bus_busy_reason', None)}

    finished = False
    for _ in range(BUS_SCAN_TIMEOUT):
        await asyncio.sleep(1)
        if not gateway.is_bus_busy:
            finished = True
            break
    await asyncio.sleep(BUS_SCAN_SETTLE)

    return {'gateway_id': gateway.dev_id, 'finished': finished, 'positions': len(positions)}


async def _async_add_devices(hass: HomeAssistant, device_config,
                             candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Add the candidates like devices created in the web ui (editable and removable).

    Grouped per gateway and stored in one go, so a gateway is reloaded once and not once per
    device (see device_config.async_add_ui_devices).
    """
    by_gateway: dict[object, list[dict]] = {}
    for candidate in candidates:
        by_gateway.setdefault(candidate.get('gateway_id'), []).append(candidate)

    added = []
    warnings = []
    for gateway_id, group in by_gateway.items():
        entry = device_config._find_gateway_entry(hass, gateway_id) if gateway_id is not None else None
        if entry is None:
            warnings.append(f"Gateway {gateway_id} is not set up in Home Assistant - "
                            f"{len(group)} detected device(s) were skipped.")
            continue

        by_address = {(candidate['platform'], str(candidate['device'][CONF_ID]).upper()): candidate
                      for candidate in group}
        result = await device_config.async_add_ui_devices(
            hass, entry, [(candidate['platform'], candidate['device']) for candidate in group])

        for platform, device in result['added']:
            candidate = by_address.get((platform, str(device[CONF_ID]).upper()), {})
            added.append({'gateway_id': gateway_id, 'platform': platform,
                          'address': device[CONF_ID], 'eep': device.get(CONF_EEP),
                          'name': device.get(CONF_NAME), 'source': candidate.get('source')})
        for platform, address, message in result['errors']:
            warnings.append(f"{platform} {address}: {message}")

    return added, warnings


### ---------------------------------------------------------------------------
### periodic detection
### ---------------------------------------------------------------------------

# a gateway needs a moment after a restart before its bus can be read
STARTUP_DELAY = 60


def is_enabled(general_settings: dict) -> bool:
    return bool((general_settings or {}).get(CONF_PLUG_AND_PLAY, False))


def get_interval(general_settings: dict) -> int:
    try:
        return int((general_settings or {}).get(CONF_PLUG_AND_PLAY_INTERVAL, 0) or 0)
    except (TypeError, ValueError):
        return 0


@callback
def apply_settings(hass: HomeAssistant, general_settings: dict = None) -> dict:
    """(Re)start or stop the periodic detection according to the general settings.

    Called during setup and again whenever the settings were changed in the web ui, so the
    checkbox takes effect without a restart.
    """
    from homeassistant.helpers.event import async_track_time_interval

    settings = general_settings if general_settings is not None \
        else config_helpers.get_general_settings_from_configuration(hass)
    state = get_state(hass)

    unsubscribe = state.get('unsubscribe')
    if unsubscribe is not None:
        unsubscribe()
        state['unsubscribe'] = None

    enabled = is_enabled(settings)
    interval = get_interval(settings)
    if not enabled or interval <= 0:
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] Periodic detection is off "
                     f"(enabled={enabled}, interval={interval} min).")
        return {'enabled': enabled, 'interval': interval, 'periodic': False}

    async def _tick(now=None) -> None:
        if get_state(hass).get('running'):
            return
        await async_run(hass)

    state['unsubscribe'] = async_track_time_interval(hass, _tick, timedelta(minutes=interval))
    LOGGER.info(f"[{LOG_PREFIX_PNP}] Enabled - checking every {interval} minute(s) whether a "
                f"gateway was plugged in.")
    return {'enabled': True, 'interval': interval, 'periodic': True}


async def async_setup_detection(hass: HomeAssistant, general_settings: dict) -> None:
    """Set up the plug & play detection during the setup of the integration.

    Deliberately not called `async_setup`: that name belongs to the setup callback of an
    integration, whose return value Home Assistant evaluates as a bool.
    """
    register_websocket_commands(hass)
    apply_settings(hass, general_settings)

    if not is_enabled(general_settings):
        return

    async def _initial_run() -> None:
        # the gateways of the configuration connect first - their bus positions are needed to
        # decide which bus still has to be read
        await asyncio.sleep(STARTUP_DELAY)
        await async_run(hass)

    hass.async_create_task(_initial_run())


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

WS_PNP_REGISTERED = "plug_and_play_ws_registered"


def register_websocket_commands(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    if domain_data.get(WS_PNP_REGISTERED, False):
        return
    websocket_api.async_register_command(hass, ws_plug_and_play_status)
    websocket_api.async_register_command(hass, ws_plug_and_play_run)
    websocket_api.async_register_command(hass, ws_plug_and_play_probe)
    domain_data[WS_PNP_REGISTERED] = True


def get_status(hass: HomeAssistant) -> dict:
    from ..observation import bus_members

    settings = config_helpers.get_general_settings_from_configuration(hass)
    state = get_state(hass)
    return {
        'enabled': is_enabled(settings),
        'interval': get_interval(settings),
        'periodic': state.get('unsubscribe') is not None,
        'running': bool(state.get('running')),
        'step': state.get('step'),
        'stage': state.get('stage'),
        'stages': list(STAGES),
        # counters of every bus scan which runs right now (percent, position x/y, memory
        # rows) - the structured form of the step text, for a progress bar
        'bus_scans': bus_members.get_scan_progress(),
        'started_at': state.get('started_at'),
        'last_run': state.get('last_run'),
        'last_report': state.get('last_report'),
        'setting': CONF_PLUG_AND_PLAY,
        'hint': "Detects gateways which are plugged in, reads the bus of a new bus gateway and "
                "adds every device which can be identified without any doubt. Added devices "
                "behave like devices created here: they can be edited and removed again. The "
                "sender ids of added actuators still have to be taught in.",
    }


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_PLUG_AND_PLAY_STATUS})
@callback
def ws_plug_and_play_status(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg['id'], get_status(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_PLUG_AND_PLAY_RUN,
    vol.Optional('rescan_bus', default=False): bool,
    vol.Optional('enable'): vol.Any(bool, None),
})
@websocket_api.async_response
async def ws_plug_and_play_run(hass: HomeAssistant, connection, msg) -> None:
    """Switch plug & play on or off and/or start a detection run in the background.

    `enable` makes the button on the overview page and the checkbox in the configuration one
    single switch: True stores the setting and starts a run right away, False switches it off
    (and starts nothing), omitting it only starts a single run without changing the setting.

    A run can take minutes (reading a bus locks it), so the result is not awaited here - the
    web ui polls `eltako/plug_and_play/status` for the progress and the report.
    """
    from ..config import general_settings

    enable = msg.get('enable')
    if enable is not None:
        await general_settings.async_set_overrides(hass, {CONF_PLUG_AND_PLAY: bool(enable)})
        apply_settings(hass)
        if not enable:
            connection.send_result(msg['id'], {'started': False, 'reason': 'disabled',
                                               'status': get_status(hass)})
            return

    state = get_state(hass)
    if state.get('running'):
        connection.send_result(msg['id'], {'started': False, 'reason': 'already_running',
                                           'status': get_status(hass)})
        return

    hass.async_create_task(async_run(hass, rescan_bus=bool(msg.get('rescan_bus'))))
    connection.send_result(msg['id'], {'started': True, 'status': get_status(hass)})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_PLUG_AND_PLAY_PROBE,
    vol.Optional('include_mdns', default=True): bool,
})
@websocket_api.async_response
async def ws_plug_and_play_probe(hass: HomeAssistant, connection, msg) -> None:
    """Detect only - create nothing, read no bus. Answers "would this stick be recognized?".

    Unlike RUN this one is awaited: without the bus scan a probe takes seconds, and the caller
    (cli, test, a REST client) wants the answer, not a background task to poll.
    """
    result = await async_detect_gateways(hass, include_mdns=bool(msg.get('include_mdns', True)))
    connection.send_result(msg['id'], result)
