"""Export of EnOcean telegrams into a timeseries database (InfluxDB), for Grafana.

Every recorded telegram - including its correlated meta data (device name, EEP, area,
platform, decoded values) - can be written into an InfluxDB bucket. Grafana on top of that
bucket can then analyse the traffic: telegrams per device over months, temperature curves,
button press patterns, calibration drift, test runs.

```yaml
eltako:
  general_settings:
    log_enocean_telegrams: True
    timeseries_enabled: True
    timeseries_url: http://localhost:8086
    timeseries_token: <api token>
    timeseries_org: home
    timeseries_bucket: eltako
```

Works with InfluxDB 2.x (native) and InfluxDB 1.8+ (its v2 compatibility api: bucket is
`database/retention_policy`, token is `username:password`). No client library needed -
the line protocol is plain text over HTTP, sent with urllib from a worker thread.

Data model (line protocol):
    measurement   eltako_telegram (configurable)
    tags          gateway_id, direction, msg_type, address, device_name, eep, area,
                  platform, known, role   - the correlated meta data, all filterable
    fields        count=1i (always - makes counting trivial), status, data, rp_count
                  and every decoded EEP value (temperature=21.5, humidity=44.0, ...)
    time          timestamp of the telegram (ns)

The full history of the rotating telegram log files can be backfilled with the service
`eltako.export_telegram_log_to_timeseries` (jsonl format only).
"""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from enum import Enum

from .const import *

LOG_PREFIX_TIMESERIES = "Timeseries Export"

# telegrams waiting to be exported. If the database is down the queue fills up and
# telegrams are dropped (and counted) instead of blocking or growing without limit.
EXPORT_QUEUE_SIZE = 50000

# a batch is flushed when it reaches this many lines or when the flush interval passes
BATCH_MAX_LINES = 500
BATCH_FLUSH_SECONDS = 5.0

# tags: the correlated meta data. Every entry is (tag name, record key).
TAG_KEYS = [
    ('gateway_id', 'gateway_id'),
    ('direction', 'direction'),
    ('msg_type', 'msg_type'),
    ('address', 'address'),
    ('local_address', 'local_address'),
    ('device_name', 'device_name'),
    ('eep', 'eep'),
    ('area', 'area'),
    ('known', 'known'),
    ('role', 'role'),
    # a configured EEP which cannot decode the telegram - the basis of the error dashboard.
    # Only present on such a telegram, so the tag exists only where it matters.
    ('decode_error', 'decode_error'),
]

# plain record values which become fields (next to the decoded EEP values)
# 'raw' is the complete ESP2 frame - for a test/analysis tool the full bytes matter, and
# 28 hex characters per telegram are affordable
FIELD_KEYS = ['status', 'data', 'raw', 'rp_count', 'rssi_dbm']


def _escape_tag(value) -> str:
    """Escape a tag key/value for the line protocol (comma, equals, space)."""
    return str(value).replace('\\', '\\\\').replace(',', '\\,').replace('=', '\\=').replace(' ', '\\ ')


def _escape_measurement(value: str) -> str:
    return str(value).replace('\\', '\\\\').replace(',', '\\,').replace(' ', '\\ ')


def _field_value(value) -> str | None:
    """Serialize one field value for the line protocol, None if not representable."""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return f"{value}i"
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, str):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    return None


def record_to_line_protocol(record: dict, measurement: str) -> str | None:
    """One telegram record -> one line protocol line. None if the record has no timestamp.

    InfluxDB identifies a point by measurement + tags + timestamp and OVERWRITES an existing
    one. Telegrams are discrete events, not samples: several of them can share the same
    address and message type within one microsecond (repeaters, a command repeated through
    several gateways, a burst test). Their sequence number therefore fills the nanoseconds
    below the microsecond resolution of the record, which keeps every telegram its own point.
    The introduced time error is below one microsecond.
    """
    timestamp = record.get('timestamp')
    if not timestamp:
        return None
    try:
        nanoseconds = int(datetime.fromisoformat(str(timestamp)).timestamp() * 1_000_000_000)
    except ValueError:
        return None

    try:
        nanoseconds += int(record.get('seq') or 0) % 1000
    except (TypeError, ValueError):
        pass

    tags = []
    for tag, key in TAG_KEYS:
        value = record.get(key)
        if value is None or value == '':
            continue
        tags.append(f"{tag}={_escape_tag(value)}")
    # the first entity/platform of the device, so Grafana can group by platform
    platforms = record.get('platforms') or []
    if platforms:
        tags.append(f"platform={_escape_tag(platforms[0])}")

    fields = ['count=1i']
    for key in FIELD_KEYS:
        serialized = _field_value(record.get(key))
        if serialized is not None:
            fields.append(f"{_escape_tag(key)}={serialized}")
    for key, value in (record.get('decoded') or {}).items():
        serialized = _field_value(value)
        if serialized is not None:
            fields.append(f"{_escape_tag(key)}={serialized}")

    head = _escape_measurement(measurement)
    if tags:
        head += ',' + ','.join(tags)
    return f"{head} {','.join(fields)} {nanoseconds}"


