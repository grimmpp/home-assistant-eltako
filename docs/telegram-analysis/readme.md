# EnOcean Telegram Logging and Analysis

The integration can record every EnOcean telegram which is received or sent by any configured gateway.
Recorded telegrams are enriched with all information the integration knows about the sender/receiver
(EEP, device name, Home Assistant entity ids, area, gateway) and are decoded with the configured EEP.

This is meant for
* analysing the traffic on your bus / in the air (how often does which device send?),
* finding devices which are **not yet** configured in Home Assistant (see [Unknown devices](#unknown-devices)),
* verifying that telegrams sent by Home Assistant really reach the bus,
* debugging EEP problems by comparing raw payloads with decoded values.

Everything is implemented in the module [`enocean_logger.py`](../../custom_components/eltako/enocean_logger.py).

## Configuration

All options belong to the `general_settings` section of the `eltako` configuration in `/config/configuration.yaml`.
Telegram recording is **disabled by default**.

```yaml
eltako:
  general_settings:
    log_enocean_telegrams: True                     # records all incoming and outgoing telegrams
    telegram_log_filename: enocean_telegrams.jsonl  # if set, telegrams are additionally written into this file
    telegram_log_format: jsonl                      # jsonl (default) or csv
    telegram_log_max_file_size_mb: 10               # rotates the file when the size is exceeded
    telegram_log_rotate_days: 7                     # ... or when its oldest telegram is older than this
    telegram_log_backup_count: 3                    # number of rotated files to keep (file.1 ... file.3)
    telegram_log_include_polling: False             # True: log bus polling telegrams (FAM14) as well
    telegram_log_decode_eep: True                   # decode telegrams of known devices with their EEP
    telegram_log_buffer_size: 500                   # telegrams kept in memory for the live view
```

All of these are on the **Settings** page of the [web ui](../web-ui/readme.md) as well, where they take
effect immediately - the yaml above is only needed if the configuration is kept in files.

| Option | Default | Description |
|---|---|---|
| `log_enocean_telegrams` | `False` | Master switch of the recording. It feeds the statistics and the live view; the web ui itself is there anyway. |
| `telegram_log_filename` | `""` | **If a filename is set, telegrams are logged into that file** – and recording is enabled implicitly. Relative paths are resolved against the Home Assistant configuration folder (`/config`), absolute paths are used as they are. Missing directories are created. |
| `telegram_log_format` | `jsonl` | `jsonl`: one JSON object per line (recommended, e.g. for pandas). `csv`: semicolon separated, spreadsheet friendly. |
| `telegram_log_max_file_size_mb` | `10` | The log file is rotated as soon as it grows beyond this size. |
| `telegram_log_rotate_days` | `7` | The log file is **also** rotated when its oldest telegram is older than this - whichever limit is reached first. The files then align with time ranges: "last week" is simply `<name>.1`, independent of how busy the bus was. The age survives restarts (it is read back from the first record of the file). `0` disables the time based rotation. |
| `telegram_log_backup_count` | `3` | Number of rotated files (`<name>.1` … `<name>.n`) to keep. `0` deletes the old content instead. |
| `telegram_log_include_polling` | `False` | Bus gateways (FAM14) poll their actuators permanently. Those telegrams are dropped by default because they would flood the log. |
| `telegram_log_decode_eep` | `True` | Decodes telegrams of configured devices with their EEP and stores the decoded values (e.g. temperature, humidity, button). |
| `telegram_log_buffer_size` | `500` | Size of the in-memory ring buffer which feeds the live view. `0` disables buffering (file logging and statistics still work). |
| `enable_frontend` | `True` | The `Eltako` panel in the sidebar, which contains the live view and the statistics. On by default, see [Web UI](../web-ui/readme.md). |

> Changed in the web ui these settings take effect immediately (the telegram logger is re-created).
> Changed in `configuration.yaml` they need a restart of Home Assistant.

Writing to the file happens in a separate thread, so neither the Home Assistant event loop nor the
serial communication is slowed down by disk i/o.

## Web UI

The sidebar contains the panel **Eltako** (visible for admins only) without any configuration. Two of its
pages belong to the telegram analysis:

* **Live telegrams** – all telegrams as they arrive, including direction, gateway, address, device name,
  entity ids, EEP, message type, raw data and decoded values. Can be filtered (address, device, EEP,
  entity, data), restricted to one direction or to unknown devices, and paused. A click on a row shows
  the complete raw record. `Export CSV` downloads the filtered view, `Clear` resets statistics and buffer
  (same as the service `eltako.clear_telegram_log`).
* **Device statistics** – one row per EnOcean address: number of telegrams (incoming/outgoing),
  average/minimum/maximum interval between two telegrams, first/last time seen, message types, area,
  platform, entity ids and the last decoded values. Sortable by clicking a column header.
  `Refresh known devices` rebuilds the list of known devices after configuration changes.
Addresses which sent telegrams but are not configured yet are listed as **unknown devices** on the
**Devices** page, including their EEP (from a teach-in telegram or guessed). A click takes such a
candidate over: the device form opens prefilled, no yaml involved.

The remaining pages (**Overview**, **Control**, **Tests**, **Settings**, **Help** and **About**) describe
and configure the integration itself. All pages and the websocket api behind them are documented in
[Web UI](../web-ui/readme.md).

## Unknown devices

Every telegram whose address is neither a configured device, a configured sender, thermostat or
cooling-mode device, nor a live entity of the integration is marked as `unknown`. This is the fastest
way to find devices which are not yet integrated: press a button on the device, look at the *unknown
devices* on the **Devices** page and add it from there with one click.

The EEP shown there is a guess derived from the message type (RPS → `F6-02-01`, 1BS → `D5-00-01`,
4BS → `A5-04-02`). If the device sends a 4BS teach-in telegram, the EEP contained in that telegram is
displayed instead – that one is reliable.

## Log file format

### JSON lines (`jsonl`)

One JSON object per telegram, e.g.:

```json
{"seq":42,"timestamp":"2025-05-19T21:07:11.482+00:00","timestamp_ms":1747688831482,"direction":"incoming",
 "gateway_id":1,"gateway_name":"FGW14-USB - fgw14usb (Id: 1)","gateway_type":"fgw14usb","protocol":"ESP2",
 "msg_type":"EltakoWrapped4BS","address":"FF-AA-DD-81","local_address":null,"known":true,"role":"device",
 "eep":"A5-04-02","device_name":"Temperature and Humidity Sensor - FLGTF55","entity_ids":["sensor.eltako_ff_aa_dd_81_temperature"],
 "platforms":["sensor"],"area":"Living Room","org":"0x07","status":"0x00","data":"00-6E-52-0A",
 "raw":"a55a0b07006e520affaadd8100","decoded":{"humidity":44.0,"temperature":21.3}}
```

Field overview:

| Field | Description |
|---|---|
| `seq`, `timestamp`, `timestamp_ms` | sequence number and time of recording (UTC) |
| `direction` | `incoming` (received from the bus/air) or `outgoing` (sent by Home Assistant onto the bus) |
| `gateway_id`, `gateway_name`, `gateway_type`, `protocol` | gateway which received/sent the telegram |
| `msg_type`, `org`, `status`, `data`, `payload`, `raw` | telegram itself. `raw` is the serialized ESP2 frame as hex string |
| `address` | external EnOcean address (base id of the gateway already added for bus devices) |
| `local_address` | address on the bus (relative to the base id) if the device is a bus device |
| `bus_address` | position on the bus for Eltako bus messages (discovery, memory, ...) |
| `known`, `role` | whether the address is configured and as what (`device`, `sender`, `thermostat`, `cooling_mode_sensor`, `cooling_mode_sender`) |
| `eep`, `device_name`, `entity_ids`, `platforms`, `area` | reference to the configured device and its Home Assistant entities |
| `decoded` | all values of the decoded EEP (only for known devices with `telegram_log_decode_eep: True`) |
| `teach_in_profile`, `teach_in_manufacturer` | EEP and manufacturer id of 4BS teach-in telegrams |
| `rp_count`, `repeated`, `t21`, `nu` | repeater information / RPS flags if available |

### CSV

Semicolon separated with a header line. Lists (`entity_ids`) and objects (`decoded`) are stored as
JSON strings so that no information is lost.

## Analysing the log file

The JSON lines format can be loaded directly, e.g. with pandas:

```python
import pandas as pd

df = pd.read_json('/config/enocean_telegrams.jsonl', lines=True)

# how many telegrams per device?
print(df.groupby(['address', 'device_name', 'eep']).size().sort_values(ascending=False))

# which addresses are not configured?
print(df[~df['known']]['address'].value_counts())

# temperature curve of one sensor
temperatures = df[df['address'] == 'FF-AA-DD-81']
print(pd.json_normalize(temperatures['decoded'])['temperature'].describe())

# telegrams per minute
print(df.set_index(pd.to_datetime(df['timestamp'])).resample('1min').size())
```

## Timeseries database and Grafana

Every recorded telegram - including the correlated meta data (device name, EEP, area, platform and
the decoded values) - can additionally be written into an **InfluxDB** bucket. On top of that bucket
**Grafana** can analyse the complete history: telegrams per device over months, temperature and
humidity curves, button press patterns, radio quality (repeater counter), test runs and calibrations.

```yaml
eltako:
  general_settings:
    log_enocean_telegrams: True
    timeseries_enabled: True
    timeseries_url: http://localhost:8086     # InfluxDB
    timeseries_token: <api token>             # InfluxDB 2.x token / InfluxDB 1.8: "user:password"
    timeseries_org: home                      # InfluxDB 2.x only, empty for 1.8
    timeseries_bucket: eltako                 # InfluxDB 2.x bucket / 1.8: "database/retention_policy"
    timeseries_measurement: eltako_telegram   # optional
```

Works with InfluxDB 2.x (native api) and InfluxDB 1.8+ (via its v2 compatibility api). No client
library is needed - the integration posts the line protocol directly, batched and from its own
worker thread. If the database is down, telegrams are counted as failed and the bus is never blocked.
All settings can also be changed on the **Settings** page of the web ui.

### Data model

| | |
|---|---|
| measurement | `eltako_telegram` |
| tags (filterable) | `gateway_id`, `direction`, `msg_type`, `address`, `local_address`, `device_name`, `eep`, `area`, `platform`, `known`, `role` |
| fields | `count=1` (always - makes counting trivial), `status`, `data`, `rp_count` and every decoded EEP value (`temperature`, `humidity`, `target_temp`, ...) |
| time | timestamp of the telegram (ns) |

### Example Grafana queries (Flux)

```flux
// telegrams per device, over time
from(bucket: "eltako")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "count")
  |> group(columns: ["device_name"])
  |> aggregateWindow(every: 1h, fn: sum)

// temperature curve of one sensor
from(bucket: "eltako")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "temperature")
  |> filter(fn: (r) => r.device_name == "Temp Living Room")

// unknown devices seen in the last 24 h
from(bucket: "eltako")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "count")
  |> filter(fn: (r) => r.known == "False")
  |> group(columns: ["address"])
  |> sum()
```

### Backfill of the history

Telegrams are exported live from the moment the export is enabled. The **history in the rotating
log files** (jsonl) can be imported once with the service
`eltako.export_telegram_log_to_timeseries` (Developer tools → Actions). The files are read oldest
first; records without a timestamp are skipped. Running it twice duplicates nothing visible in
practice - InfluxDB overwrites points with identical timestamp and tag set.

## Service

| Service | Description |
|---|---|
| `eltako.clear_telegram_log` | Resets statistics and live buffer. The log file is not modified. |
| `eltako.export_telegram_log_to_timeseries` | Backfill: writes the history of the jsonl log files into the configured InfluxDB bucket. |

## Websocket API

The web ui is based on the following websocket commands (admin only), which can also be used by own
dashboards or scripts:

| Command | Result |
|---|---|
| `eltako/telegram_log/info` | status, configuration and counters |
| `eltako/telegram_log/statistics` | summary and per-device statistics |
| `eltako/telegram_log/recent` | last telegrams from the ring buffer (parameter `limit`) |
| `eltako/telegram_log/subscribe` | live stream of all recorded telegrams |
| `eltako/telegram_log/clear` | resets statistics and buffer |
| `eltako/telegram_log/refresh_devices` | rebuilds the list of known devices |

## Relation to the normal logging

This telegram log is independent of the Home Assistant logger described in [docs/logging](../logging/readme.md).
Debug logging (`eltako: debug`) writes human readable log lines into the Home Assistant log, while the
telegram log writes structured, machine readable records into a separate file.
