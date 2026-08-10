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
* decoded with the configured EEP of the device, or with the profile a 4BS teach-in
  telegram revealed if the device is not configured,
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
from functools import partial
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

from ..const import (CONF_AREA, CONF_BASE_ID, CONF_COOLING_MODE, CONF_EEP, CONF_GATEWAY,
                     CONF_GERNERAL_SETTINGS, CONF_GRAFANA_URL, CONF_LOG_ENOCEAN_TELEGRAMS,
                     CONF_LOG_LEVEL_BUS_MESSAGES, CONF_LOG_LEVEL_DECODE_ERRORS, CONF_LOG_LEVEL_INCOMING,
                     CONF_LOG_LEVEL_OUTGOING, CONF_LOG_LEVEL_POLLING, CONF_LOG_LEVEL_UNKNOWN_DEVICES,
                     CONF_ROOM_THERMOSTAT, CONF_SENDER, CONF_SENSOR, CONF_TELEGRAM_LOG_BACKUP_COUNT,
                     CONF_TELEGRAM_LOG_BUFFER_SIZE, CONF_TELEGRAM_LOG_DECODE_EEP, CONF_TELEGRAM_LOG_FILENAME,
                     CONF_TELEGRAM_LOG_FORMAT, CONF_TELEGRAM_LOG_INCLUDE_POLLING,
                     CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB, CONF_TELEGRAM_LOG_ROTATE_DAYS,
                     CONF_TIMESERIES_ENABLED, DATA_ELTAKO, DATA_TELEGRAM_LOGGER, DOMAIN, ELTAKO_CONFIG,
                     LOGGER, SERVICE_CLEAR_TELEGRAM_LOG, SERVICE_EXPORT_TELEGRAM_LOG, TELEGRAM_LOGGER_NAME,
                     TelegramDirection, TelegramLogFormat, TelegramLogLevel, WS_GRAFANA_SYNC,
                     WS_RADIO_COMPARISON, WS_RADIO_COMPARISON_CLEAR,
                     WS_TELEGRAM_LOG_CLEAR, WS_TELEGRAM_LOG_INFO, WS_TELEGRAM_LOG_RECENT,
                     WS_TELEGRAM_LOG_REFRESH_DEVICES, WS_TELEGRAM_LOG_STATISTICS,
                     WS_TELEGRAM_LOG_SUBSCRIBE, WS_TELEGRAM_LOG_SUGGESTIONS)

from .radio_comparison import (DEFAULT_WINDOW_MS as RADIO_DEFAULT_WINDOW_MS,
                               MAX_WINDOW_MS as RADIO_MAX_WINDOW_MS,
                               MIN_WINDOW_MS as RADIO_MIN_WINDOW_MS)

if TYPE_CHECKING:
    from ..core.gateway import EnOceanGateway


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
    'rssi_dbm',
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
        self.last_status: str | None = None
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
        self.last_status = record.get('status')
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
            'last_status': self.last_status,
            'last_decoded': self.last_decoded,
            'min_interval': None if self.min_interval is None else round(self.min_interval, 3),
            'max_interval': None if self.max_interval is None else round(self.max_interval, 3),
            'avg_interval': None if self.avg_interval is None else round(self.avg_interval, 3),
        }


