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

from ..const import *
from ..config import config_helpers
from ..catalog.device_catalog import describe_gateway_type

LOG_PREFIX_PNP = "Plug & Play"

### ---------------------------------------------------------------------------
### probing of the serial ports
### ---------------------------------------------------------------------------

# A port which is no gateway cannot be distinguished from a gateway which does not answer,
# so every test costs its full timeout. Therefore the number of retries is kept low - a
# gateway which is there answers on the first attempt.
PROBE_CONNECT_TIMEOUT = 1.0         # time granted to a communicator to open the port
PROBE_BASE_ID_TIMEOUT = 1.0         # the base id request of a FAM-USB really needs up to 1 s
PROBE_BASE_ID_RETRIES = 1

# base id request of a FAM-USB (ESP2, 'AB 58')
FAM_USB_BASE_ID_REQUEST = b'\xAB\x58\x00\x00\x00\x00\x00\x00\x00\x00\x00'

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


async def _async_detect_gateway(device: str, baud_rate: int, is_usb_port: bool = True) -> str | None:
    """Probe one serial port with one baud rate and return the gateway type or None.

    The order of the tests must not be changed:
      * an ESP3 stick answers a base id request only at 57600 baud
      * only the adapter of a FAM14 echoes back what is written to it - the cheapest test
      * a FAM-USB works with 9600 baud only and has to be tested before the FGW14, whose
        test matches every port which does not echo
    """
    import serial

    from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
    from eltakobus.serial import RS485SerialInterfaceV2

    communicator = None
    try:
        # opening the port with pyserial is the cheapest check whether it exists at all
        probe = serial.Serial(device, baudrate=baud_rate, timeout=0.2)
        probe.close()

        if baud_rate == 57600:
            communicator = ESP3SerialCommunicator(device, auto_reconnect=False)
            _start_communicator(communicator)
            if communicator.is_serial_connected.wait(PROBE_CONNECT_TIMEOUT):
                base_id = await communicator.async_base_id
                if base_id and isinstance(base_id, list):
                    return GatewayDeviceType.ESP3.value
            # no ESP3 gateway - the port can still be a FAM14 or an FGW14-USB
            _stop_communicator(communicator)
            communicator = None

        communicator = RS485SerialInterfaceV2(device, baud_rate=baud_rate, delay_message=0.2,
                                              auto_reconnect=False)
        _start_communicator(communicator)
        if not communicator.is_serial_connected.wait(PROBE_CONNECT_TIMEOUT):
            return None

        if communicator.suppress_echo:
            return GatewayDeviceType.GatewayEltakoFAM14.value

        if baud_rate == 9600:
            if not is_usb_port:
                LOGGER.debug(f"[{LOG_PREFIX_PNP}] {device} has no usb descriptor - "
                             f"skipping the FAM-USB test.")
            elif await _async_query_fam_usb_base_id(communicator) not in (None, '00-00-00-00'):
                return GatewayDeviceType.GatewayEltakoFAMUSB.value

        if baud_rate == 57600:
            # reachable, no echo, no ESP3 answer: an FGW14-USB behaves like this - but so does
            # every other serial device. Only a suggestion, see CONFIDENT_GATEWAY_TYPES.
            return GatewayDeviceType.GatewayEltakoFGW14USB.value

        return None
    except Exception as e:  # noqa: BLE001 - a port which is no gateway is the normal case
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] {device} is no gateway with {baud_rate} baud: {e}")
        return None
    finally:
        _stop_communicator(communicator)


async def _async_query_fam_usb_base_id(communicator) -> str | None:
    """A FAM-USB answers a base id request - that is the proof that it is one."""
    from eltakobus.message import ESP2Message
    from eltakobus.util import b2s

    try:
        communicator.set_callback(None)
        response = await communicator.exchange(ESP2Message(bytes(FAM_USB_BASE_ID_REQUEST)),
                                               ESP2Message, retries=PROBE_BASE_ID_RETRIES,
                                               timeout=PROBE_BASE_ID_TIMEOUT)
        return b2s(response.body[2:6])
    except Exception:   # noqa: BLE001 - no answer means: no FAM-USB
        return None


def _start_communicator(communicator) -> None:
    """A port which blocks while being probed must not keep the process alive."""
    communicator.daemon = True
    communicator.start()


def _stop_communicator(communicator) -> None:
    if communicator is None:
        return
    try:
        communicator.stop()
        communicator.join(0.5)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] Cannot stop the probe communicator: {e}")


def probe_ports(ports: list[dict]) -> dict[str, dict]:
    """Probe a list of ports (entries of gateway_scan) -> {device: {device_type, baud_rate}}.

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
                gateway_type = await _async_detect_gateway(device, baud_rate, _is_usb_port(port))
                if gateway_type is None:
                    continue
                detected[device] = {'device_type': gateway_type, 'baud_rate': baud_rate}
                LOGGER.info(f"[{LOG_PREFIX_PNP}] {gateway_type} detected on {device} "
                            f"({baud_rate} baud).")
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


def ports_to_probe(scan: dict, configured_paths: set[str]) -> list[dict]:
    """Ports which may be opened by the probe.

    Three rules, all of them protecting something which is already working:

    * a port which one of our gateways uses is never touched - opening it would interrupt its
      reception. `scan['ports']` marks the ports of the *running* gateways, `configured_paths`
      additionally covers gateways which are configured but not set up yet.
    * a port whose usb descriptor is known but does not fit any Eltako/EnOcean gateway is
      skipped. Home Assistant installations usually carry more sticks (Zigbee, Z-Wave, ...)
      and those belong to another integration.
    * a port without any usb descriptor is probed: inside a container only the device nodes
      are passed through, so the descriptor of a FAM14 is simply not readable there.

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
        if _has_usb_descriptor(port) and not port.get('suggested_device_types'):
            LOGGER.debug(f"[{LOG_PREFIX_PNP}] {port.get('device')} "
                         f"({port.get('name')}) is no known gateway descriptor - not probed.")
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