class TimeseriesExporter(threading.Thread):
    """Batches telegram records and posts them to InfluxDB as line protocol.

    Runs in its own thread (like the file writer), so neither the Home Assistant event
    loop nor the serial bus thread ever waits for the database.
    """

    _SENTINEL = object()

    def __init__(self, url: str, token: str, org: str, bucket: str,
                 measurement: str = 'eltako_telegram', timeout: float = 10.0):
        super().__init__(name="eltako_timeseries_exporter", daemon=True)
        self.url = url.rstrip('/')
        self.token = token
        self.org = org
        self.bucket = bucket
        self.measurement = measurement
        self.timeout = timeout

        self.exported_count = 0
        self.dropped_count = 0
        self.failed_count = 0
        self.batch_count = 0
        self.last_error: str | None = None
        self.last_export_at: float | None = None

        self._queue: queue.Queue = queue.Queue(maxsize=EXPORT_QUEUE_SIZE)

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

    def get_status(self) -> dict:
        return {
            'url': self.url,
            'bucket': self.bucket,
            'measurement': self.measurement,
            'exported_count': self.exported_count,
            'dropped_count': self.dropped_count,
            'failed_count': self.failed_count,
            'batch_count': self.batch_count,
            'queued_count': self._queue.qsize(),
            'last_error': self.last_error,
            'last_export_at': None if self.last_export_at is None
                              else datetime.fromtimestamp(self.last_export_at,
                                                          timezone.utc).isoformat(timespec='seconds'),
        }

    ### thread internals

    def run(self) -> None:
        batch: list[str] = []
        stop = False
        while not stop:
            try:
                record = self._queue.get(timeout=BATCH_FLUSH_SECONDS)
                if record is self._SENTINEL:
                    stop = True
                else:
                    line = record_to_line_protocol(record, self.measurement)
                    if line:
                        batch.append(line)
            except queue.Empty:
                pass

            if batch and (stop or len(batch) >= BATCH_MAX_LINES or self._queue.empty()):
                self._flush(batch)
                batch = []

    def _flush(self, batch: list[str]) -> None:
        try:
            self._post('\n'.join(batch))
            self.exported_count += len(batch)
            self.batch_count += 1
            self.last_export_at = time.time()
            self.last_error = None
        except Exception as e:  # noqa: BLE001 - the export must never break anything
            self.failed_count += len(batch)
            self.last_error = str(e)
            LOGGER.warning(f"[{LOG_PREFIX_TIMESERIES}] Cannot write {len(batch)} telegram(s) "
                           f"to '{self.url}': {e}")

    def _post(self, body: str) -> None:
        query = urllib.parse.urlencode({'org': self.org, 'bucket': self.bucket, 'precision': 'ns'})
        request = urllib.request.Request(
            f"{self.url}/api/v2/write?{query}",
            data=body.encode('utf-8'),
            headers={
                'Authorization': f"Token {self.token}",
                'Content-Type': 'text/plain; charset=utf-8',
            },
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            # 204 is the expected answer; anything readable else is an error detail
            if response.status >= 300:  # pragma: no cover - urlopen raises on >= 400
                raise RuntimeError(f"HTTP {response.status}")


def create_exporter_from_settings(general_settings: dict) -> TimeseriesExporter | None:
    """Build the exporter if the timeseries export is enabled and configured."""
    if not general_settings.get(CONF_TIMESERIES_ENABLED, False):
        return None
    url = str(general_settings.get(CONF_TIMESERIES_URL, '') or '').strip()
    if not url:
        LOGGER.warning(f"[{LOG_PREFIX_TIMESERIES}] '{CONF_TIMESERIES_ENABLED}' is set but "
                       f"'{CONF_TIMESERIES_URL}' is empty - export stays off.")
        return None
    return TimeseriesExporter(
        url=url,
        token=str(general_settings.get(CONF_TIMESERIES_TOKEN, '') or ''),
        org=str(general_settings.get(CONF_TIMESERIES_ORG, '') or ''),
        bucket=str(general_settings.get(CONF_TIMESERIES_BUCKET, 'eltako') or 'eltako'),
        measurement=str(general_settings.get(CONF_TIMESERIES_MEASUREMENT, 'eltako_telegram')
                        or 'eltako_telegram'),
    )


def backfill_log_files(exporter: TimeseriesExporter, file_path: str) -> dict:
    """Submit the full history of the rotating jsonl log files to the exporter.

    Reads the oldest backup first so the records arrive in chronological order (InfluxDB
    does not require it, but it makes a partial import easier to reason about). Runs
    synchronously - call it from an executor.
    """
    import os

    candidates = [f"{file_path}.{index}" for index in range(100, 0, -1)] + [file_path]
    submitted = 0
    skipped = 0
    files = 0
    for path in candidates:
        if not os.path.exists(path):
            continue
        files += 1
        with open(path, encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    skipped += 1
                    continue
                if record_to_line_protocol(record, exporter.measurement) is None:
                    skipped += 1
                    continue
                exporter.submit(record)
                submitted += 1

    LOGGER.info(f"[{LOG_PREFIX_TIMESERIES}] Backfill: submitted {submitted} telegram(s) "
                f"from {files} file(s), skipped {skipped}.")
    return {'files': files, 'submitted': submitted, 'skipped': skipped}