class TelegramFileWriter(threading.Thread):
    """Writes telegrams into a rotating file. Runs in its own thread so that neither
    the Home Assistant event loop nor the serial bus thread is blocked by disk i/o.

    The file rotates when it grows beyond `max_bytes` **or** when its oldest telegram is
    older than `max_age_seconds` - whichever happens first. The time based rotation keeps
    the files aligned with a time range (default one week), so "last week" is simply the
    previous backup file, independent of how busy the bus was.
    """

    _SENTINEL = object()

    def __init__(self, path: str, log_format: str, max_bytes: int, backup_count: int,
                 max_age_seconds: float = 0):
        super().__init__(name="eltako_telegram_log_writer", daemon=True)
        self.path = path
        self.log_format = log_format
        self.max_bytes = max_bytes
        self.max_age_seconds = max_age_seconds
        self.backup_count = backup_count
        self.written_count = 0
        self.dropped_count = 0
        self.last_error: str | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=FILE_QUEUE_SIZE)
        self._file = None
        self._size = 0
        # unix timestamp of the oldest record in the current file - survives a restart
        # because it is read back from the file itself (see _read_oldest_timestamp)
        self.oldest_record_at: float | None = None

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
        if not is_new_file:
            # continue an existing file: its age is defined by its oldest record, not by
            # the restart - otherwise the time based rotation would reset on every restart
            self.oldest_record_at = self._read_oldest_timestamp()
        self._file = open(self.path, 'a', encoding='utf-8', newline='')
        self._size = os.path.getsize(self.path)
        if is_new_file:
            self._write_header()

    def _read_oldest_timestamp(self) -> float | None:
        """Timestamp of the first record in the existing file (jsonl and csv both carry it)."""
        try:
            with open(self.path, encoding='utf-8') as file:
                first = file.readline().strip()
                if self.log_format == TelegramLogFormat.CSV.value and first.startswith('seq;'):
                    first = file.readline().strip()     # skip the header
                if not first:
                    return None
                if self.log_format == TelegramLogFormat.CSV.value:
                    timestamp = first.split(';')[CSV_COLUMNS.index('timestamp')]
                else:
                    timestamp = json.loads(first).get('timestamp')
                return datetime.fromisoformat(str(timestamp)).timestamp()
        except Exception:   # noqa: BLE001 - an unreadable first line must not break the writer
            return None

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
        if self.oldest_record_at is None:
            self.oldest_record_at = time.time()

    def _rotate_if_needed(self, next_size: int) -> None:
        too_big = self.max_bytes > 0 and self._size + next_size > self.max_bytes
        too_old = (self.max_age_seconds > 0 and self.oldest_record_at is not None
                   and time.time() - self.oldest_record_at > self.max_age_seconds)
        if not too_big and not too_old:
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
        self.oldest_record_at = None        # set again by the first record of the new file
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

        # optional export into a timeseries database (InfluxDB, see timeseries.py)
        from .timeseries import create_exporter_from_settings
        self._timeseries = create_exporter_from_settings(general_settings)

        # one radio telegram as every gateway received it (radio_comparison.py). Always on:
        # recording into it is only an append to a ring buffer, and the differences it looks
        # for are rare - a comparison which starts when somebody opens the page would never
        # see them. The analysis itself happens when the web ui asks for it, which is what
        # makes its time window and its filters adjustable.
        from .radio_comparison import RadioComparison
        self.radio_comparison = RadioComparison()

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

        # address -> EEP revealed by a 4BS teach-in telegram. Lets the values of devices
        # which are not (yet) configured be decoded as well.
        self._teach_in_profiles: dict[str, str] = {}

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
                max_age_seconds=float(self.general_settings.get(CONF_TELEGRAM_LOG_ROTATE_DAYS, 7)) * 86400,
            )
            self._writer.start()
            LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Write EnOcean telegrams as {self.log_format} into '{self.file_path}'.")
        else:
            LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] EnOcean telegram recording enabled "
                        f"(in memory only, no filename configured in '{CONF_TELEGRAM_LOG_FILENAME}').")

        if self._timeseries is not None:
            self._timeseries.start()
            LOGGER.info(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Export EnOcean telegrams to "
                        f"'{self._timeseries.url}' (bucket '{self._timeseries.bucket}').")

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

        if self._timeseries:
            self._timeseries.stop()
            self._timeseries.join(15)
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Timeseries exporter stopped "
                         f"({self._timeseries.exported_count} telegrams exported).")
            self._timeseries = None

    ### recording

    def record_message(self, gateway: "EnOceanGateway", msg: ESP2Message, direction: str) -> None:
        """Record one telegram. Can be called from any thread (e.g. the serial bus thread)."""
        try:
            if isinstance(msg, POLLING_MESSAGE_TYPES):
                # polling is logged without building a whole record, it can be very frequent
                self._log_polling(gateway, msg)
                if not self.include_polling:
                    self._filtered_count += 1
                    return

            record = self._create_record(gateway, msg, direction)

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

            if self._timeseries:
                self._timeseries.submit(record)

            self._compare_radio_reception(record)
            self._log_record(record)
            self._notify_subscribers_threadsafe(record)

        except Exception as e:  # noqa: BLE001 - logging must never break the bus
            self._error_count += 1
            LOGGER.error(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot record telegram: {e}", exc_info=True)

    def _compare_radio_reception(self, record: dict) -> None:
        """Hand the telegram to the per gateway comparison (radio_comparison.py).

        Its own try/except: an analysis which is only read by one page of the web ui must
        never cost a telegram in the live view or in the log file.
        """
        try:
            self.radio_comparison.add(record)
        except Exception as e:  # noqa: BLE001
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot compare the reception of a "
                         f"telegram: {e}")

    # The bus member registry is fed by the gateway (see bus_members.note_telegram), not from
    # here: recording telegrams is off by default, and the channel layout of multi channel
    # devices must be collected on a default installation as well.

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
            # microseconds, not milliseconds: telegram bursts (repeaters, a command repeated
            # through several gateways) happen well within one millisecond, and the timeseries
            # export needs distinct timestamps - see timeseries.record_to_line_protocol.
            'timestamp': now.isoformat(timespec='microseconds'),
            'timestamp_ms': int(now.timestamp() * 1000),
            'direction': direction,
            'gateway_id': getattr(gateway, 'dev_id', None),
            'gateway_name': getattr(gateway, 'dev_name', None),
            'gateway_type': _json_safe(getattr(gateway, 'dev_type', None)),
            # a telegram of a gateway without hardware: it was produced by the simulation
            # (see simulation/) and not received from a real device. The live view marks it, and
            # the flag ends up in the log file and in the timeseries export as well - otherwise a
            # recording made while testing could not be told apart from a real one afterwards.
            'simulated': bool(getattr(gateway, 'is_simulated', False)),
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

        # signal strength of radio telegrams (only ESP3 transceivers report it, the
        # value is attached to the converted message - see gateway._attach_rssi_to_esp2_conversion).
        # Read from the original msg: prettify() above creates a new object without it.
        rssi = getattr(msg, 'dBm', None)
        if isinstance(rssi, (int, float)) and rssi < 0:
            record['rssi_dbm'] = int(rssi)

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
                if address:
                    self._teach_in_profiles[address] = record['teach_in_profile']
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

        # decode the telegram whenever an EEP is available for its address
        if self.decode_eep:
            eep_string, eep_source = self._eep_for_decoding(record, device_info)
            if eep_string:
                record['decoded'] = self._decode(telegram, eep_string, count_errors=eep_source == 'device')
                record['decoded_eep'] = eep_string
                record['decoded_source'] = eep_source
                # A configured EEP which cannot decode the telegram is a real configuration
                # error (wrong EEP for that device) - marked per telegram so it can be found
                # in the log file and grouped in Grafana. A profile guessed from a teach-in
                # telegram is only a best guess and therefore no error.
                if record['decoded'] is None and eep_source == 'device':
                    record['decode_error'] = True

        return record

    def _eep_for_decoding(self, record: dict, device_info: dict | None) -> tuple[str | None, str | None]:
        """EEP used to decode a telegram and where it comes from.

        The configured EEP of a known device always wins. For devices which are not part of
        the configuration the profile of an earlier 4BS teach-in telegram is used so that the
        live view shows their values as well. A teach-in telegram itself carries the profile
        instead of sensor data and is therefore never decoded.
        """
        if record.get('teach_in_profile'):
            return None, None
        if device_info is not None and device_info.get('eep'):
            return device_info['eep'], 'device'
        profile = self._teach_in_profiles.get(record.get('address'))
        return (profile, 'teach_in') if profile else (None, None)

    def _decode(self, telegram: ESP2Message, eep_string: str, count_errors: bool = True) -> dict | None:
        try:
            eep_class = EEP.find(eep_string)
        except Exception:   # noqa: BLE001
            return None
        try:
            return decoded_eep_to_dict(eep_class.decode_message(telegram))
        except Exception:   # noqa: BLE001 - e.g. WrongOrgError for status telegrams
            # only a configured EEP which does not fit is an error worth counting, a profile
            # taken from a teach-in telegram is just a best guess
            if count_errors:
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
        """Build address -> device information from the configuration of every gateway.

        Both sources count: `configuration.yaml` and the web ui. Reading only the yaml left the
        **sender** addresses of devices created in the web ui unknown - and a sender is what
        Home Assistant transmits with, so its own commands came back as telegrams of an
        unconfigured device and were offered as "newly discovered" ones.
        """
        device_map: dict[str, dict] = {}
        config = self._get_config()

        for gateway_config in config.get(CONF_GATEWAY, []) or []:
            gateway_id = gateway_config.get(CONF_ID)
            base_id = self._get_gateway_base_id(gateway_id, gateway_config.get(CONF_BASE_ID))

            for platform, devices in (self._devices_of_gateway(gateway_config) or {}).items():
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

    def _devices_of_gateway(self, gateway_config: dict) -> dict:
        """Devices of one gateway from `configuration.yaml` AND from the web ui."""
        yaml_devices = gateway_config.get(CONF_DEVICES, {}) or {}
        try:
            from ..config.device_config import get_devices_of_gateway

            return get_devices_of_gateway(self.hass, gateway_config.get(CONF_ID)) or yaml_devices
        except Exception as e:  # noqa: BLE001 - without config entries the yaml is all there is
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Web ui devices are not available: {e}")
            return yaml_devices

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
            'file_rotate_after_days': None if self._writer is None or self._writer.max_age_seconds <= 0
                                      else self._writer.max_age_seconds / 86400,
            'file_max_size_mb': None if self._writer is None or self._writer.max_bytes <= 0
                                else self._writer.max_bytes / (1024 * 1024),
            'file_backup_count': None if self._writer is None else self._writer.backup_count,
            'file_oldest_record_at': None if self._writer is None or self._writer.oldest_record_at is None
                                     else datetime.fromtimestamp(self._writer.oldest_record_at,
                                                                 timezone.utc).isoformat(timespec='seconds'),
            'timeseries_enabled': self._timeseries is not None,
            'timeseries': None if self._timeseries is None else self._timeseries.get_status(),
            # the web ui offers a link to the dashboards with it, see pages/telegrams.js
            'grafana_url': str(self.general_settings.get(CONF_GRAFANA_URL, "") or "").rstrip('/'),
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

        # What could this address be? Derived from the telegrams (message type, data bytes,
        # teach-in profile), enriched with the devices of the central catalog and with a ready
        # configuration.yaml snippet. The web ui only renders these fields - all of the logic
        # lives in telegram_suggestions.py so that services and the CLI can reuse it.
        # Only for the unknown ones: a configured device has its EEP already.
        from .telegram_suggestions import enrich_unknown
        for device in unknown_devices:
            enrich_unknown(device)

        # senders which were already found in the memory of a bus actuator are not "unknown"
        # for the ui: they are shown at their bus position, where the key function names the
        # EEP reliably instead of guessing it from the data.
        detected = self._addresses_detected_in_memories()
        unknown_for_ui = [device for device in unknown_devices
                          if str(device['address']).upper() not in detected]

        return {
            'summary': info,
            'devices': devices,
            # ready to render: filtered, sorted by telegram count, enriched
            'unknown_devices': unknown_for_ui,
        }

    def _addresses_detected_in_memories(self) -> set[str]:
        """Taught-in senders which the bus scan already found in a device memory."""
        try:
            from .bus_members import get_registry

            registry = get_registry(self.hass)
            if registry is None:
                return set()
            return {str(sensor.get('sensor_id')).upper()
                    for member in registry.get_members()
                    for sensor in (member.get('taught_in') or [])
                    if sensor.get('sensor_id')}
        except Exception as e:  # noqa: BLE001 - must never break the statistics
            LOGGER.debug(f"[{LOG_PREFIX_TELEGRAM_LOGGER}] Cannot read the bus members: {e}")
            return set()

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
            self._teach_in_profiles.clear()
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
    websocket_api.async_register_command(hass, ws_telegram_log_suggestions)
    websocket_api.async_register_command(hass, ws_telegram_log_subscribe)
    websocket_api.async_register_command(hass, ws_telegram_log_clear)
    websocket_api.async_register_command(hass, ws_telegram_log_refresh_devices)
    websocket_api.async_register_command(hass, ws_radio_comparison)
    websocket_api.async_register_command(hass, ws_radio_comparison_clear)
    websocket_api.async_register_command(hass, ws_grafana_sync)

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
@websocket_api.websocket_command({
    vol.Required('type'): WS_TELEGRAM_LOG_SUGGESTIONS,
    vol.Optional('address'): vol.Any(str, None),
    vol.Optional('data'): vol.Any(str, None),
    vol.Optional('status'): vol.Any(str, None),
    vol.Optional('msg_type'): vol.Any(str, None),
    vol.Optional('teach_in_profile'): vol.Any(str, None),
    vol.Optional('limit', default=6): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
})
@callback
def ws_telegram_log_suggestions(hass: HomeAssistant, connection, msg) -> None:
    """Which profiles fit **this** telegram, and what each of them makes of its data.

    The statistics carry the suggestions of the *last* telegram of an address. This answers
    the same question for the one telegram a user is looking at, so the values shown next to
    each candidate belong to the row in front of them - which is what makes a profile
    recognizable ("22.4 °C, 41 %" against "button B pressed").
    """
    from . import telegram_suggestions

    msg_type = msg.get('msg_type')
    suggestions = telegram_suggestions.suggest(
        msg_types={msg_type: 1} if msg_type else None,
        data=msg.get('data'), status=msg.get('status'), address=msg.get('address'),
        teach_in_profile=msg.get('teach_in_profile'), limit=msg['limit'])
    connection.send_result(msg['id'], {
        'suggestions': suggestions,
        'best': telegram_suggestions.best_candidate(suggestions),
    })


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required('type'): WS_RADIO_COMPARISON,
    vol.Optional('limit', default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=200)),
    # how far apart two receptions may be to count as the same transmission. Adjustable
    # because the answer depends on the installation - see radio_comparison.WINDOW_CHOICES.
    vol.Optional('window_ms'): vol.All(vol.Coerce(int),
                                       vol.Range(min=RADIO_MIN_WINDOW_MS, max=RADIO_MAX_WINDOW_MS)),
    # which telegrams the list shows: 'all', 'disagreeing', 'missing', ... (FILTERS)
    vol.Optional('filter'): vol.Any(str, None),
    # the direct comparison: only these gateways, only this sender
    vol.Optional('gateway_ids'): vol.Any([vol.Any(int, str)], None),
    vol.Optional('address'): vol.Any(str, None),
})
@websocket_api.async_response
async def ws_radio_comparison(hass: HomeAssistant, connection, msg) -> None:
    """One radio telegram as every gateway received it - see radio_comparison.py."""
    connection.send_result(msg['id'], await async_radio_comparison_report(hass, msg))