def describe_candidate(device: str, detection: dict, port: dict = None) -> dict:
    """One gateway detected on a serial port, ready for the report and for creating it."""
    device_type = detection['device_type']
    hw_type, description = _label_of(device_type)
    return {
        'connection': 'serial',
        'serial_path': device,
        'device_type': device_type,
        'baud_rate': detection.get('baud_rate'),
        'hw_type': hw_type,
        'description': description,
        'port_name': (port or {}).get('name'),
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


async def async_run(hass: HomeAssistant, rescan_bus: bool = False,
                    add_devices: bool = True) -> dict:
    """One complete plug & play pass. Returns the report.

    rescan_bus reads the bus of every bus gateway again, also of those which were scanned
    before. Without it only a bus which was never scanned is read - locking the bus for
    minutes must not happen behind the back of the user over and over again.
    """
    from ..observation import bus_members
    from ..config import device_config
    from .. import simulation
    from .gateway_scan import scan as scan_ports
    from ..core.websocket import get_gateways

    state = get_state(hass)
    if state.get('running'):
        LOGGER.debug(f"[{LOG_PREFIX_PNP}] A detection is already running - skipped.")
        return dict(state.get('last_report') or {}, skipped='already_running')

    state.update({'running': True, 'started_at': _utc_now_iso(), 'stage': STAGE_PORTS,
                  'step': "Scanning serial ports"})
    report = {
        'started_at': state['started_at'], 'finished_at': None, 'rescan_bus': bool(rescan_bus),
        'gateways_detected': [], 'gateways_added': [], 'gateways_suggested': [],
        'buses_read': [], 'devices_added': [], 'devices_skipped': [], 'warnings': [],
    }
    # published while it is still being filled: the web ui polls the status every few seconds
    # and shows the stages of a running detection filling up (`finished_at` tells them apart)
    state['last_report'] = report

    try:
        ### 1) which gateway is plugged in or announces itself on the network?
        scan = await hass.async_add_executor_job(scan_ports, hass)
        candidates = []
        probe_list = ports_to_probe(scan, configured_serial_paths(hass))
        if probe_list:
            _set_step(hass, STAGE_PORTS, f"Probing {len(probe_list)} free serial port(s)")
            detected = await async_probe_ports(hass, probe_list)
            ports_by_device = {str(port.get('device')): port for port in probe_list}
            candidates.extend(describe_candidate(device, detection, ports_by_device.get(device))
                              for device, detection in detected.items())
        report['ports_probed'] = len(probe_list)

        _set_step(hass, STAGE_PORTS, "Listening for LAN gateways which announce themselves (mDNS)")
        lan_candidates = await async_discover_mdns_gateways(hass)
        candidates.extend(lan_candidates)
        report['mdns_found'] = len(lan_candidates)

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

        ### 3) read the bus of the bus gateways
        gateways = get_gateways(hass)
        for gateway in gateways:
            if not GatewayDeviceType.is_bus_gateway(gateway.dev_type):
                continue
            if getattr(gateway, 'is_simulated', False):
                # a simulated bus has no device memory to read; its devices are known anyway
                # (they are taken over as candidates in the next step)
                continue
            gateway_id = gateway.dev_id
            if not rescan_bus and _bus_was_read(hass, bus_members, gateway_id):
                continue
            _set_step(hass, STAGE_BUS, f"Reading the bus of gateway {gateway_id} "
                                       f"(this can take a few minutes)")
            read = await _async_read_bus(hass, bus_members, gateway)
            report['buses_read'].append(read)
            if read.get('finished'):
                scanned = state.setdefault('scanned_gateways', [])
                if gateway_id not in scanned:
                    scanned.append(gateway_id)
            else:
                report['warnings'].append(f"The bus scan of gateway {gateway_id} did not finish "
                                          f"within {BUS_SCAN_TIMEOUT} s.")

        ### 4) add every device which is identified without any doubt
        _set_step(hass, STAGE_DEVICES, "Collecting the devices which can be identified")
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
        report['devices_skipped'] = merged['skipped']

        if add_devices:
            added, warnings = await _async_add_devices(hass, device_config, merged['candidates'])
            report['devices_added'] = added
            report['warnings'].extend(warnings)
        else:
            report['devices_pending'] = merged['candidates']

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
        state.update({'running': False, 'step': None, 'stage': None,
                      'last_run': _utc_now_iso(), 'last_report': report})


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


async def _async_read_bus(hass: HomeAssistant, bus_members, gateway) -> dict:
    """Discovery plus complete memory of every device of one bus. Blocks the bus while running."""
    registry = bus_members.get_registry(hass)
    positions = sorted({member['bus_address']
                        for member in (registry.get_members(hass) if registry else [])
                        if member['gateway_id'] == gateway.dev_id})
    if not positions:
        positions = list(range(1, 65))      # a fresh bus was not polled yet

    try:
        if gateway._reading_memory_of_devices_is_running.is_set():
            return {'gateway_id': gateway.dev_id, 'finished': False, 'reason': 'already_running'}
    except Exception:   # noqa: BLE001
        pass

    bus_members.start_bus_scan_thread(hass, gateway, positions)

    finished = False
    for _ in range(BUS_SCAN_TIMEOUT):
        await asyncio.sleep(1)
        if not gateway._reading_memory_of_devices_is_running.is_set():
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
    domain_data[WS_PNP_REGISTERED] = True


def get_status(hass: HomeAssistant) -> dict:
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
