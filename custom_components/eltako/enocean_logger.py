"""Logging, statistics and live streaming of EnOcean telegrams.

This module is completely self-contained and can be enabled/disabled via the
`general_settings` section of the Home Assistant configuration:

```yaml
eltako:
  general_settings:
    log_enocean_telegrams: True                     # enables recording of all telegrams
    telegram_log_filename: enocean_telegrams.jsonl  # if set, telegrams are additionally persisted
```

Recorded telegrams are
* enriched with all available information about the sending/receiving device
  (EEP, device name, Home Assistant entity ids, area, gateway, ...),
* decoded with the configured EEP if the device is known,
* aggregated into per-device statistics,
* kept in a ring buffer so that the web ui can display a live view,
* and optionally written into a rotating log file (JSON lines or CSV).
"""

from __future__ import annotations

import asyncio
import csv
import logging
import io
import itertools
import json
import os
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

import voluptuous as vol

from eltakobus.eep import EEP
from eltakobus.message import (
    ESP2Message,
    EltakoDiscoveryReply,
    EltakoDiscoveryRequest,
    EltakoMemoryRequest,
    EltakoMemoryResponse,
    EltakoPoll,
    EltakoPollForced,
    EltakoTimeout,
    TeachIn4BSMessage2,
    prettify,
)
from eltakobus.util import AddressExpression, b2s

from homeassistant.components import websocket_api
from homeassistant.const import CONF_DEVICES, CONF_NAME, CONF_ID, EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import DATA_ENTITY_PLATFORM

from .const import *

if TYPE_CHECKING:
    from .gateway import EnOceanGateway


LOG_PREFIX_TELEGRAM_LOGGER = "Telegram Logger"

# Own logger for the telegrams so that its level can be configured independently of the
# integration (logger: logs: eltako.telegrams: debug).
TELEGRAM_LOGGER = logging.getLogger(TELEGRAM_LOGGER_NAME)

LOG_LEVEL_VALUES = {
    TelegramLogLevel.DEBUG.value: logging.DEBUG,
    TelegramLogLevel.INFO.value: logging.INFO,
    TelegramLogLevel.WARNING.value: logging.WARNING,
}

# telegram category -> setting which defines its log level
LOG_LEVEL_SETTINGS = {
    'incoming': CONF_LOG_LEVEL_INCOMING,
    'outgoing': CONF_LOG_LEVEL_OUTGOING,
    'unknown': CONF_LOG_LEVEL_UNKNOWN_DEVICES,
    'bus': CONF_LOG_LEVEL_BUS_MESSAGES,
    'polling': CONF_LOG_LEVEL_POLLING,
    'decode_error': CONF_LOG_LEVEL_DECODE_ERRORS,
}

# message types which are pure bus house keeping and usually not interesting for an analysis
POLLING_MESSAGE_TYPES = (EltakoPoll, EltakoPollForced, EltakoTimeout)

# maximum number of telegrams waiting to be written to disk. If the queue is full
# telegrams are dropped (and counted) instead of blocking the serial bus thread.
FILE_QUEUE_SIZE = 10000

# csv column order. 'decoded' is serialized as json string into one column.
CSV_COLUMNS = [
    'seq', 'timestamp', 'direction', 'gateway_id', 'gateway_name', 'gateway_type', 'protocol',
    'msg_type', 'org', 'address', 'local_address', 'status', 'data', 'raw',
    'known', 'role', 'eep', 'device_name', 'entity_ids', 'platforms', 'area',
    'rp_count', 'repeated', 'teach_in_profile', 'teach_in_manufacturer', 'decoded',
]


def get_telegram_logger(hass: HomeAssistant) -> "EnOceanTelegramLogger | None":
    """Return the telegram logger if it is enabled, otherwise None.

    Kept cheap and defensive because it is called for every single telegram.
    """
    data = getattr(hass, 'data', None)
    if not isinstance(data, dict):
        return None
    return data.get(DATA_ELTAKO, {}).get(DATA_TELEGRAM_LOGGER, None)


def is_telegram_logging_enabled(general_settings: dict) -> bool:
    """Telegram logging is enabled explicitly or implicitly by providing a filename."""
    return bool(general_settings.get(CONF_LOG_ENOCEAN_TELEGRAMS, False)) or \
        len(str(general_settings.get(CONF_TELEGRAM_LOG_FILENAME, "") or "").strip()) > 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    """Convert values of decoded EEPs into something which can be serialized."""
    if value is None:
        return value
    # enums first: GatewayDeviceType and several EEP values are subclasses of str/int
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, AddressExpression):
        return b2s(value)
    if isinstance(value, (bytes, bytearray)):
        return b2s(bytes(value))
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return str(value)


def resolve_addresses(gateway: "EnOceanGateway", telegram: ESP2Message) -> tuple[str | None, str | None]:
    """Return (external address, local bus address) of a telegram.

    Devices connected to a bus gateway use addresses relative to the base id of the gateway.
    The external address is the address other EnOcean devices see.

    Shared by the telegram logger and the device activity tracker so that both use the very
    same address for one telegram.
    """
    raw_address = getattr(telegram, 'address', None)
    if not isinstance(raw_address, (bytes, bytearray)) or len(raw_address) != 4:
        return None, None

    address = AddressExpression((bytes(raw_address), None))
    if address.is_local_address():
        base_id = getattr(gateway, 'base_id', None)
        if base_id is not None and int.from_bytes(base_id[0], 'big') != 0:
            return b2s(address.add(base_id)), b2s(address)
        return b2s(address), b2s(address)

    return b2s(address), None