async def async_radio_comparison_report(hass: HomeAssistant, msg: dict) -> dict:
    """The answer of WS_RADIO_COMPARISON for one request.

    `limit` and `filter` only bound the list of single telegrams; the summary, the per gateway,
    the per address and the head to head numbers describe everything in the buffer which is
    left after `gateway_ids` / `address`.

    Runs in the executor: the whole analysis is computed for this request (which is what makes
    the window adjustable), and grouping a full buffer takes long enough to be felt in the
    event loop. The web ui asks for it when a telegram arrived, not on a timer - see the
    `onTelegram` hook of frontend/pages/radio.js.
    """
    telegram_logger = get_telegram_logger(hass)
    if telegram_logger is None:
        return {'summary': _disabled_response(), 'gateways': [], 'addresses': [], 'pairs': [],
                'bursts': [], 'selected_count': 0}

    return await hass.async_add_executor_job(
        partial(telegram_logger.radio_comparison.get_report,
                window_ms=msg.get('window_ms') or RADIO_DEFAULT_WINDOW_MS,
                limit=msg.get('limit') or 50,
                telegram_filter=msg.get('filter') or 'all',
                gateway_ids=msg.get('gateway_ids'),
                address=msg.get('address')))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_RADIO_COMPARISON_CLEAR})
