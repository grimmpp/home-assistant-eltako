"""Devices on the RS485 bus, detected passively from the traffic of the gateway.

A FAM14 permanently polls every position of its bus and the actuators answer with their
status. In addition discovery replies contain the model, the size (number of bus positions)
and the memory size of a device. All of that runs over the bus anyway, so the bus can be
mapped completely **without** locking it and without an active scan:

* `EltakoPoll to N`            -> the gateway asks position N
* status answer (00-00-00-NN)  -> position NN exists and works
* `EltakoDiscoveryReply`       -> model, size and memory size of a position

This is the reason why polling telegrams must not be dropped before this aggregation:
they are the list of positions the gateway knows.

An active scan (locking the bus, reading the memory of every device like the EnOcean Device
Manager does) can build on this table later - the model information collected here already
tells which positions to visit.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from eltakobus.error import TimeoutError as BusTimeoutError
from eltakobus.message import EltakoDiscoveryReply, EltakoMemoryResponse
from eltakobus.util import b2s

from ..const import (CONF_EEP, CONF_GATEWAY, CONF_GATEWAY_DESCRIPTION, CONF_SENDER, DATA_BUS_MEMBERS,
                     DATA_ELTAKO, DOMAIN, ELTAKO_CONFIG, GatewayDeviceType, LOGGER, WS_BUS_CANCEL,
                     WS_BUS_DELETE_MEMORY_LINE, WS_BUS_MEMBERS, WS_BUS_PROGRAM_GATEWAY,
                     WS_BUS_READ_MEMORY, WS_BUS_TEACH_IN_SENDERS)
from ..catalog.device_catalog import DEVICE_CATALOG, describe_hw_type

if TYPE_CHECKING:
    from ..core.gateway import EnOceanGateway

LOG_PREFIX_BUS = "Bus Members"

# Reading the memory of every bus device locks the bus for minutes, so the result is
# persisted: after a restart the taught-in senders are known without scanning again.
STORAGE_KEY = f"{DOMAIN}_bus_members"
STORAGE_VERSION = 1

# writes are debounced - a scan produces a memory response per row
SAVE_DELAY_SECONDS = 30

# a memory image which was not confirmed by a discovery reply for this long is dropped
MAX_AGE_DAYS = 365


def _build_model_map() -> dict:
    """(model bytes, size) -> device class name of the eltakobus library."""
    from eltakobus import device as eltako_devices

    by_model_and_size = {}
    by_model = {}
    for name, cls in inspect.getmembers(eltako_devices, inspect.isclass):
        for model in getattr(cls, 'discovery_names', None) or []:
            key = bytes(model)
            size = getattr(cls, 'size', None)
            if size is not None:
                by_model_and_size.setdefault((key, size), []).append(name)
            by_model.setdefault(key, []).append(name)
    return {'by_model_and_size': by_model_and_size, 'by_model': by_model}


MODEL_MAP = _build_model_map()

# Device knowledge per hardware type from the central device catalog (device_catalog.py,
# ported from the EEP_MAPPING of the EnOcean Device Manager). The key matches the BusObject
# class name of the eltakobus library. The PCT14 fields describe where the Home Assistant
# sender id has to be entered when teaching in the actuator.
HW_TYPE_INFO = {entry['hw_type']: describe_hw_type(entry['hw_type'])
                for entry in DEVICE_CATALOG if entry.get('bus_device')}


def describe_model(model: bytes | None, size: int | None) -> tuple[str | None, str | None]:
    """Return (device class name, remaining candidates) for a model of a discovery reply.

    Classes which share their model bytes differ in their size (FSR14_1x/FSR14_4x report 1
    and 4 addresses, FHK14/F4HK14 2 and 4) - a hit by (model, size) is therefore **exact**
    and returns no candidate list. This matters downstream: `plug_and_play` refuses to add a
    device whose model stays ambiguous, and an FSR14_4x which was identified beyond doubt
    must not be held back only because its model bytes have siblings.
    """
    if not model:
        return None, None
    key = bytes(model)[:2]

    exact = MODEL_MAP['by_model_and_size'].get((key, size)) or []
    if len(exact) == 1:
        return exact[0], None
    # several classes with the same size (none today - a future library addition) fall back
    # to the honest answer: a best guess plus the list a human has to pick from
    candidates = exact or MODEL_MAP['by_model'].get(key, [])
    if candidates:
        return candidates[0], ", ".join(candidates) if len(candidates) > 1 else None
    return None, None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class BusMemberRegistry:
    """Bus positions per gateway, collected from the traffic."""

    def __init__(self, hass: HomeAssistant = None):
        self.hass = hass
        # gateway id -> bus address -> information
        self._members: dict[int, dict[int, dict]] = {}
        # raw data collected during a memory scan (not part of the json members)
        self._replies: dict[tuple[int, int], object] = {}         # discovery reply objects
        self._memory: dict[tuple[int, int], dict[int, bytes]] = {}  # memory rows per device
        self._last_discovery: dict[int, int] = {}                 # gateway -> last discovered position

        # (model, memory size) of the device a memory image belongs to. Survives a restart,
        # so a restored image can be validated against the next discovery reply - the reply
        # objects themselves are not serializable.
        self._signatures: dict[tuple[int, int], tuple] = {}
        # gateways whose bus was read automatically once (plug_and_play.async_auto_scan_bus).
        # Persisted, because that scan locks the bus for minutes - repeating it on every
        # restart is exactly what must not happen, not even when it did not succeed.
        self._auto_scanned: set[int] = set()
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY) if hass is not None else None
        self._unsubscribe = None

    ### the one automatic bus scan per gateway

    def was_auto_scanned(self, gateway_id: int) -> bool:
        """True if the bus of this gateway was already read automatically once."""
        return int(gateway_id) in self._auto_scanned

    def mark_auto_scanned(self, gateway_id: int) -> None:
        """Remember the attempt before it starts, so a restart never repeats it."""
        self._auto_scanned.add(int(gateway_id))
        self._schedule_save()

    def note_memory_write(self, gateway_id: int, bus_address: int, line: int,
                          value: bytes) -> None:
        """Follow a memory line which was just written on the bus.

        Without it the stored image - and with it everything the pages show about taught-in
        senders - would keep the old content until somebody reads the whole bus again, which
        takes minutes.
        """
        rows = self._memory.setdefault((int(gateway_id), int(bus_address)), {})
        rows[int(line)] = bytes(value)
        entry = self._members.get(int(gateway_id), {}).get(int(bus_address))
        if entry is not None:
            entry['taught_in_dirty'] = True
        self._schedule_save()

    def _entry(self, gateway_id: int, bus_address: int) -> dict:
        members = self._members.setdefault(gateway_id, {})
        return members.setdefault(bus_address, {
            'gateway_id': gateway_id,
            'bus_address': bus_address,
            'polled_count': 0,
            'answer_count': 0,
            'first_seen': _utc_now_iso(),
            'last_seen': None,
            'model': None,
            'device_class': None,
            'model_candidates': None,
            'size': None,
            'memory_size': None,
            'is_fam': None,
            'external_address': None,
        })

    ### persistence

    @staticmethod
    def _storage_id(gateway_id: int, bus_address: int) -> str:
        return f"{gateway_id}:{bus_address}"

    async def async_load(self) -> None:
        """Restore the memory images of the last scan.

        Only the result of a memory scan is restored - the passively collected counters
        (polling, answers) describe the current session and are deliberately not persisted.
        """
        if self._store is None:
            return

        try:
            stored = await self._store.async_load()
        except Exception as e:  # noqa: BLE001 - a broken store must not prevent the setup
            LOGGER.warning(f"[{LOG_PREFIX_BUS}] Cannot load persisted memory images: {e}")
            stored = None

        for gateway_id in ((stored or {}).get('auto_scanned') or []):
            try:
                self._auto_scanned.add(int(gateway_id))
            except (TypeError, ValueError):
                continue

        devices = (stored or {}).get('devices')
        if isinstance(devices, dict):
            threshold = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
            restored = 0
            for storage_id, device in devices.items():
                if not isinstance(device, dict):
                    continue
                try:
                    gateway_id, bus_address = (int(part) for part in str(storage_id).split(':', 1))
                except ValueError:
                    continue

                scanned_at = device.get('scanned_at')
                try:
                    if scanned_at and datetime.fromisoformat(scanned_at) < threshold:
                        continue
                except ValueError:
                    pass

                entry = self._entry(gateway_id, bus_address)
                entry['model'] = device.get('model')
                entry['device_class'] = device.get('device_class')
                entry['model_candidates'] = device.get('model_candidates')
                entry['size'] = device.get('size')
                entry['memory_size'] = device.get('memory_size')
                entry['is_fam'] = device.get('is_fam')
                entry['taught_in'] = device.get('taught_in') or []
                entry['taught_in_dirty'] = False
                entry['scanned_at'] = scanned_at
                # the position was restored, not seen in this session
                entry['last_seen'] = None
                entry['first_seen'] = device.get('first_seen') or entry['first_seen']

                rows = {}
                for line, value in (device.get('memory') or {}).items():
                    try:
                        rows[int(line)] = bytes.fromhex(value)
                    except (TypeError, ValueError):
                        continue
                if rows:
                    self._memory[(gateway_id, bus_address)] = rows
                entry['memory_rows_read'] = len(rows)

                self._signatures[(gateway_id, bus_address)] = (device.get('model'), device.get('memory_size'))
                restored += 1

            LOGGER.debug(f"[{LOG_PREFIX_BUS}] Restored the memory image of {restored} bus position(s).")

        self._unsubscribe = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_on_stop)

    @callback
    def _async_on_stop(self, event) -> None:
        self._schedule_save(delay=0)

    def unload(self) -> None:
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception:   # noqa: BLE001
                pass
            self._unsubscribe = None
        self._schedule_save(delay=0)

    def _schedule_save(self, delay: int = SAVE_DELAY_SECONDS) -> None:
        if self._store is None:
            return
        try:
            self._store.async_delay_save(self._data_to_save, delay)
        except Exception as e:  # noqa: BLE001 - persisting must never break the bus
            LOGGER.debug(f"[{LOG_PREFIX_BUS}] Cannot schedule save of memory images: {e}")

    def _data_to_save(self) -> dict:
        """Only positions with a memory image are worth persisting."""
        devices = {}
        for (gateway_id, bus_address), rows in self._memory.items():
            entry = self._members.get(gateway_id, {}).get(bus_address)
            if entry is None or not rows:
                continue
            devices[self._storage_id(gateway_id, bus_address)] = {
                'model': entry.get('model'),
                'device_class': entry.get('device_class'),
                'model_candidates': entry.get('model_candidates'),
                'size': entry.get('size'),
                'memory_size': entry.get('memory_size'),
                'is_fam': entry.get('is_fam'),
                'first_seen': entry.get('first_seen'),
                'scanned_at': entry.get('scanned_at'),
                'taught_in': entry.get('taught_in') or [],
                'memory': {str(line): value.hex() for line, value in sorted(rows.items())},
            }
        return {'devices': devices, 'auto_scanned': sorted(self._auto_scanned)}

    ### collecting

    def note_polled(self, gateway: "EnOceanGateway", bus_address: int) -> None:
        """The gateway asked this position - so it is part of its bus."""
        entry = self._entry(getattr(gateway, 'dev_id', -1), int(bus_address))
        entry['polled_count'] += 1
        entry['last_polled'] = _utc_now_iso()

    def note_answer(self, gateway: "EnOceanGateway", bus_address: int, external_address: str = None) -> None:
        """A device answered from this position - it exists and works."""
        entry = self._entry(getattr(gateway, 'dev_id', -1), int(bus_address))
        entry['answer_count'] += 1
        entry['last_seen'] = _utc_now_iso()
        if external_address:
            entry['external_address'] = external_address

    def note_discovery_reply(self, gateway: "EnOceanGateway", telegram) -> None:
        """A discovery reply carries model, size and memory size of a position."""
        bus_address = getattr(telegram, 'reported_address', None)
        if not isinstance(bus_address, int):
            return

        entry = self._entry(getattr(gateway, 'dev_id', -1), bus_address)
        model = getattr(telegram, 'model', None)
        size = getattr(telegram, 'reported_size', None)

        entry['last_seen'] = _utc_now_iso()
        entry['size'] = size
        entry['memory_size'] = getattr(telegram, 'memory_size', None)
        entry['is_fam'] = getattr(telegram, 'is_fam', None)

        # The FAM14 re-enumerates the bus periodically, so discovery replies arrive all the
        # time. The memory image collected by a scan therefore only starts fresh when the
        # device behind the position actually changed - otherwise the image of positions
        # 1..n would be wiped again right after the scan by the routine enumeration.
        #
        # The comparison runs against the stored (model, memory size) signature and not
        # against the previous reply object, because the signature is persisted: after a
        # restart the reply objects are gone, and comparing against them would discard the
        # restored memory image on the very first routine enumeration.
        gateway_id = getattr(gateway, 'dev_id', -1)
        signature = (b2s(bytes(model)) if isinstance(model, (bytes, bytearray)) else None,
                     getattr(telegram, 'memory_size', None))
        previous_signature = self._signatures.get((gateway_id, bus_address))
        device_changed = previous_signature is not None and previous_signature != signature

        self._replies[(gateway_id, bus_address)] = telegram
        self._signatures[(gateway_id, bus_address)] = signature
        if device_changed:
            self._memory[(gateway_id, bus_address)] = {}
            entry['memory_rows_read'] = 0
            entry.pop('taught_in', None)
            entry.pop('scanned_at', None)
            entry['taught_in_dirty'] = False
            LOGGER.debug(f"[{LOG_PREFIX_BUS}] Position {bus_address} of gateway {gateway_id} changed "
                         f"({previous_signature} -> {signature}), memory image discarded.")
            self._schedule_save()
        self._last_discovery[gateway_id] = bus_address
        if isinstance(model, (bytes, bytearray)):
            entry['model'] = b2s(bytes(model))
            device_class, candidates = describe_model(bytes(model), size)
            entry['device_class'] = device_class
            entry['model_candidates'] = candidates

        LOGGER.debug(f"[{LOG_PREFIX_BUS}] Bus position {bus_address} of gateway "
                     f"{getattr(gateway, 'dev_id', '?')}: {entry.get('device_class') or entry.get('model')}")

    def note_memory_response(self, gateway: "EnOceanGateway", telegram) -> None:
        """Collect a memory row read during a scan.

        A memory response does not carry the address of its device. During the scan of the
        library (request_memory_of_all_devices) the rows of a device always follow its
        discovery reply, so they are attributed to the last discovered position - the same
        approach the EnOcean Device Manager uses.
        """
        gateway_id = getattr(gateway, 'dev_id', -1)
        bus_address = self._last_discovery.get(gateway_id)
        if bus_address is None:
            return
        row = getattr(telegram, 'row', None)
        value = getattr(telegram, 'value', None)
        if not isinstance(row, int) or not isinstance(value, (bytes, bytearray)):
            return

        rows = self._memory.setdefault((gateway_id, bus_address), {})
        rows[row] = bytes(value)
        entry = self._entry(gateway_id, bus_address)
        entry['memory_rows_read'] = len(rows)
        entry['taught_in_dirty'] = True

    @staticmethod
    def classify_taught_in_sensor(sensor_id: str, key_function_name: str) -> dict:
        """What kind of sensor hides behind a taught-in id, derived from its key function.

        Follows the classification of the EnOcean Device Manager
        (device.py, get_decentralized_device_by_sensor_info): many Eltako key functions carry
        the EEP of the sensor in their name (e.g. ..._ACCORDING_EEP_A5_10_06_...), push
        buttons use F6-02-01, ids below 0x1500 come from a FTS14EM, and 00-00-B*.. ids are
        the virtual senders of Home Assistant itself.
        """
        key_function_name = str(key_function_name or '')
        try:
            sensor_int = int(str(sensor_id).replace('-', ''), 16)
        except ValueError:
            sensor_int = 0
        is_local = str(sensor_id).upper().startswith('00-00-')

        if (is_local and str(sensor_id).upper().startswith('00-00-B')) \
                or 'FROM_CONTROLLER' in key_function_name:
            return {'role': 'ha_sender'}

        eep_in_name = re.search(r'EEP_([0-9A-Fa-f]{2})_([0-9A-Fa-f]{2})_([0-9A-Fa-f]{2})', key_function_name)
        if eep_in_name:
            eep = '-'.join(part.upper() for part in eep_in_name.groups())
            prefix = key_function_name[:key_function_name.find('_ACCORDING_')]
            name = prefix.replace('_', ' ').lower().title() if '_ACCORDING_' in key_function_name else ''
            return {'role': 'sensor', 'suggested_eep': eep,
                    'suggested_platform': 'sensor', 'suggested_name': name.strip()}

        if 'PUSH_BUTTON' in key_function_name and not is_local:
            return {'role': 'button', 'suggested_eep': 'F6-02-01',
                    'suggested_platform': 'binary_sensor', 'suggested_name': 'Button'}

        if sensor_int and sensor_int < 0x1500:
            return {'role': 'fts14em', 'suggested_eep': 'F6-02-01',
                    'suggested_platform': 'binary_sensor', 'suggested_name': 'FTS14EM input'}

        if 'WEATHER_STATION' in key_function_name:
            return {'role': 'weather_station', 'suggested_eep': 'A5-04-02',
                    'suggested_platform': 'sensor', 'suggested_name': 'Weather station'}

        return {'role': 'unknown'}

    async def async_parse_taught_in(self) -> None:
        """Extract the taught-in sensors from completely read device memories.

        Uses the BusObject classes of the eltakobus library (get_all_sensors). The memory is
        fully cached, so no bus communication happens here.
        """
        from eltakobus.device import KeyFunction, get_bus_object_by_discovery_message

        for (gateway_id, bus_address), rows in list(self._memory.items()):
            entry = self._members.get(gateway_id, {}).get(bus_address)
            reply = self._replies.get((gateway_id, bus_address))
            if entry is None or reply is None or not entry.get('taught_in_dirty'):
                continue
            memory_size = entry.get('memory_size') or 0
            if memory_size == 0 or any(line not in rows for line in range(memory_size)):
                continue        # memory not complete (scan still running)

            try:
                bus_object = get_bus_object_by_discovery_message(reply)
                bus_object.memory = [rows.get(line) for line in range(memory_size)]
                sensors = await bus_object.get_all_sensors()

                taught_in = []
                for sensor in sensors:
                    if int.from_bytes(sensor.sensor_id, 'big') == 0:
                        continue
                    try:
                        function_name = KeyFunction(sensor.key_func).name
                    except ValueError:
                        function_name = str(sensor.key_func)
                    sensor_id = b2s(sensor.sensor_id)
                    taught_in.append({
                        'sensor_id': sensor_id,
                        'function_group': sensor.in_func_group,
                        'key_function': sensor.key_func,
                        'key_function_name': function_name,
                        'channel': sensor.channel,
                        'target_address': b2s(sensor.dev_adr),
                        'memory_line': sensor.memory_line,
                        # what kind of sensor this is and how it would be configured
                        **self.classify_taught_in_sensor(sensor_id, function_name),
                    })
                entry['taught_in'] = taught_in
                entry['taught_in_dirty'] = False
                entry['scanned_at'] = _utc_now_iso()
                LOGGER.debug(f"[{LOG_PREFIX_BUS}] Position {bus_address} of gateway {gateway_id}: "
                             f"{len(taught_in)} taught-in sender(s).")
                # a complete memory image is worth keeping across a restart
                self._schedule_save()
            except Exception as e:  # noqa: BLE001 - a broken memory image must not break the view
                entry['taught_in_dirty'] = False
                LOGGER.warning(f"[{LOG_PREFIX_BUS}] Cannot parse memory of position {bus_address} "
                               f"(gateway {gateway_id}): {e}")

    ### queries

    def get_members(self, hass: HomeAssistant = None) -> list[dict]:
        """All known bus positions, enriched with the configured device of that address."""
        configured = _get_configured_bus_devices(hass) if hass else {}

        ha_devices = _get_ha_device_ids(hass) if hass else {}

        result = []
        for gateway_id, members in self._members.items():
            for bus_address, entry in members.items():
                device = configured.get((gateway_id, bus_address)) or {}
                local_address = f"00-00-00-{bus_address:02X}"
                info = describe_hw_type(entry.get('device_class'))
                result.append({
                    **entry,
                    'local_address': local_address,
                    'configured': bool(device),
                    'configured_name': device.get('name'),
                    'configured_platform': device.get('platform'),
                    'configured_eep': device.get('eep'),
                    # knowledge of the eo_man mapping table
                    'description': info.get('description'),
                    'suggested_eep': info.get('eep'),
                    'suggested_sender_eep': info.get('sender_eep'),
                    'suggested_platform': info.get('platform'),
                    'pct14_function_group': info.get('pct14_function_group'),
                    'pct14_key_function': info.get('pct14_key_function'),
                    # link to the device page in home assistant
                    'ha_device_id': ha_devices.get(local_address) or ha_devices.get(entry.get('external_address')),
                })

        result.sort(key=lambda member: (member['gateway_id'], member['bus_address']))

        # Multi-channel devices occupy several consecutive positions but only the first one
        # answers the discovery (eo_man skips the covered range with `skip_until`). Attribute
        # the follow-up positions to their physical device so a hierarchy can be built.
        parent = None       # (gateway_id, first position, last position)
        for member in result:
            size = member.get('size')
            if member.get('device_class') and isinstance(size, int) and size > 0:
                parent = (member['gateway_id'], member['bus_address'], member['bus_address'] + size - 1)
                member['channel_count'] = size
                member['parent_bus_address'] = None
            elif parent and parent[0] == member['gateway_id'] and parent[1] < member['bus_address'] <= parent[2]:
                member['parent_bus_address'] = parent[1]
            else:
                member['parent_bus_address'] = None
                parent = None

        return result

    def clear(self) -> None:
        """Forget everything, including the persisted memory images."""
        self._members.clear()
        self._replies.clear()
        self._memory.clear()
        self._signatures.clear()
        self._last_discovery.clear()
        self._schedule_save(delay=0)


def _devices_of_gateway(hass: HomeAssistant, gateway_config: dict) -> dict:
    """Devices of one gateway from `configuration.yaml` AND from the web ui.

    Reading only the yaml section would make every device created in the web ui invisible here
    - and that is the configuration of an installation which was never touched by hand.
    """
    from homeassistant.const import CONF_DEVICES, CONF_ID

    yaml_devices = gateway_config.get(CONF_DEVICES, {}) or {}
    try:
        from ..config.device_config import get_devices_of_gateway

        return get_devices_of_gateway(hass, gateway_config.get(CONF_ID)) or yaml_devices
    except Exception as e:  # noqa: BLE001 - without config entries the yaml is all there is
        LOGGER.debug(f"[{LOG_PREFIX_BUS}] Web ui devices are not available: {e}")
        return yaml_devices


def _get_configured_bus_devices(hass: HomeAssistant) -> dict:
    """(gateway id, bus address) -> configured device of that position."""
    from homeassistant.const import CONF_ID, CONF_NAME

    result = {}
    config = (getattr(hass, 'data', None) or {}).get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    for gateway in config.get(CONF_GATEWAY, []) or []:
        gateway_id = gateway.get(CONF_ID)
        for platform, devices in (_devices_of_gateway(hass, gateway) or {}).items():
            for device in devices or []:
                address = str(device.get(CONF_ID, ''))
                parts = address.split('-')
                # only local bus addresses 00-00-00-xx belong to a bus position
                if len(parts) == 4 and parts[0] == '00' and parts[1] == '00' and parts[2] == '00':
                    try:
                        bus_address = int(parts[3], 16)
                    except ValueError:
                        continue
                    result[(gateway_id, bus_address)] = {
                        'name': device.get(CONF_NAME),
                        'platform': str(platform),
                        'eep': device.get(CONF_EEP),
                    }
    return result


def _get_ha_device_ids(hass: HomeAssistant) -> dict[str, str]:
    """EnOcean address -> device id of the Home Assistant device registry.

    Entities register their device with identifiers={(DOMAIN, <address>)}, see device.py.
    """
    try:
        from homeassistant.helpers import device_registry as dr

        result = {}
        for device in dr.async_get(hass).devices.values():
            for domain, identifier in device.identifiers:
                if domain == DOMAIN:
                    result[str(identifier).upper()] = device.id
        return result
    except Exception:   # noqa: BLE001 - registry not available (e.g. in tests)
        return {}


def get_registry(hass: HomeAssistant) -> BusMemberRegistry | None:
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return None
    return data.get(DATA_ELTAKO, {}).get(DATA_BUS_MEMBERS, None)


def setup_registry(hass: HomeAssistant) -> BusMemberRegistry:
    """Create the registry without restoring anything (see async_setup_registry)."""
    registry = BusMemberRegistry(hass)
    hass.data.setdefault(DATA_ELTAKO, {})[DATA_BUS_MEMBERS] = registry
    register_websocket_commands(hass)
    return registry


async def async_setup_registry(hass: HomeAssistant) -> BusMemberRegistry:
    """Create the registry and restore the memory images of the last bus scan."""
    existing = get_registry(hass)
    if existing is not None:
        existing.unload()

    registry = setup_registry(hass)
    await registry.async_load()
    return registry


def note_telegram(hass: HomeAssistant, gateway: "EnOceanGateway", telegram) -> None:
    """Feed everything which reveals a bus position into the registry.

    Called by the gateway for every telegram, deliberately **not** by the telegram logger:
    the channel layout of multi channel devices (e.g. the four positions of an FSR14-4x)
    only comes from the discovery replies of the FAM14, and the web ui needs it to group
    the channels of a physical device. Recording telegrams is off by default, so tying this
    to the logger would leave the hierarchy flat on a default installation.

    Must never raise - it runs in the serial bus thread.
    """
    from .enocean_logger import POLLING_MESSAGE_TYPES, resolve_addresses

    registry = get_registry(hass)
    if registry is None:
        return

    try:
        if isinstance(telegram, POLLING_MESSAGE_TYPES):
            address = getattr(telegram, 'address', None)
            if isinstance(address, int):
                registry.note_polled(gateway, address)
            return

        if isinstance(telegram, EltakoDiscoveryReply):
            registry.note_discovery_reply(gateway, telegram)
            return

        if isinstance(telegram, EltakoMemoryResponse):
            registry.note_memory_response(gateway, telegram)
            return

        # a status answer of a bus device carries its position as local address
        address, local_address = resolve_addresses(gateway, telegram)
        if local_address:
            parts = str(local_address).split('-')
            if len(parts) == 4 and parts[:3] == ['00', '00', '00']:
                registry.note_answer(gateway, int(parts[3], 16), address)
    except Exception as e:  # noqa: BLE001 - must never break the bus
        LOGGER.debug(f"[{LOG_PREFIX_BUS}] Cannot note bus member: {e}")


### ---------------------------------------------------------------------------
### websocket api
### ---------------------------------------------------------------------------

WS_BUS_REGISTERED = "bus_members_ws_registered"


def register_websocket_commands(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    if domain_data.get(WS_BUS_REGISTERED, False):
        return
    websocket_api.async_register_command(hass, ws_bus_members)
    websocket_api.async_register_command(hass, ws_bus_read_memory)
    websocket_api.async_register_command(hass, ws_bus_cancel)
    websocket_api.async_register_command(hass, ws_bus_teach_in_senders)
    websocket_api.async_register_command(hass, ws_bus_program_gateway)
    websocket_api.async_register_command(hass, ws_bus_delete_memory_line)
    domain_data[WS_BUS_REGISTERED] = True


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_BUS_MEMBERS})
@websocket_api.async_response
async def ws_bus_members(hass: HomeAssistant, connection, msg) -> None:
    registry = get_registry(hass)
    members = []
    scans_running = {}
    busy_with = {}
    if registry is not None:
        await registry.async_parse_taught_in()
        members = registry.get_members(hass)

    from ..core.websocket import get_gateways
    programmed = {}
    for gateway in get_gateways(hass):
        try:
            # 'a scan is running' has become 'the bus is busy' - a teach-in and the base id
            # request block the bus just as much, and the page shows the same thing for them
            scans_running[str(gateway.dev_id)] = bool(gateway.is_bus_busy)
            busy_with[str(gateway.dev_id)] = gateway.bus_busy_reason
            if GatewayDeviceType.is_bus_gateway(gateway.dev_type):
                programmed[str(gateway.dev_id)] = programmed_gateways(hass, gateway)
        except Exception:   # noqa: BLE001
            scans_running[str(gateway.dev_id)] = False

    connection.send_result(msg['id'], {
        'members': members,
        'scans_running': scans_running,
        'busy_with': busy_with,
        # how far each running scan is - keyed like scans_running, so the page can put the
        # numbers right next to its "scanning" badge
        'scan_progress': {str(progress['gateway_id']): progress
                          for progress in get_scan_progress()},
        # a write (teach-in / programming another gateway) has its own counters - it takes a
        # discovery and up to one memory write per actuator
        'teach_in_progress': {str(progress['gateway_id']): progress
                              for progress in get_teach_in_progress()},
        # and what is already in the actuators, per gateway: 'can the installation be operated
        # with this one?' See programmed_gateways()
        'programmed': programmed,
        'hint': "Detected from the traffic of the gateway (polling, status answers, discovery "
                "replies) - no bus lock and no active scan needed. Positions without an answer "
                "are polled by the gateway but did not report yet.",
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_BUS_READ_MEMORY,
    vol.Required('gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_bus_read_memory(hass: HomeAssistant, connection, msg) -> None:
    """Actively scan the bus: discovery of every position plus the complete device memories.

    Uses request_memory_of_all_devices of the eltakobus library (the same as the EnOcean
    Device Manager). The bus is locked while the scan runs, so normal reception pauses -
    all results stream through the receive callback and land in the registry.
    """
    from ..core.websocket import get_gateways

    gateway = next((g for g in get_gateways(hass) if g.dev_id == msg['gateway_id']), None)
    if gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    if not GatewayDeviceType.is_bus_gateway(gateway.dev_type):
        connection.send_error(msg['id'], 'not_a_bus_gateway',
                              f"Gateway {gateway.dev_id} ({gateway.dev_type}) has no RS485 bus.")
        return

    if getattr(gateway, 'is_bus_busy', False):
        # a scan, a teach-in or the base id request already has the bus - a second operation
        # would talk over it
        connection.send_result(msg['id'], {'started': False, 'reason': 'already_running',
                                           'busy_with': gateway.bus_busy_reason})
        return

    LOGGER.info(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} started from the web ui.")

    async def scan_with_recovery():
        """Run the scan and make sure reception resumes afterwards.

        Observed on a live installation: the scan of the library can run into a serial write
        timeout which kills the serial thread and leaves the scan thread hanging - reception
        is dead afterwards while the connection still claims to be active. Therefore the scan
        gets a hard timeout, and if no telegram arrives afterwards the config entry of the
        gateway is reloaded, which rebuilds the connection completely (a plain reconnect
        proved to be insufficient in exactly this state).
        """
        # positions known from the polling of the gateway; fall back to 1..64 for a fresh bus
        registry = get_registry(hass)
        positions = sorted({member['bus_address']
                            for member in (registry.get_members(hass) if registry else [])
                            if member['gateway_id'] == gateway.dev_id})
        if not positions:
            positions = list(range(1, 65))

        if not start_bus_scan_thread(hass, gateway, positions):
            LOGGER.info(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} was not started - "
                        f"the bus is busy with '{gateway.bus_busy_reason}'.")
            return

        # wait for the scan thread (runs independently, this only observes it)
        for _ in range(600):
            await asyncio.sleep(1)
            if not gateway.is_bus_busy:
                break
        else:
            LOGGER.warning(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} did not finish "
                           f"within 600 s.")

        try:
            received_before = gateway._received_message_count
            await asyncio.sleep(20)
            if gateway._received_message_count != received_before:
                return      # reception is alive, nothing to recover

            LOGGER.warning(f"[{LOG_PREFIX_BUS}] No telegram received after the bus scan - "
                           f"reloading gateway {gateway.dev_id} to restore the connection.")
            from ..config import config_helpers
            for entry in hass.config_entries.async_entries(DOMAIN):
                try:
                    entry_gateway_id = config_helpers.get_id_from_gateway_name(
                        entry.data[CONF_GATEWAY_DESCRIPTION])
                except Exception:   # noqa: BLE001
                    continue
                if entry_gateway_id == gateway.dev_id:
                    await hass.config_entries.async_reload(entry.entry_id)
                    LOGGER.info(f"[{LOG_PREFIX_BUS}] Gateway {gateway.dev_id} reloaded.")
                    return
        except Exception as e:  # noqa: BLE001
            LOGGER.error(f"[{LOG_PREFIX_BUS}] Recovery after the bus scan failed: {e}")

    hass.async_create_task(scan_with_recovery())
    connection.send_result(msg['id'], {'started': True})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_BUS_CANCEL,
    # without a gateway id every bus is freed - which is what "the bus hangs" needs when it is
    # not even clear which of them is stuck
    vol.Optional('gateway_id'): vol.Any(None, vol.Coerce(int)),
})
@websocket_api.async_response
async def ws_bus_cancel(hass: HomeAssistant, connection, msg) -> None:
    """Cancel the running bus operation and release the bus.

    Deliberately allowed at any time, also when nothing seems to run: a scan whose thread
    hangs in a serial read looks exactly like an idle bus from here, and that is precisely the
    situation in which somebody presses this. It is idempotent - see
    gateway.cancel_bus_operation() for the two steps and why the bus is released even when the
    operation itself cannot be reached anymore.
    """
    from ..core.websocket import get_gateways

    gateway_id = msg.get('gateway_id')
    gateways = [g for g in get_gateways(hass)
                if gateway_id is None or g.dev_id == gateway_id]
    if gateway_id is not None and not gateways:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {gateway_id}")
        return

    results = []
    for gateway in gateways:
        try:
            results.append(gateway.cancel_bus_operation())
        except Exception as e:  # noqa: BLE001 - one gateway must not stop the others
            LOGGER.error(f"[{LOG_PREFIX_BUS}] Cannot cancel the bus operation of gateway "
                         f"{gateway.dev_id}: {e}", exc_info=True)
            results.append({'gateway_id': gateway.dev_id, 'was_busy': None, 'error': str(e),
                            'released': False})

    connection.send_result(msg['id'], {
        'gateways': results,
        # what was really stopped - the web ui says "nothing was running" instead of pretending
        'cancelled': [entry for entry in results if entry.get('was_busy')],
    })


### ---------------------------------------------------------------------------
### teaching in the home assistant sender addresses
### ---------------------------------------------------------------------------

TEACH_IN_TIMEOUT = 20       # seconds per device

### paced bus scan --------------------------------------------------------------------------
# The scan of the eltakobus library (request_memory_of_all_devices) fires its requests
# back to back: its `asyncio.sleep(.02)` calls are missing the await, so no pause ever
# happens. On a real FAM14 that overruns the bus and ends in serial write timeouts which
# kill the connection. Therefore the integration brings its own scan:
#   * it runs in a dedicated thread with its own event loop, so nothing in Home Assistant
#     can delay it and the bus timing stays intact
#   * every exchange is followed by a real pause (SCAN_PAUSE)
#   * it visits the positions which are already known from the polling of the gateway
#     instead of probing all 255 addresses
SCAN_PAUSE = 0.05           # seconds between two bus requests
SCAN_EXCHANGE_TIMEOUT = 10  # seconds per request

# "nobody answered at this position" arrives in three shapes, and one of them is a trap:
# `eltakobus.error.TimeoutError` only shares its *name* with the builtin - it inherits from
# Exception, so `except TimeoutError` does NOT catch it. The library raises it whenever the
# gateway answers with an EltakoTimeout telegram ("the addressed device did not answer"),
# which is a completely normal reply while scanning. Without it in this tuple a single silent
# position ends the whole scan instead of being skipped.
NO_ANSWER = (TimeoutError, asyncio.TimeoutError, BusTimeoutError)

# Progress of the running scans, gateway id -> counters. Written by the scan thread, read by
# whoever reports progress (the plug & play status, the bus members websocket). Single item
# assignments under the GIL, so no lock is needed for a display value. An entry exists
# exactly while its scan runs - `pop` in the finally of `_scan_bus` is the "finished" signal.
SCAN_PROGRESS: dict[int, dict] = {}


# Progress of a running teach-in / programming run, gateway id -> counters. Same idea as
# SCAN_PROGRESS: writing the senders of a full bus takes a while (one discovery and up to one
# memory write per actuator), and without counters a page which says nothing for a minute is
# indistinguishable from one which is stuck.
TEACH_IN_PROGRESS: dict[int, dict] = {}


def get_teach_in_progress(gateway_id: int = None):
    """Progress of one running write (dict or None) or of all of them (list)."""
    if gateway_id is not None:
        return TEACH_IN_PROGRESS.get(gateway_id)
    return list(TEACH_IN_PROGRESS.values())


def describe_teach_in_progress(progress: dict) -> str:
    """One readable line, e.g. 'actuator 3/14 - 00-00-00-05, 2 written'."""
    total = progress.get('total') or 0
    current = min(progress.get('done', 0) + 1, total) if total else '?'
    line = f"actuator {current}/{total or '?'}"
    if progress.get('address'):
        line += f" - {progress['address']}"
    if progress.get('written'):
        line += f", {progress['written']} written"
    return line


def get_scan_progress(gateway_id: int = None):
    """Progress of one running scan (dict or None) or of all of them (list)."""
    if gateway_id is not None:
        return SCAN_PROGRESS.get(gateway_id)
    return list(SCAN_PROGRESS.values())


def describe_scan_progress(progress: dict) -> str:
    """One readable line, e.g. 'position 11/14, memory 23/56'.

    Shown while the scan works on a position, so the count is the position **being read**
    (done + 1) - 'position 0/14' at the very start would read like nothing is happening.
    """
    total = progress.get('positions_total') or 0
    current = min(progress.get('positions_done', 0) + 1, total) if total else '?'
    line = f"position {current}/{total or '?'}"
    if progress.get('memory_rows_total'):
        line += f", memory {progress.get('memory_rows_read', 0)}/{progress['memory_rows_total']}"
    # a scan which broke off and goes on where it stopped says so - otherwise the counters
    # jumping back looks like the scan started over
    if (progress.get('attempt') or 1) > 1:
        line += f" (attempt {progress['attempt']}/{progress.get('attempts', SCAN_ATTEMPTS)})"
    return line


SCAN_ATTEMPTS = 3           # a scan which breaks off is resumed this often
SCAN_RETRY_PAUSE = 3        # seconds before the next attempt - a port which just died needs a moment


async def _scan_bus(gateway, positions: list[int], completed: set = None, attempt: int = 1) -> None:
    from eltakobus import locking
    from eltakobus.message import (EltakoDiscoveryReply, EltakoDiscoveryRequest,
                                   EltakoMemoryRequest, EltakoMemoryResponse)

    bus = gateway._bus
    forward = bus.callback_func
    is_locked = False

    ordered = sorted(positions)
    total = max(len(ordered), 1)
    # the denominator is the position count - the memory rows of the current device refine
    # the fraction of its own position, so the bar does not stall on a device with a large
    # memory and does not jump when a position turns out to be empty
    progress = SCAN_PROGRESS[gateway.dev_id] = {
        'gateway_id': gateway.dev_id, 'positions_total': len(ordered), 'positions_done': 0,
        'position': None, 'memory_rows_read': None, 'memory_rows_total': None, 'percent': 0,
        'started_at': _utc_now_iso(),
        # which try this is - the web ui says "attempt 2 of 3" instead of starting at 0 again
        'attempt': attempt, 'attempts': SCAN_ATTEMPTS,
    }
    # positions which are done. Filled while the scan runs, so a scan which breaks off in the
    # middle can be continued at the position it did not reach - the caller keeps this set.
    if completed is None:
        completed = set()
    try:
        bus.set_callback(None)
        is_locked = (await locking.lock_bus(bus)) == locking.LOCKED

        skip_until = 0
        for index, position in enumerate(ordered):
            if gateway.is_bus_cancelled:
                break
            progress.update({'position': position, 'positions_done': index,
                             'memory_rows_read': None, 'memory_rows_total': None,
                             'percent': int(100 * index / total)})
            if position <= skip_until:
                continue
            # Everything about one position is guarded: a position which does not answer, or
            # whose answer arrives damaged (the serial reader logs a ParseError and drops the
            # frame), must cost that position - not the rest of the bus. Before this, one such
            # position ended the scan and every position behind it stayed unread.
            try:
                reply = await asyncio.wait_for(
                    bus.exchange(EltakoDiscoveryRequest(address=position), EltakoDiscoveryReply, retries=2),
                    timeout=SCAN_EXCHANGE_TIMEOUT)
                await asyncio.sleep(SCAN_PAUSE)

                if reply is not None:
                    forward(reply)      # feeds the registry through the normal receive path
                    skip_until = position + reply.reported_size - 1
                    # the further positions of a multi channel device do not answer a discovery
                    # of their own, so a retry must not visit them again either
                    completed.update(range(position, skip_until + 1))

                for line in range(reply.memory_size if reply is not None else 0):
                    if gateway.is_bus_cancelled:
                        break
                    progress.update({'memory_rows_read': line + 1, 'memory_rows_total': reply.memory_size,
                                     'percent': int(100 * (index + (line + 1) / max(reply.memory_size, 1))
                                                    / total)})
                    try:
                        response = await asyncio.wait_for(
                            bus.exchange(EltakoMemoryRequest(reply.reported_address, line), EltakoMemoryResponse,
                                         retries=2),
                            timeout=SCAN_EXCHANGE_TIMEOUT)
                    except NO_ANSWER:
                        LOGGER.debug(f"[{LOG_PREFIX_BUS}] Gateway {gateway.dev_id}, position "
                                     f"{position}: memory row {line} did not answer.")
                        continue
                    if response is not None:
                        forward(response)
                    await asyncio.sleep(SCAN_PAUSE)
            except NO_ANSWER:
                # the normal answer for a gap in the bus, and what a damaged reply ends up as
                LOGGER.debug(f"[{LOG_PREFIX_BUS}] Gateway {gateway.dev_id}: position {position} "
                             f"did not answer, skipping it.")
            except Exception as e:  # noqa: BLE001 - one position must not end the whole scan
                LOGGER.warning(f"[{LOG_PREFIX_BUS}] Gateway {gateway.dev_id}: position {position} "
                               f"could not be read ({type(e).__name__}: {e}) - skipping it.")
            # visited, whatever came back - a retry starts behind it instead of reading the
            # positions which are already in the registry a second time
            completed.add(position)

        if gateway.is_bus_cancelled:
            # the memories read so far are kept: they are complete per position, and a position
            # which was not visited simply has no memory image (async_parse_taught_in skips it)
            LOGGER.warning(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} was "
                           f"cancelled at position {progress.get('position')}.")
        else:
            LOGGER.info(f"[{LOG_PREFIX_BUS}] Paced bus scan of gateway {gateway.dev_id} finished.")
    finally:
        SCAN_PROGRESS.pop(gateway.dev_id, None)
        if is_locked:
            try:
                await locking.unlock_bus(bus)
            except Exception as e:  # noqa: BLE001
                LOGGER.error(f"[{LOG_PREFIX_BUS}] Cannot unlock the bus: {e}")
        bus.set_callback(forward)


def sender_is_taught_in(hass: HomeAssistant, gateway_id: int, address: str,
                        sender_id: str) -> bool | None:
    """Is this sender in the memory of that bus position? None when it cannot be told.

    Only a device on the RS485 bus has a memory which can be read, and only after a bus scan.
    For a wireless actuator there is no way to ask - it answers no such question, which is why
    a teach-in there is always the manual procedure at the device itself.
    """
    parts = str(address or '').upper().split('-')
    if len(parts) != 4 or parts[:3] != ['00', '00', '00'] or not sender_id:
        return None
    registry = get_registry(hass)
    if registry is None:
        return None

    position = int(parts[3], 16)
    wanted = str(sender_id).upper()
    members = {member['bus_address']: member for member in registry.get_members(hass)
               if member.get('gateway_id') == gateway_id}

    member = members.get(position)
    if member is None:
        return None
    # a multi-channel device (FSR14/4x) occupies four positions but has **one** memory, at its
    # first one - the senders of every channel are in there, marked with their channel
    owner = members.get(member.get('parent_bus_address')) or member
    if not owner.get('memory_rows_read'):
        return None         # the memory of this position was never read
    return any(str(sensor.get('sensor_id', '')).upper() == wanted
               for sensor in (owner.get('taught_in') or []))


def start_bus_scan_thread(hass: HomeAssistant, gateway, positions: list[int]) -> bool:
    """Run the paced scan in its own thread so that the bus timing cannot be disturbed.

    The bus is taken **before** the thread starts, not inside it: otherwise two scans which are
    started in the same moment would both pass the check and then talk over each other. False
    means somebody else has the bus - the caller reports that instead of starting a second one.
    """
    if not gateway.try_acquire_bus("bus scan"):
        return False

    # The bus can be taken away from this scan while it runs (cancel button of the web ui,
    # gateway.cancel_bus_operation). Its own release must not then take the bus from whoever
    # started afterwards, so it names the generation it acquired.
    generation = gateway.bus_generation

    def runner():
        """Read the bus, and pick the scan up where it broke off.

        A scan can end in the middle for reasons which have nothing to do with the position it
        was reading: the serial connection dies, the port throws, the gateway stops answering
        for a moment. Starting from position 1 again would read everything which was already
        read a second time - minutes on a full bus - so the positions which are done are
        remembered and the next attempt only visits the rest.

        Up to SCAN_ATTEMPTS attempts. A cancel is not a failure: it ends the scan for good
        (see gateway.cancel_bus_operation), otherwise the button would not do anything.
        """
        completed: set[int] = set()
        try:
            for attempt in range(1, SCAN_ATTEMPTS + 1):
                remaining = [position for position in positions if position not in completed]
                if not remaining or gateway.is_bus_cancelled:
                    break
                if attempt > 1:
                    LOGGER.warning(
                        f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id}: attempt "
                        f"{attempt} of {SCAN_ATTEMPTS}, continuing at position {min(remaining)} "
                        f"({len(completed)} of {len(positions)} already read).")
                    time.sleep(SCAN_RETRY_PAUSE)
                try:
                    asyncio.run(_scan_bus(gateway, remaining, completed, attempt))
                    break           # finished - a position which stayed silent is not a failure
                except Exception as e:  # noqa: BLE001 - the next attempt is the answer to this
                    LOGGER.error(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} broke "
                                 f"off in attempt {attempt} of {SCAN_ATTEMPTS}: {e}",
                                 exc_info=attempt == SCAN_ATTEMPTS)
            else:
                LOGGER.error(f"[{LOG_PREFIX_BUS}] Bus scan of gateway {gateway.dev_id} did not "
                             f"finish after {SCAN_ATTEMPTS} attempts - "
                             f"{len(completed)} of {len(positions)} positions were read.")
        finally:
            gateway.release_bus(generation)

    import threading
    thread = threading.Thread(target=runner, name=f"eltako-bus-scan-gw{gateway.dev_id}", daemon=True)
    thread.start()
    # a device which is created (by hand or by the detection) while this runs is stored but
    # not loaded - reloading the gateway would close the port under the scan. This carries
    # that reload out when the bus is free again.
    _schedule_reload_flush(hass, gateway)
    return True


def _schedule_reload_flush(hass: HomeAssistant, gateway, timeout: int = 900) -> None:
    """Wait until the bus of this gateway is free and then do the postponed reloads."""
    async def _wait_and_flush() -> None:
        from ..core.integration import async_flush_pending_reloads
        from ..tools.plug_and_play import get_state

        for _ in range(timeout):
            if not gateway.is_bus_busy:
                break
            await asyncio.sleep(1)
        # a detection does this itself when it is completely done - it is very likely still
        # adding the devices of the bus which was just read, and a reload in the middle of
        # that would only rebuild the gateway twice
        if get_state(hass).get('running'):
            return
        await async_flush_pending_reloads(hass)

    try:
        hass.async_create_task(_wait_and_flush())
    except Exception as e:  # noqa: BLE001 - no event loop (cli, tests): nothing was postponed
        LOGGER.debug(f"[{LOG_PREFIX_BUS}] Cannot watch for postponed reloads: {e}")


def sender_id_for_gateway(base_id: str, device_address: str) -> str | None:
    """The sender address another gateway uses for a bus actuator.

    The same rule the EnOcean Device Manager writes into its configurations: the **base id of
    the gateway** carries the address and the **last byte of the actuator address** identifies
    the actuator inside it, so position 4 of a bus (00-00-00-04) becomes FF-C0-02-04 behind a
    gateway with base id FF-C0-02-00.

    That is what makes it possible to move an installation from the FAM14 to a wireless
    gateway: a transceiver only transmits senders out of its own base id range, so those are
    the addresses which have to be in the memory of the actuators - written while the FAM14 is
    still connected, because only it can write anything.

    None when it cannot be formed: without a base id, for a device which is not on the bus, or
    when the offset would leave the range of 128 addresses a base id covers.
    """
    from eltakobus.util import AddressExpression, b2s

    parts = str(device_address or '').upper().split('-')
    if len(parts) != 4 or parts[:3] != ['00', '00', '00']:
        return None
    offset = int(parts[3], 16)
    try:
        base = int.from_bytes(AddressExpression.parse(str(base_id))[0], 'big')
    except Exception:   # noqa: BLE001 - a gateway without a (valid) base id has none to offer
        return None
    if not base or (base & 0xFF) + offset > 0x7F:
        # a base id covers 128 addresses; beyond that the gateway would refuse to transmit
        return None
    return b2s((base + offset).to_bytes(4, 'big'))


def _collect_teach_in_jobs(hass: HomeAssistant, gateway, only_address: str = None) -> list[dict]:
    """(position, sender id, sender eep) of every configured bus actuator of this gateway."""
    from homeassistant.const import CONF_ID

    config = hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}
    devices_config = {}
    for gateway_config in config.get(CONF_GATEWAY, []) or []:
        if gateway_config.get(CONF_ID) == gateway.dev_id:
            # web ui devices count too - otherwise there is nothing to teach in on an
            # installation which was configured without a yaml
            devices_config = _devices_of_gateway(hass, gateway_config)

    jobs = []
    for platform, devices in devices_config.items():
        for device in devices or []:
            address = str(device.get(CONF_ID, ''))
            sender = device.get(CONF_SENDER) or {}
            sender_id = str(sender.get(CONF_ID, '') or '')
            sender_eep = str(sender.get(CONF_EEP, '') or '')
            parts = address.upper().split('-')
            if len(parts) != 4 or parts[:3] != ['00', '00', '00'] or not sender_id or not sender_eep:
                continue
            if only_address and address.upper() != only_address.upper():
                continue
            jobs.append({'address': address.upper(), 'position': int(parts[3], 16),
                         'sender_id': sender_id, 'sender_eep': sender_eep,
                         'name': device.get('name'), 'platform': str(platform)})
    return jobs


async def _async_write_teach_in_jobs(hass: HomeAssistant, gateway, jobs: list[dict],
                                     reason: str) -> list[dict]:
    """Write the sender ids of `jobs` into the memories of the bus devices.

    The bus is locked and the receive callback is disabled while writing - exactly like the
    EnOcean Device Manager does it. One job which cannot be written is reported and does not
    stop the others.
    """
    from eltakobus import locking
    from eltakobus.device import create_busobject
    from eltakobus.eep import EEP
    from eltakobus.util import AddressExpression

    registry = get_registry(hass)
    members = {m['bus_address']: m for m in (registry.get_members(hass) if registry else [])
               if m['gateway_id'] == gateway.dev_id}

    def owner_of(position: int) -> int:
        member = members.get(position)
        if member and member.get('parent_bus_address'):
            return member['parent_bus_address']
        return position

    if not gateway.try_acquire_bus(reason):
        return [{'status': 'busy', 'message': f"The bus is busy with "
                                              f"'{gateway.bus_busy_reason}' - try again when it "
                                              f"has finished."}]
    generation = gateway.bus_generation

    bus = gateway._bus
    results = []
    original_callback = bus.callback_func
    is_locked = False
    progress = TEACH_IN_PROGRESS[gateway.dev_id] = {
        'gateway_id': gateway.dev_id, 'reason': reason, 'total': len(jobs), 'done': 0,
        'address': None, 'sender_id': None, 'written': 0, 'failed': 0, 'percent': 0,
        'started_at': _utc_now_iso(),
    }
    try:
        bus.set_callback(None)
        is_locked = (await locking.lock_bus(bus)) == locking.LOCKED

        bus_objects = {}
        for index, job in enumerate(jobs):
            progress.update({'done': index, 'address': job.get('address'),
                             'sender_id': job.get('sender_id'),
                             'percent': int(100 * index / max(len(jobs), 1))})
            owner = owner_of(job['position'])
            channel = job['position'] - owner
            try:
                if owner not in bus_objects:
                    bus_objects[owner] = await asyncio.wait_for(
                        create_busobject(bus=bus, id=owner), timeout=TEACH_IN_TIMEOUT)
                device = bus_objects[owner]
                if device is None:
                    raise TimeoutError(f"position {owner} did not answer the discovery")

                written = await asyncio.wait_for(
                    device.ensure_programmed(channel, AddressExpression.parse(job['sender_id']),
                                             EEP.find(job['sender_eep'])),
                    timeout=TEACH_IN_TIMEOUT)
                results.append({**job, 'result': 'written' if written else 'already_taught_in'})
                if written:
                    progress['written'] += 1
            except ValueError as e:
                results.append({**job, 'result': 'unsupported', 'message': str(e)})
                progress['failed'] += 1
            except Exception as e:  # noqa: BLE001
                results.append({**job, 'result': 'error', 'message': str(e)})
                progress['failed'] += 1
            progress.update({'done': index + 1,
                             'percent': int(100 * (index + 1) / max(len(jobs), 1))})

        LOGGER.info(f"[{LOG_PREFIX_BUS}] {reason.capitalize()} on gateway {gateway.dev_id}: "
                    + ", ".join(f"{r['address']}={r['result']}" for r in results))
    finally:
        TEACH_IN_PROGRESS.pop(gateway.dev_id, None)
        if is_locked:
            try:
                await locking.unlock_bus(bus)
            except Exception as e:  # noqa: BLE001
                LOGGER.error(f"[{LOG_PREFIX_BUS}] Cannot unlock the bus: {e}")
        bus.set_callback(original_callback)
        # commands which arrived while this was running are sent now
        gateway.release_bus(generation)
        # and a gateway whose reload was postponed while the bus was taken gets it now
        from ..core.integration import async_flush_pending_reloads
        await async_flush_pending_reloads(hass)

    return results


async def async_teach_in_senders(hass: HomeAssistant, gateway, only_address: str = None) -> list[dict]:
    """Verify and teach in the configured Home Assistant sender ids on the bus.

    Follows the standard procedure of the EnOcean Device Manager: for every configured
    actuator its sender id is looked up in the device memory (ensure_programmed of the
    eltakobus library) and written into the first free line if it is missing.
    """
    if gateway.is_bus_busy:
        LOGGER.warning(f"[{LOG_PREFIX_BUS}] Teaching in the senders of gateway {gateway.dev_id} "
                       f"was refused - the bus is busy with '{gateway.bus_busy_reason}'.")
        return [{'status': 'busy', 'message': f"The bus is busy with "
                                              f"'{gateway.bus_busy_reason}' - try again when it "
                                              f"has finished."}]

    jobs = _collect_teach_in_jobs(hass, gateway, only_address)
    if not jobs:
        return []
    return await _async_write_teach_in_jobs(hass, gateway, jobs, "teaching in the senders")


async def async_delete_memory_line(hass: HomeAssistant, gateway, bus_address: int,
                                   memory_line: int, expected_sensor_id: str = None) -> dict:
    """Clear one taught-in sender out of the memory of a bus device.

    The counterpart of the teach-in: a sender which is in an actuator switches it, and an
    address which does not belong there anymore (an old gateway, a sensor which was replaced)
    keeps switching it. Removing it means writing an **empty line** at that position - the same
    thing the PCT14 does.

    `expected_sensor_id` is the safety catch and should always be passed: the line is read
    first and only cleared when it really holds that sender. Without it a page which is a few
    seconds out of date would delete whatever moved into that line meanwhile - and a wrongly
    deleted line is a device which silently stops reacting.
    """
    from eltakobus import locking
    from eltakobus.device import create_busobject
    from eltakobus.util import b2s

    if gateway.is_bus_busy:
        return {'error': 'bus_busy',
                'message': f"The bus is busy with '{gateway.bus_busy_reason}' - try again "
                           f"when it has finished."}
    if not gateway.try_acquire_bus("deleting a memory line"):
        return {'error': 'bus_busy', 'message': f"The bus is busy with "
                                                f"'{gateway.bus_busy_reason}'."}
    generation = gateway.bus_generation

    bus = gateway._bus
    original_callback = bus.callback_func
    is_locked = False
    try:
        bus.set_callback(None)
        is_locked = (await locking.lock_bus(bus)) == locking.LOCKED

        device = await asyncio.wait_for(create_busobject(bus=bus, id=int(bus_address)),
                                        timeout=TEACH_IN_TIMEOUT)
        if device is None:
            return {'error': 'no_answer',
                    'message': f"Position {bus_address} did not answer the discovery."}

        line = await asyncio.wait_for(device.read_mem_line(int(memory_line)),
                                      timeout=TEACH_IN_TIMEOUT)
        current = b2s(bytes(line[:4]))
        if expected_sensor_id and current.upper() != str(expected_sensor_id).upper():
            LOGGER.warning(f"[{LOG_PREFIX_BUS}] Not deleting line {memory_line} of position "
                           f"{bus_address}: it holds {current}, not {expected_sensor_id}.")
            return {'error': 'line_changed',
                    'message': f"Memory line {memory_line} holds {current}, not "
                               f"{expected_sensor_id} - the view was out of date. Read the bus "
                               f"again and try once more."}

        await asyncio.wait_for(device.write_mem_line(int(memory_line), bytes(len(line))),
                               timeout=TEACH_IN_TIMEOUT)
        LOGGER.info(f"[{LOG_PREFIX_BUS}] Gateway {gateway.dev_id}: sender {current} removed "
                    f"from position {bus_address}, memory line {memory_line}.")

        # the stored memory image has to follow, otherwise the page shows the deleted sender
        # until somebody reads the whole bus again
        registry = get_registry(hass)
        if registry is not None:
            registry.note_memory_write(gateway.dev_id, int(bus_address), int(memory_line),
                                       bytes(len(line)))
            await registry.async_parse_taught_in()
        return {'deleted': True, 'sensor_id': current, 'bus_address': int(bus_address),
                'memory_line': int(memory_line)}
    except Exception as e:  # noqa: BLE001 - the answer says what went wrong, the bus is freed
        LOGGER.error(f"[{LOG_PREFIX_BUS}] Cannot delete memory line {memory_line} of position "
                     f"{bus_address}: {e}", exc_info=True)
        return {'error': 'write_failed', 'message': str(e)}
    finally:
        if is_locked:
            try:
                await locking.unlock_bus(bus)
            except Exception as e:  # noqa: BLE001
                LOGGER.error(f"[{LOG_PREFIX_BUS}] Cannot unlock the bus: {e}")
        bus.set_callback(original_callback)
        gateway.release_bus(generation)


def programmed_gateways(hass: HomeAssistant, gateway) -> list[dict]:
    """Whose senders are already in the actuators of this bus - one entry per gateway.

    This is the answer to the question the programming raises: did it work, and can the
    installation be operated with that gateway? It is read out of the memory images of the last
    bus scan, so a position whose memory was never read says **unknown** instead of "no" - the
    difference matters, because "no" would send somebody programming what is long since in
    there.
    """
    from ..const import GatewayDeviceType
    from ..core.websocket import get_gateways
    from eltakobus.util import b2s

    jobs = _collect_teach_in_jobs(hass, gateway)
    if not jobs:
        return []

    summary = []
    for target in get_gateways(hass):
        is_self = target.dev_id == gateway.dev_id
        if not is_self and GatewayDeviceType.is_bus_gateway(target.dev_type):
            continue        # a second bus gateway uses the same local senders as this one
        base_id = None
        if not is_self:
            try:
                base_id = b2s(target.base_id[0]) if target.base_id else None
            except Exception:   # noqa: BLE001
                base_id = None
            if not base_id or not base_id.upper().startswith('FF'):
                continue    # no wireless base id -> no addresses to look for

        programmed = unknown = 0
        for job in jobs:
            sender_id = job['sender_id'] if is_self else sender_id_for_gateway(base_id, job['address'])
            if sender_id is None:
                unknown += 1
                continue
            state = sender_is_taught_in(hass, gateway.dev_id, job['address'], sender_id)
            if state is None:
                unknown += 1
            elif state:
                programmed += 1
        summary.append({
            'gateway_id': target.dev_id, 'name': target.dev_name, 'base_id': base_id,
            'is_this_bus': is_self, 'total': len(jobs),
            'programmed': programmed, 'unknown': unknown,
            'missing': len(jobs) - programmed - unknown,
        })
    return summary


async def async_program_gateway_senders(hass: HomeAssistant, gateway, target_gateway) -> dict:
    """Write the sender addresses of **another** gateway into the actuators of this bus.

    Why this exists: an installation is read and programmed with a FAM14, but it is often
    operated with something else afterwards - an FGW14-USB or a wireless gateway. A wireless
    gateway may only transmit senders out of its own base id range, so the actuators have to
    carry *those* addresses in their memory. Writing them needs a FAM14, so it has to happen
    while it is still connected - which is exactly what this does, for all actuators at once.

    The addresses follow sender_id_for_gateway(): base id of the target gateway plus the last
    byte of the actuator address, the rule the EnOcean Device Manager uses as well.
    """
    from eltakobus.util import b2s

    if gateway.is_bus_busy:
        return {'results': [], 'error': 'bus_busy',
                'message': f"The bus is busy with '{gateway.bus_busy_reason}' - try again "
                           f"when it has finished."}

    base_id = b2s(target_gateway.base_id[0]) if getattr(target_gateway, 'base_id', None) else None
    if not base_id or not str(base_id).upper().startswith('FF'):
        # a gateway which never reported its base id (not connected yet, or a bus gateway,
        # which has no range of its own) has no sender addresses to hand out
        return {'results': [], 'error': 'no_base_id',
                'message': f"Gateway '{target_gateway.dev_name}' has no wireless base id yet - "
                           f"connect it once so that it reports one."}

    jobs = []
    skipped = []
    for job in _collect_teach_in_jobs(hass, gateway):
        sender_id = sender_id_for_gateway(base_id, job['address'])
        if sender_id is None:
            skipped.append({**job, 'result': 'out_of_range'})
            continue
        jobs.append({**job, 'sender_id': sender_id, 'sender_eep': job['sender_eep'],
                     'target_gateway_id': target_gateway.dev_id,
                     'target_gateway_name': target_gateway.dev_name})

    if not jobs:
        return {'results': skipped, 'base_id': base_id,
                'target_gateway_id': target_gateway.dev_id,
                'target_gateway_name': target_gateway.dev_name}

    LOGGER.info(f"[{LOG_PREFIX_BUS}] Programming the senders of gateway "
                f"'{target_gateway.dev_name}' (base id {base_id}) into {len(jobs)} actuator(s) "
                f"of gateway {gateway.dev_id}.")
    results = await _async_write_teach_in_jobs(
        hass, gateway, jobs, f"programming the senders of '{target_gateway.dev_name}'")
    return {'results': results + skipped, 'base_id': base_id,
            'target_gateway_id': target_gateway.dev_id,
            'target_gateway_name': target_gateway.dev_name}


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_BUS_TEACH_IN_SENDERS,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Optional('address'): str,
})
@websocket_api.async_response
async def ws_bus_teach_in_senders(hass: HomeAssistant, connection, msg) -> None:
    from ..core.websocket import get_gateways

    gateway = next((g for g in get_gateways(hass) if g.dev_id == msg['gateway_id']), None)
    if gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    if not GatewayDeviceType.is_bus_gateway(gateway.dev_type):
        connection.send_error(msg['id'], 'not_a_bus_gateway',
                              f"Gateway {gateway.dev_id} ({gateway.dev_type}) has no RS485 bus.")
        return
    if gateway.is_bus_busy:
        connection.send_error(msg['id'], 'bus_busy',
                              f"The bus is busy with '{gateway.bus_busy_reason}' - try again "
                              f"afterwards. Only one operation may talk on the bus at a time.")
        return

    results = await async_teach_in_senders(hass, gateway, msg.get('address'))
    connection.send_result(msg['id'], {'results': results})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_BUS_PROGRAM_GATEWAY,
    # the FAM14 which does the writing, and the gateway whose addresses are written
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('target_gateway_id'): vol.Coerce(int),
})
@websocket_api.async_response
async def ws_bus_program_gateway(hass: HomeAssistant, connection, msg) -> None:
    """Program the sender addresses of another gateway into the actuators of this bus."""
    from ..core.websocket import get_gateways

    gateways = get_gateways(hass)
    gateway = next((g for g in gateways if g.dev_id == msg['gateway_id']), None)
    target = next((g for g in gateways if g.dev_id == msg['target_gateway_id']), None)
    if gateway is None or target is None:
        connection.send_error(msg['id'], 'unknown_gateway',
                              f"No gateway with id {msg['gateway_id']} / {msg['target_gateway_id']}")
        return
    if not GatewayDeviceType.is_bus_gateway(gateway.dev_type):
        connection.send_error(msg['id'], 'not_a_bus_gateway',
                              f"Gateway {gateway.dev_id} ({gateway.dev_type}) has no RS485 bus.")
        return
    if gateway.dev_id == target.dev_id:
        connection.send_error(msg['id'], 'same_gateway',
                              "The senders of this gateway are written by the normal teach-in.")
        return

    answer = await async_program_gateway_senders(hass, gateway, target)
    if answer.get('error'):
        connection.send_error(msg['id'], answer['error'], answer.get('message', ''))
        return
    connection.send_result(msg['id'], answer)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_BUS_DELETE_MEMORY_LINE,
    vol.Required('gateway_id'): vol.Coerce(int),
    vol.Required('bus_address'): vol.Coerce(int),
    vol.Required('memory_line'): vol.Coerce(int),
    # what the page believes is in that line - the write only happens if it is really there
    vol.Optional('sensor_id'): vol.Any(None, str),
})
@websocket_api.async_response
async def ws_bus_delete_memory_line(hass: HomeAssistant, connection, msg) -> None:
    """Remove one taught-in sender from the memory of a bus device."""
    from ..core.websocket import get_gateways

    gateway = next((g for g in get_gateways(hass) if g.dev_id == msg['gateway_id']), None)
    if gateway is None:
        connection.send_error(msg['id'], 'unknown_gateway', f"No gateway with id {msg['gateway_id']}")
        return
    if not GatewayDeviceType.is_bus_gateway(gateway.dev_type):
        connection.send_error(msg['id'], 'not_a_bus_gateway',
                              f"Gateway {gateway.dev_id} ({gateway.dev_type}) has no RS485 bus.")
        return

    answer = await async_delete_memory_line(hass, gateway, msg['bus_address'],
                                            msg['memory_line'], msg.get('sensor_id'))
    if answer.get('error'):
        connection.send_error(msg['id'], answer['error'], answer.get('message', ''))
        return
    connection.send_result(msg['id'], answer)