def decoded_eep_to_dict(decoded: Any) -> dict:
    """Dump all properties of a decoded EEP into a serializable dict."""
    result = {}
    for name in dir(type(decoded)):
        if name.startswith('_'):
            continue
        if not isinstance(getattr(type(decoded), name, None), property):
            continue
        try:
            result[name] = _json_safe(getattr(decoded, name))
        except Exception:   # noqa: BLE001 - a broken property must not break logging
            continue
    return result


class DeviceStatistics:
    """Aggregated telegram statistics of one EnOcean address."""

    def __init__(self, address: str):
        self.address = address
        self.local_address: str | None = None
        self.known: bool = False
        self.role: str | None = None            # device | sender | thermostat | cooling_sensor ...
        self.name: str | None = None
        self.eep: str | None = None
        self.area: str | None = None
        self.entity_ids: list[str] = []
        self.platforms: list[str] = []
        self.gateway_ids: list[int] = []
        self.msg_types: dict[str, int] = {}
        self.count: int = 0
        self.count_incoming: int = 0
        self.count_outgoing: int = 0
        self.teach_in_count: int = 0
        self.teach_in_profile: str | None = None
        self.first_seen: str | None = None
        self.last_seen: str | None = None
        self.last_data: str | None = None
        self.last_decoded: dict | None = None
        self.min_interval: float | None = None
        self.max_interval: float | None = None
        self._last_monotonic: float | None = None
        self._interval_sum: float = 0.0
        self._interval_count: int = 0

    def add(self, record: dict, monotonic: float) -> None:
        self.count += 1
        if record.get('direction') == TelegramDirection.OUTGOING.value:
            self.count_outgoing += 1
        else:
            self.count_incoming += 1

        msg_type = record.get('msg_type', 'unknown')
        self.msg_types[msg_type] = self.msg_types.get(msg_type, 0) + 1

        if record.get('teach_in_profile'):
            self.teach_in_count += 1
            self.teach_in_profile = record['teach_in_profile']

        if self.first_seen is None:
            self.first_seen = record.get('timestamp')
        self.last_seen = record.get('timestamp')
        self.last_data = record.get('data')
        if record.get('decoded'):
            self.last_decoded = record['decoded']
        if record.get('local_address'):
            self.local_address = record['local_address']

        gateway_id = record.get('gateway_id')
        if gateway_id is not None and gateway_id not in self.gateway_ids:
            self.gateway_ids.append(gateway_id)

        # meta data of the (known) device
        self.known = self.known or bool(record.get('known'))
        for attr, key in (('name', 'device_name'), ('eep', 'eep'), ('area', 'area'), ('role', 'role')):
            if record.get(key):
                setattr(self, attr, record[key])
        for entity_id in record.get('entity_ids', []) or []:
            if entity_id not in self.entity_ids:
                self.entity_ids.append(entity_id)
        for platform in record.get('platforms', []) or []:
            if platform not in self.platforms:
                self.platforms.append(platform)

        # interval statistics
        if self._last_monotonic is not None:
            interval = monotonic - self._last_monotonic
            self._interval_sum += interval
            self._interval_count += 1
            if self.min_interval is None or interval < self.min_interval:
                self.min_interval = interval
            if self.max_interval is None or interval > self.max_interval:
                self.max_interval = interval
        self._last_monotonic = monotonic

    @property
    def avg_interval(self) -> float | None:
        if self._interval_count == 0:
            return None
        return self._interval_sum / self._interval_count

    def to_dict(self) -> dict:
        return {
            'address': self.address,
            'local_address': self.local_address,
            'known': self.known,
            'role': self.role,
            'name': self.name,
            'eep': self.eep,
            'area': self.area,
            'entity_ids': self.entity_ids,
            'platforms': self.platforms,
            'gateway_ids': self.gateway_ids,
            'count': self.count,
            'count_incoming': self.count_incoming,
            'count_outgoing': self.count_outgoing,
            'msg_types': self.msg_types,
            'teach_in_count': self.teach_in_count,
            'teach_in_profile': self.teach_in_profile,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'last_data': self.last_data,
            'last_decoded': self.last_decoded,
            'min_interval': None if self.min_interval is None else round(self.min_interval, 3),
            'max_interval': None if self.max_interval is None else round(self.max_interval, 3),
            'avg_interval': None if self.avg_interval is None else round(self.avg_interval, 3),
        }