@callback
def ws_radio_comparison_clear(hass: HomeAssistant, connection, msg) -> None:
    """Start the comparison over. Deliberately separate from the telegram log: clearing the
    live view must not throw away the differences which were collected over hours."""
    telegram_logger = get_telegram_logger(hass)
    if telegram_logger is not None:
        telegram_logger.radio_comparison.clear()
    connection.send_result(msg['id'], {'cleared': telegram_logger is not None})


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

    async def async_service_export_telegram_log(call) -> None:
        """Backfill: submit the full history of the jsonl log files to the timeseries export."""
        from .timeseries import LOG_PREFIX_TIMESERIES, backfill_log_files

        if telegram_logger._timeseries is None:
            LOGGER.warning(f"[{LOG_PREFIX_TIMESERIES}] Backfill requested but the timeseries "
                           f"export is not enabled ('{CONF_TIMESERIES_ENABLED}').")
            return
        if not telegram_logger.file_path:
            LOGGER.warning(f"[{LOG_PREFIX_TIMESERIES}] Backfill requested but no telegram log "
                           f"file is configured ('{CONF_TELEGRAM_LOG_FILENAME}').")
            return
        if telegram_logger.log_format != TelegramLogFormat.JSONL.value:
            LOGGER.warning(f"[{LOG_PREFIX_TIMESERIES}] Backfill only supports the jsonl format "
                           f"(configured: '{telegram_logger.log_format}').")
            return
        await hass.async_add_executor_job(
            backfill_log_files, telegram_logger._timeseries, telegram_logger.file_path)

    hass.services.async_register(DOMAIN, SERVICE_EXPORT_TELEGRAM_LOG, async_service_export_telegram_log)

    return telegram_logger

@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required('type'): WS_GRAFANA_SYNC})
@websocket_api.async_response
async def ws_grafana_sync(hass: HomeAssistant, connection, msg) -> None:
    """Push the dashboards shipped with the integration into the configured Grafana.

    The http requests run in an executor - urllib is blocking and must not stall the event
    loop. Errors are part of the result instead of an exception, so the web ui can show them.
    """
    from ..config import config_helpers
    from ..tools import grafana_sync

    settings = config_helpers.get_general_settings_from_configuration(hass)
    result = await hass.async_add_executor_job(grafana_sync.sync, settings)
    result['available'] = grafana_sync.describe_dashboards()
    connection.send_result(msg['id'], result)