class TelegramFileWriter(threading.Thread):
    """Writes telegrams into a rotating file. Runs in its own thread so that neither
    the Home Assistant event loop nor the serial bus thread is blocked by disk i/o."""

    _SENTINEL = object()

    def __init__(self, path: str, log_format: str, max_bytes: int, backup_count: int):
        super().__init__(name="eltako_telegram_log_writer", daemon=True)
        self.path = path
        self.log_format = log_format
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.written_count = 0
        self.dropped_count = 0
        self.last_error: str | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=FILE_QUEUE_SIZE)
        self._file = None
        self._size = 0

    ### public api (thread safe)

    def submit(self, record: dict) -> None:
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self.dropped_count += 1

    def stop(self) -> None:
        try:
            self._queue.put_nowait(self._SENTINEL)
        except queue.Full:      # pragma: no cover - drain to be able to stop
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(self._SENTINEL)
            except Exception:   # noqa: BLE001
                pass

    ### thread internals

    def run(self) -> None:
        try:
            self._open()
        except Exception as e:  # noqa: BLE001
            self.last_error = str(e)
            LOGGER.error(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot open telegram log file '{self.path}': {e}")
            return

        while True:
            record = self._queue.get()
            if record is self._SENTINEL:
                break
            try:
                self._write(record)
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
                LOGGER.error(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot write telegram into log file: {e}")

        self._close()

    def _open(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        is_new_file = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        self._file = open(self.path, 'a', encoding='utf-8', newline='')
        self._size = os.path.getsize(self.path)
        if is_new_file:
            self._write_header()

    def _close(self) -> None:
        if self._file:
            try:
                self._file.flush()
                self._file.close()
            except Exception:   # noqa: BLE001
                pass
            self._file = None

    def _write_header(self) -> None:
        if self.log_format == TelegramLogFormat.CSV.value:
            self._file.write(';'.join(CSV_COLUMNS) + '\n')
            self._file.flush()
            self._size = self._file.tell()

    def _serialize(self, record: dict) -> str:
        if self.log_format == TelegramLogFormat.CSV.value:
            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter=';', quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
            row = []
            for column in CSV_COLUMNS:
                value = record.get(column)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, separators=(',', ':')) if value else ''
                elif isinstance(value, bool):
                    value = 'true' if value else 'false'
                row.append('' if value is None else value)
            writer.writerow(row)
            return buffer.getvalue()

        return json.dumps(record, separators=(',', ':'), default=str) + '\n'

    def _write(self, record: dict) -> None:
        if self._file is None:
            return
        line = self._serialize(record)
        self._rotate_if_needed(len(line.encode('utf-8')))
        self._file.write(line)
        self._file.flush()
        self._size += len(line.encode('utf-8'))
        self.written_count += 1

    def _rotate_if_needed(self, next_size: int) -> None:
        if self.max_bytes <= 0 or self._size + next_size <= self.max_bytes:
            return

        self._close()

        if self.backup_count <= 0:
            os.remove(self.path)
        else:
            oldest = f"{self.path}.{self.backup_count}"
            if os.path.exists(oldest):
                os.remove(oldest)
            for index in range(self.backup_count - 1, 0, -1):
                source = f"{self.path}.{index}"
                if os.path.exists(source):
                    os.replace(source, f"{self.path}.{index + 1}")
            os.replace(self.path, f"{self.path}.1")

        LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Rotated telegram log file '{self.path}'.")
        self._file = open(self.path, 'a', encoding='utf-8', newline='')
        self._size = 0
        self._write_header()


class EnOceanTelegramLogger:
    """Records all EnOcean telegrams which are received or sent by any gateway."""

    def __init__(self, hass: HomeAssistant, general_settings: dict):
        self.hass = hass
        self.general_settings = general_settings

        self.include_polling: bool = bool(general_settings.get(CONF_TELEGRAM_LOG_INCLUDE_POLLING, False))
        self.decode_eep: bool = bool(general_settings.get(CONF_TELEGRAM_LOG_DECODE_EEP, True))
        self.log_format: str = str(general_settings.get(CONF_TELEGRAM_LOG_FORMAT, TelegramLogFormat.JSONL.value))
        self.filename: str = str(general_settings.get(CONF_TELEGRAM_LOG_FILENAME, "") or "").strip()
        self.buffer_size: int = int(general_settings.get(CONF_TELEGRAM_LOG_BUFFER_SIZE, 500))

        # log level per telegram category (None = do not log)
        self.log_levels: dict[str, int | None] = {
            category: LOG_LEVEL_VALUES.get(str(general_settings.get(setting, TelegramLogLevel.OFF.value)))
            for category, setting in LOG_LEVEL_SETTINGS.items()
        }
        self._lowest_log_level = min([level for level in self.log_levels.values() if level is not None],
                                     default=None)
        if self._lowest_log_level is not None:
            # make sure the messages are not dropped because the logger inherits a higher level
            TELEGRAM_LOGGER.setLevel(min(TELEGRAM_LOGGER.level or logging.CRITICAL, self._lowest_log_level))

        self.file_path: str | None = None
        self._writer: TelegramFileWriter | None = None

        self._buffer: deque = deque(maxlen=max(self.buffer_size, 1))
        self._statistics: dict[str, DeviceStatistics] = {}
        self._subscribers: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()

        # telegrams are recorded from the serial bus threads of all gateways.
        # itertools.count is atomic and therefore safe to be used without a lock.
        self._sequence_counter = itertools.count(1)
        self._total_count = 0
        self._filtered_count = 0
        self._error_count = 0
        self._decode_error_count = 0
        self._count_by_gateway: dict[int, int] = {}
        self._count_by_msg_type: dict[str, int] = {}
        self._recent_timestamps: deque = deque()       # monotonic timestamps of the last minute
        self._started_at = _utc_now()

        # address -> device information built from configuration and live entities
        self._device_map: dict[str, dict] = {}
        self._device_map_built_at: float = 0.0
        self._unsubscribe_handles: list[Callable[[], None]] = []

    ### setup / teardown

    async def async_setup(self) -> None:
        """Start file writer and register websocket api."""
        if self.filename:
            self.file_path = self.filename if os.path.isabs(self.filename) else self.hass.config.path(self.filename)
            self._writer = TelegramFileWriter(
                path=self.file_path,
                log_format=self.log_format,
                max_bytes=int(float(self.general_settings.get(CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB, 10)) * 1024 * 1024),
                backup_count=int(self.general_settings.get(CONF_TELEGRAM_LOG_BACKUP_COUNT, 3)),
            )
            self._writer.start()
            LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Write EnOcean telegrams as {self.log_format} into '{self.file_path}'.")
        else:
            LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] EnOcean telegram recording enabled "
                        f"(in memory only, no filename configured in '{CONF_TELEGRAM_LOG_FILENAME}').")

        # known devices can only be collected once all platforms have been set up
        self._unsubscribe_handles.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._async_on_hass_started)
        )
        self._unsubscribe_handles.append(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_on_hass_stop)
        )

        register_websocket_commands(self.hass)

    @callback
    def _async_on_hass_started(self, event) -> None:
        self.refresh_device_map()

    @callback
    def _async_on_hass_stop(self, event) -> None:
        self.unload()

    def unload(self) -> None:
        """Stop the file writer and release all listeners."""
        for unsubscribe in self._unsubscribe_handles:
            try:
                unsubscribe()
            except Exception:   # noqa: BLE001
                pass
        self._unsubscribe_handles.clear()
        self._subscribers.clear()

        if self._writer:
            self._writer.stop()
            self._writer.join(5)
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Telegram log file writer stopped "
                         f"({self._writer.written_count} telegrams written).")
            self._writer = None

    ### recording

    def record_message(self, gateway: "EnOceanGateway", msg: ESP2Message, direction: str) -> None:
        """Record one telegram. Can be called from any thread (e.g. the serial bus thread)."""
        try:
            if isinstance(msg, POLLING_MESSAGE_TYPES):
                # The polling telegrams are the list of bus positions the gateway knows, so
                # their information is collected even when they are not recorded.
                self._note_bus_member(gateway, msg)
                # polling is logged without building a whole record, it can be very frequent
                self._log_polling(gateway, msg)
                if not self.include_polling:
                    self._filtered_count += 1
                    return

            record = self._create_record(gateway, msg, direction)
            telegram_for_bus = prettify(msg) if type(msg) is ESP2Message else msg

            monotonic = time.monotonic()
            with self._lock:
                self._total_count += 1
                self._count_by_gateway[record['gateway_id']] = self._count_by_gateway.get(record['gateway_id'], 0) + 1
                self._count_by_msg_type[record['msg_type']] = self._count_by_msg_type.get(record['msg_type'], 0) + 1
                self._recent_timestamps.append(monotonic)
                self._trim_recent_timestamps(monotonic)

                if record['address']:
                    statistics = self._statistics.get(record['address'])
                    if statistics is None:
                        statistics = DeviceStatistics(record['address'])
                        self._statistics[record['address']] = statistics
                    statistics.add(record, monotonic)

                if self.buffer_size > 0:
                    self._buffer.append(record)

            if self._writer:
                self._writer.submit(record)

            self._note_bus_member(gateway, telegram_for_bus, record)
            self._log_record(record)
            self._notify_subscribers_threadsafe(record)

        except Exception as e:  # noqa: BLE001 - logging must never break the bus
            self._error_count += 1
            LOGGER.error(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot record telegram: {e}", exc_info=True)

    ### bus members (see bus_members.py)

    def _note_bus_member(self, gateway: "EnOceanGateway", telegram, record: dict = None) -> None:
        """Feed everything which reveals a bus position into the bus member registry."""
        from .bus_members import get_registry

        registry = get_registry(self.hass)
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
            if record and record.get('local_address'):
                parts = str(record['local_address']).split('-')
                if len(parts) == 4 and parts[:3] == ['00', '00', '00']:
                    registry.note_answer(gateway, int(parts[3], 16), record.get('address'))
        except Exception as e:  # noqa: BLE001 - must never break the recording
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot note bus member: {e}")

    ### logging into the home assistant log

    def _log_polling(self, gateway: "EnOceanGateway", msg: ESP2Message) -> None:
        level = self.log_levels.get('polling')
        if level is None:
            return
        TELEGRAM_LOGGER.log(level, "polling  gw=%s %s", getattr(gateway, 'dev_id', '?'), msg)

    def _category_of(self, record: dict) -> str:
        if record.get('role') == 'bus_message' or record.get('bus_address') is not None:
            return 'bus'
        if record.get('direction') == TelegramDirection.OUTGOING.value:
            return 'outgoing'
        if not record.get('known'):
            return 'unknown'
        return 'incoming'

    def _log_record(self, record: dict) -> None:
        """One log line per telegram, if its category is configured to be logged."""
        if self._lowest_log_level is None:
            return

        level = self.log_levels.get(self._category_of(record))
        if level is not None:
            TELEGRAM_LOGGER.log(level, "%s", self._format_record(record))

        # a known device whose telegram could not be decoded points to a wrong EEP
        decode_level = self.log_levels.get('decode_error')
        if decode_level is not None and record.get('eep') and record.get('decoded') is None \
                and record.get('role') != 'bus_message':
            TELEGRAM_LOGGER.log(decode_level,
                                "decode error: %s (%s) could not be decoded with %s - wrong EEP configured? data=%s",
                                record.get('address'), record.get('device_name') or 'unknown device',
                                record.get('eep'), record.get('data'))

    def _format_record(self, record: dict) -> str:
        direction = 'out' if record.get('direction') == TelegramDirection.OUTGOING.value else 'in '
        parts = [
            f"{direction} gw={record.get('gateway_id')}",
            f"{record.get('msg_type')}",
            f"{record.get('address') or record.get('bus_address')}",
        ]
        if record.get('known'):
            parts.append(f"'{record.get('device_name')}'")
            if record.get('eep'):
                parts.append(record['eep'])
        else:
            parts.append("UNKNOWN device")
        if record.get('data'):
            parts.append(f"data={record['data']}")
        if record.get('decoded'):
            values = ", ".join(f"{key}={value}" for key, value in list(record['decoded'].items())[:4])
            parts.append(f"[{values}]")
        if record.get('entity_ids'):
            parts.append(f"-> {', '.join(record['entity_ids'][:3])}")
        return "  ".join(str(part) for part in parts)

    def _create_record(self, gateway: "EnOceanGateway", msg: ESP2Message, direction: str) -> dict:
        telegram = prettify(msg) if type(msg) is ESP2Message else msg

        address, local_address = self._resolve_addresses(gateway, telegram)
        device_info = self._lookup_device(address, local_address)

        now = _utc_now()

        record = {
            'seq': next(self._sequence_counter),
            'timestamp': now.isoformat(timespec='milliseconds'),
            'timestamp_ms': int(now.timestamp() * 1000),
            'direction': direction,
            'gateway_id': getattr(gateway, 'dev_id', None),
            'gateway_name': getattr(gateway, 'dev_name', None),
            'gateway_type': _json_safe(getattr(gateway, 'dev_type', None)),
            'protocol': getattr(gateway, 'native_protocol', None),
            'msg_type': type(telegram).__name__,
            'address': address,
            'local_address': local_address,
            'known': device_info is not None,
            'role': None if device_info is None else device_info.get('role'),
            'eep': None if device_info is None else device_info.get('eep'),
            'device_name': None if device_info is None else device_info.get('name'),
            'entity_ids': [] if device_info is None else list(device_info.get('entity_ids', [])),
            'platforms': [] if device_info is None else list(device_info.get('platforms', [])),
            'area': None if device_info is None else device_info.get('area'),
        }

        try:
            record['org'] = f"0x{telegram.org:02X}"
        except Exception:   # noqa: BLE001
            record['org'] = None

        if hasattr(telegram, 'status') and isinstance(telegram.status, int):
            record['status'] = f"0x{telegram.status:02X}"
        if hasattr(telegram, 'data') and isinstance(telegram.data, (bytes, bytearray)):
            record['data'] = b2s(bytes(telegram.data))
        if hasattr(telegram, 'payload') and isinstance(telegram.payload, (bytes, bytearray)):
            record['payload'] = b2s(bytes(telegram.payload))
        if hasattr(telegram, 'is_request'):
            record['is_request'] = telegram.is_request
        for attribute in ('rp_count', 't21', 'nu'):
            if hasattr(telegram, attribute):
                try:
                    record[attribute] = _json_safe(getattr(telegram, attribute))
                except Exception:   # noqa: BLE001
                    pass
        if isinstance(record.get('rp_count'), int):
            record['repeated'] = record['rp_count'] > 0

        try:
            record['raw'] = telegram.serialize().hex()
        except Exception:   # noqa: BLE001
            record['raw'] = None

        # teach-in telegrams reveal the EEP of unknown devices
        if isinstance(telegram, TeachIn4BSMessage2):
            try:
                record['teach_in_profile'] = "%02X-%02X-%02X" % telegram.profile
                record['teach_in_manufacturer'] = telegram.manufacturer
            except Exception:   # noqa: BLE001
                pass

        # Bus messages (polling, discovery, memory) are addressed by the position of the actuator
        # on the bus instead of an EnOcean address. They are counted under a synthetic address so
        # that the sum of the per address statistics matches the total number of telegrams.
        if isinstance(getattr(telegram, 'address', None), int):
            record['bus_address'] = telegram.address
            if record['address'] is None:
                record['address'] = f"bus {telegram.address}"
                record['role'] = 'bus_message'

        if isinstance(telegram, (EltakoDiscoveryRequest, EltakoDiscoveryReply, EltakoMemoryRequest, EltakoMemoryResponse)):
            for attribute in ('reported_address', 'reported_size', 'memory_size', 'model', 'is_fam', 'row'):
                if hasattr(telegram, attribute):
                    record[attribute] = _json_safe(getattr(telegram, attribute))

        # decode telegram with the EEP of the known device
        if self.decode_eep and device_info is not None and device_info.get('eep'):
            record['decoded'] = self._decode(telegram, device_info['eep'])

        return record

    def _decode(self, telegram: ESP2Message, eep_string: str) -> dict | None:
        try:
            eep_class = EEP.find(eep_string)
        except Exception:   # noqa: BLE001
            return None
        try:
            return decoded_eep_to_dict(eep_class.decode_message(telegram))
        except Exception:   # noqa: BLE001 - e.g. WrongOrgError for status telegrams
            self._decode_error_count += 1
            return None

    def _resolve_addresses(self, gateway: "EnOceanGateway", telegram: ESP2Message) -> tuple[str | None, str | None]:
        """Delegates to the shared resolver (also used by the device activity tracker)."""
        return resolve_addresses(gateway, telegram)

    ### known devices

    def _lookup_device(self, address: str | None, local_address: str | None) -> dict | None:
        if address is None and local_address is None:
            return None

        device_map = self._device_map
        for key in (address, local_address):
            if key and key in device_map:
                return device_map[key]

        # a device might have been added after the map has been built. Rebuild it at
        # most every 30 seconds so that unknown addresses do not cause a rebuild storm.
        if time.monotonic() - self._device_map_built_at > 30:
            device_map = self.refresh_device_map()
            for key in (address, local_address):
                if key and key in device_map:
                    return device_map[key]

        return None

    def refresh_device_map(self) -> dict[str, dict]:
        """Collect all known addresses from the configuration and from live entities."""
        try:
            device_map = self._collect_devices_from_config()
            self._merge_entity_information(device_map)
            self._device_map = device_map
            self._device_map_built_at = time.monotonic()
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Known addresses for telegram analysis: {len(device_map)}")
        except Exception as e:  # noqa: BLE001
            self._device_map_built_at = time.monotonic()
            LOGGER.warning(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot collect known devices: {e}")
        return self._device_map

    def _get_config(self) -> dict:
        return self.hass.data.get(DATA_ELTAKO, {}).get(ELTAKO_CONFIG, {}) or {}

    def _get_gateway_base_id(self, gateway_id: int, config_base_id: str | None) -> AddressExpression | None:
        """Prefer the base id of the running gateway because transceivers report it at runtime."""
        gateway = self.hass.data.get(DATA_ELTAKO, {}).get(f"gateway_{gateway_id}", None)
        base_id = getattr(gateway, 'base_id', None)
        if base_id is not None and int.from_bytes(base_id[0], 'big') != 0:
            return base_id
        if config_base_id:
            try:
                return AddressExpression.parse(config_base_id)
            except Exception:   # noqa: BLE001
                return None
        return None

    def _collect_devices_from_config(self) -> dict[str, dict]:
        """Build address -> device information from the yaml configuration."""
        device_map: dict[str, dict] = {}
        config = self._get_config()

        for gateway_config in config.get(CONF_GATEWAY, []) or []:
            gateway_id = gateway_config.get(CONF_ID)
            base_id = self._get_gateway_base_id(gateway_id, gateway_config.get(CONF_BASE_ID))

            for platform, devices in (gateway_config.get(CONF_DEVICES, {}) or {}).items():
                for device in devices or []:
                    name = device.get(CONF_NAME) or ""
                    area = device.get(CONF_AREA)
                    self._add_device_to_map(device_map, base_id, gateway_id, platform, device.get(CONF_ID),
                                            device.get(CONF_EEP), name, area, 'device')

                    # senders and additional related devices are visible on the bus as well
                    sender = device.get(CONF_SENDER)
                    if sender:
                        self._add_device_to_map(device_map, base_id, gateway_id, platform, sender.get(CONF_ID),
                                                sender.get(CONF_EEP), f"{name} (sender)".strip(), area, 'sender')

                    thermostat = device.get(CONF_ROOM_THERMOSTAT)
                    if thermostat:
                        self._add_device_to_map(device_map, base_id, gateway_id, platform, thermostat.get(CONF_ID),
                                                thermostat.get(CONF_EEP), f"{name} (thermostat)".strip(), area, 'thermostat')

                    cooling_mode = device.get(CONF_COOLING_MODE) or {}
                    cooling_sensor = cooling_mode.get(CONF_SENSOR)
                    if cooling_sensor:
                        self._add_device_to_map(device_map, base_id, gateway_id, platform, cooling_sensor.get(CONF_ID),
                                                None, f"{name} (cooling mode sensor)".strip(), area, 'cooling_mode_sensor')
                    cooling_sender = cooling_mode.get(CONF_SENDER)
                    if cooling_sender:
                        self._add_device_to_map(device_map, base_id, gateway_id, platform, cooling_sender.get(CONF_ID),
                                                cooling_sender.get(CONF_EEP), f"{name} (cooling mode sender)".strip(),
                                                area, 'cooling_mode_sender')

        return device_map

    def _add_device_to_map(self, device_map: dict[str, dict], base_id: AddressExpression | None, gateway_id: int,
                           platform: str, device_id: str | None, eep: str | None, name: str, area: str | None,
                           role: str) -> None:
        if not device_id:
            return
        try:
            address = AddressExpression.parse(device_id)
        except Exception:   # noqa: BLE001
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot parse configured device id '{device_id}'.")
            return

        keys = [b2s(address)]
        if address.is_local_address() and base_id is not None:
            keys.append(b2s(address.add(base_id)))

        for key in keys:
            entry = device_map.setdefault(key, {
                'address': key,
                'name': name,
                'eep': eep,
                'area': area,
                'role': role,
                'platforms': [],
                'entity_ids': [],
                'gateway_ids': [],
            })
            if not entry.get('name'):
                entry['name'] = name
            if not entry.get('eep') and eep:
                entry['eep'] = eep
            if platform and platform not in entry['platforms']:
                entry['platforms'].append(str(platform))
            if gateway_id is not None and gateway_id not in entry['gateway_ids']:
                entry['gateway_ids'].append(gateway_id)

    def _merge_entity_information(self, device_map: dict[str, dict]) -> None:
        """Add entity ids, names and EEPs of all live Eltako entities."""
        entity_platforms = (self.hass.data.get(DATA_ENTITY_PLATFORM, {}) or {}).get(DOMAIN, [])
        for entity_platform in entity_platforms:
            for entity in list(getattr(entity_platform, 'entities', {}).values()):
                for raw_address in getattr(entity, 'listen_to_addresses', []) or []:
                    try:
                        key = b2s(raw_address)
                    except Exception:   # noqa: BLE001
                        continue

                    entry = device_map.setdefault(key, {
                        'address': key,
                        'name': None,
                        'eep': None,
                        'area': None,
                        'role': 'device',
                        'platforms': [],
                        'entity_ids': [],
                        'gateway_ids': [],
                    })
                    entity_id = getattr(entity, 'entity_id', None)
                    if entity_id and entity_id not in entry['entity_ids']:
                        entry['entity_ids'].append(entity_id)
                    if not entry.get('name'):
                        entry['name'] = getattr(entity, 'dev_name', None)
                    if not entry.get('eep'):
                        eep = getattr(entity, 'dev_eep', None)
                        entry['eep'] = getattr(eep, 'eep_string', None)
                    if not entry.get('area'):
                        entry['area'] = getattr(entity, '_attr_dev_area', None)
                    platform = str(getattr(entity_platform, 'domain', '') or '')
                    if platform and platform not in entry['platforms']:
                        entry['platforms'].append(platform)
                    gateway = getattr(entity, 'gateway', None)
                    gateway_id = getattr(gateway, 'dev_id', None)
                    if gateway_id is not None and gateway_id not in entry['gateway_ids']:
                        entry['gateway_ids'].append(gateway_id)

    ### live view

    def add_subscriber(self, subscriber: Callable[[dict], None]) -> Callable[[], None]:
        """Register a callback which is called (inside the event loop) for every telegram."""
        self._subscribers.append(subscriber)

        def remove_subscriber() -> None:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

        return remove_subscriber

    def _notify_subscribers_threadsafe(self, record: dict) -> None:
        if not self._subscribers:
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is not None and running_loop is self.hass.loop:
            self._notify_subscribers(record)
        else:
            self.hass.loop.call_soon_threadsafe(self._notify_subscribers, record)

    @callback
    def _notify_subscribers(self, record: dict) -> None:
        for subscriber in list(self._subscribers):
            try:
                subscriber(record)
            except Exception as e:  # noqa: BLE001
                LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot forward telegram to subscriber: {e}")

    ### queries used by the web ui

    def _trim_recent_timestamps(self, now: float) -> None:
        while self._recent_timestamps and now - self._recent_timestamps[0] > 60:
            self._recent_timestamps.popleft()

    def get_info(self) -> dict:
        with self._lock:
            self._trim_recent_timestamps(time.monotonic())
            telegrams_per_minute = len(self._recent_timestamps)

        return {
            'enabled': True,
            'started_at': self._started_at.isoformat(timespec='seconds'),
            'file_logging_enabled': self._writer is not None,
            'file_path': self.file_path,
            'file_format': self.log_format,
            'file_written_count': 0 if self._writer is None else self._writer.written_count,
            'file_dropped_count': 0 if self._writer is None else self._writer.dropped_count,
            'file_error': None if self._writer is None else self._writer.last_error,
            'buffer_size': self.buffer_size,
            'buffered_count': len(self._buffer),
            'include_polling': self.include_polling,
            'decode_eep': self.decode_eep,
            'total_count': self._total_count,
            'filtered_count': self._filtered_count,
            'error_count': self._error_count,
            'decode_error_count': self._decode_error_count,
            'telegrams_per_minute': telegrams_per_minute,
            'known_address_count': len(self._device_map),
            'log_levels': {category: logging.getLevelName(level) if level else 'off'
                           for category, level in self.log_levels.items()},
        }

    def get_statistics(self) -> dict:
        with self._lock:
            devices = [s.to_dict() for s in self._statistics.values()]
            count_by_gateway = dict(self._count_by_gateway)
            count_by_msg_type = dict(self._count_by_msg_type)

        devices.sort(key=lambda d: d['count'], reverse=True)
        known_devices = [d for d in devices if d['known']]
        # bus internal messages have no EnOcean address, they are neither a known nor an
        # unknown device and cannot be added to the configuration
        bus_messages = [d for d in devices if d.get('role') == 'bus_message']
        unknown_devices = [d for d in devices if not d['known'] and d.get('role') != 'bus_message']

        info = self.get_info()
        info.update({
            'device_count': len(devices),
            'known_device_count': len(known_devices),
            'unknown_device_count': len(unknown_devices),
            'bus_message_count': len(bus_messages),
            'count_by_gateway': {str(k): v for k, v in count_by_gateway.items()},
            'count_by_msg_type': count_by_msg_type,
        })

        return {
            'summary': info,
            'devices': devices,
        }

    def get_recent_telegrams(self, limit: int = 200) -> list[dict]:
        with self._lock:
            telegrams = list(self._buffer)
        if limit and limit < len(telegrams):
            return telegrams[-limit:]
        return telegrams

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._statistics.clear()
            self._count_by_gateway.clear()
            self._count_by_msg_type.clear()
            self._recent_timestamps.clear()
            self._total_count = 0
            self._filtered_count = 0
            self._error_count = 0
            self._decode_error_count = 0
            self._started_at = _utc_now()
        LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Telegram statistics and buffer cleared.")


### ---------------------------------------------------------------------------
### Websocket api used by the web ui
### ---------------------------------------------------------------------------

WS_COMMANDS_REGISTERED = "telegram_log_ws_registered"


def register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all websocket commands of the telegram logger exactly once."""
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})
    if domain_data.get(WS_COMMANDS_REGISTERED, False):
        return

    websocket_api.async_register_command(hass, ws_telegram_log_info)
    websocket_api.async_register_command(hass, ws_telegram_log_statistics)
    websocket_api.async_register_command(hass, ws_telegram_log_recent)
    websocket_api.async_register_command(hass, ws_telegram_log_subscribe)
    websocket_api.async_register_command(hass, ws_telegram_log_clear)
    websocket_api.async_register_command(hass, ws_telegram_log_refresh_devices)

    domain_data[WS_COMMANDS_REGISTERED] = True
    LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Websocket commands registered.")


def _disabled_response() -> dict:
    return {
        'enabled': False,
        'hint': f"Set '{CONF_LOG_ENOCEAN_TELEGRAMS}: True' (and optionally "
                f"'{CONF_TELEGRAM_LOG_FILENAME}') in the '{CONF_GERNERAL_SETTINGS}' "
                f"section of your configuration.yaml to record EnOcean telegrams.",
    }


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_TELEGRAM_LOG_INFO})
@callback
def ws_telegram_log_info(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    response = _disabled_response() if telegram_logger is None else telegram_logger.get_info()
    connection.send_result(msg['id'], response)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_TELEGRAM_LOG_STATISTICS})
@callback
def ws_telegram_log_statistics(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    if telegram_logger is None:
        connection.send_result(msg['id'], {'summary': _disabled_response(), 'devices': []})
        return
    connection.send_result(msg['id'], telegram_logger.get_statistics())


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_TELEGRAM_LOG_RECENT,
    vol.Optional('limit', default=200): vol.All(vol.Coerce(int), vol.Range(min=1, max=100000)),
})
@callback
def ws_telegram_log_recent(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    telegrams = [] if telegram_logger is None else telegram_logger.get_recent_telegrams(msg['limit'])
    connection.send_result(msg['id'], {'telegrams': telegrams})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_TELEGRAM_LOG_SUBSCRIBE})
@callback
def ws_telegram_log_subscribe(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    if telegram_logger is None:
        connection.send_error(msg['id'], 'not_enabled', _disabled_response()['hint'])
        return

    @callback
    def forward_telegram(record: dict) -> None:
        connection.send_message(websocket_api.event_message(msg['id'], record))

    connection.subscriptions[msg['id']] = telegram_logger.add_subscriber(forward_telegram)
    connection.send_result(msg['id'])


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_TELEGRAM_LOG_CLEAR})
@callback
def ws_telegram_log_clear(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    if telegram_logger is not None:
        telegram_logger.clear()
    connection.send_result(msg['id'], {'cleared': telegram_logger is not None})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_TELEGRAM_LOG_REFRESH_DEVICES})
@callback
def ws_telegram_log_refresh_devices(hass: HomeAssistant, connection, msg) -> None:
    telegram_logger = get_telegram_logger(hass)
    count = 0 if telegram_logger is None else len(telegram_logger.refresh_device_map())
    connection.send_result(msg['id'], {'known_address_count': count})


### ---------------------------------------------------------------------------
### Setup of the module
### ---------------------------------------------------------------------------

async def async_setup_telegram_logger(hass: HomeAssistant, general_settings: dict) -> EnOceanTelegramLogger | None:
    """Create and register the telegram logger if it is enabled in the general settings."""
    domain_data = hass.data.setdefault(DATA_ELTAKO, {})

    # remove a previously created logger (e.g. after a configuration reload)
    existing: EnOceanTelegramLogger = domain_data.pop(DATA_TELEGRAM_LOGGER, None)
    if existing is not None:
        existing.unload()

    if not is_telegram_logging_enabled(general_settings):
        LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] EnOcean telegram logging is disabled.")
        # the websocket api is registered anyway so that the web ui can display a hint
        register_websocket_commands(hass)
        return None

    telegram_logger = EnOceanTelegramLogger(hass, general_settings)
    await telegram_logger.async_setup()
    domain_data[DATA_TELEGRAM_LOGGER] = telegram_logger

    async def async_service_clear_telegram_log(call) -> None:
        telegram_logger.clear()

    hass.services.async_register(DOMAIN, SERVICE_CLEAR_TELEGRAM_LOG, async_service_clear_telegram_log)

    return telegram_logger
