# Analysing telegrams with Grafana

Every recorded telegram can be written into an InfluxDB bucket, **including its raw data
bytes and its correlated meta data**. Grafana on top of that answers questions the live view
cannot: what did this product send over the last month, which device is configured with the
wrong EEP, how did the temperature develop during a test run.

Setup: [dev container](../dev-container/readme.md#analysis-with-grafana) (one command) or
[standalone runtime](../standalone/readme.md) (on by default).

## What lands in the database

One point per telegram, in the measurement `eltako_telegram`.

**Tags** (indexed, use them to filter and group):

| Tag | Example | |
| --- | --- | --- |
| `address` | `FF-AA-DD-81` | EnOcean address of the sender |
| `local_address` | `00-00-00-05` | bus position, for devices behind a bus gateway |
| `device_name` | `Temp Living Room` | as configured |
| `eep` | `A5-04-02` | configured EEP |
| `msg_type` | `Regular4BSMessage` | telegram type |
| `direction` | `incoming` / `outgoing` | seen from Home Assistant |
| `gateway_id` | `1` | which gateway saw it |
| `area` / `platform` | `Living room` / `sensor` | as configured |
| `known` | `True` / `False` | is the address configured at all |
| `role` | `device`, `sender`, `thermostat`, … | |
| `decode_error` | `True` | the configured EEP could **not** decode this telegram |

**Fields** (the values):

| Field | Example | |
| --- | --- | --- |
| `count` | `1` | always 1, makes counting trivial |
| `data` | `00-50-64-0A` | **the raw data bytes** |
| `raw` | `a55a0b05…` | the complete ESP2 frame |
| `status` | `0x30` | status byte |
| `rp_count` | `2` | how often the telegram was repeated |
| `rssi_dbm` | `-72` | signal strength (ESP3 gateways only) |
| decoded EEP values | `temperature=21.5`, `humidity=44`, `state=true`, `switching_command=1`, … | one field per property of the EEP |

So yes - the payload is in Grafana, and you can analyse **by** payload. Example: which
distinct payloads did a device send, and how often?

```flux
from(bucket: "eltako")
  |> range(start: -2h)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "data")
  |> map(fn: (r) => ({ r with payload: r._value }))
  |> group(columns: ["payload", "address", "msg_type"])
  |> reduce(identity: {occurrences: 0},
            fn: (r, accumulator) => ({occurrences: accumulator.occurrences + 1}))
  |> group() |> sort(columns: ["occurrences"], desc: true)
```

That query is the panel *Distinct data payloads* of the inspector - a rocker switch shows a
handful of values, a sensor a wide spread, and a stuck device exactly one.

## Which dashboard for what

Five dashboards, folder **ELTAKO**, tag `eltako`. They ship with the integration
(`custom_components/eltako/grafana/dashboards/`) and are versioned together with the data
model above.

### Telegram overview - "is everything alright?"

The home dashboard, and the one to open first. Telegram rate by direction and by gateway,
the most active addresses, the distribution over message type and EEP.

**Unconfigured devices are shown next to the configured ones**, because on a fresh
installation they are usually the majority:

* *Telegrams of unknown devices* - the count as a tile
* *Configured vs. unconfigured addresses over time* - both as stacked bars
* *Most active unconfigured addresses* - with their last data payload, the address linking
  into the inspector
* *Unknown devices (not configured yet)* - the table, address linked as well
* in *Telegrams per EEP* they appear as **not configured** (they have no EEP) instead of a
  nameless slice

Use it to see at a glance whether the bus is busy as usual, whether a gateway went quiet, and
which devices are still missing from the configuration.

### Telegrams per device - "who talks how much?"

Per device over time, totals, first and last telegram, telegrams per hour and platform, and
the **average interval between two telegrams**.

Use it to find a battery sensor which stopped reporting (long interval, last telegram old) or
a device which floods the bus (very short interval). The interval is also the honest way to
choose a sensible `off_delay` or automation timing.

### Errors and bus health - "what is broken?"

Telegrams whose **configured EEP cannot decode them** (over time and as a table with the
configured EEP next to the actual message type - a 4BS device configured with an F6 profile
can never work), unconfigured addresses, repeated telegrams, and the signal strength per
device.

Use it after changing the configuration, and when a device behaves oddly: a red *wrong EEP*
tile is a configuration bug, a low `rssi_dbm` or a high repeater level is a radio problem.

### Product and test inspector - "what exactly did this product send?"

The dashboard for a single product, device or test run. Search by free text over address and
device name, narrow by device/address/EEP, and filter by **data payload**. Then:

* **Raw telegrams** - direction, message type, `data`, `raw`, `status`, repeater level and
  signal strength, newest first. This is the table to read after a test run.
* **Telegram sequence (in / out)** - when did which side talk. A command followed by an answer
  is a working round trip; a command without an answer is the failure to look at.
* **$value over time** - any decoded value, chosen with the *Decoded value* variable.
* **Message types and EEPs** and **Distinct data payloads** of the current selection.

Use it for calibration (drive a cover, read the real travel time from the answers), for
acceptance tests of a product, and to understand an unknown device.

### Device analysis - "how do the values develop?"

Any decoded EEP value over time for selected devices, switching states of the actuators as a
state timeline, a table of when each address was last heard from, telegrams per hour and area,
and the average repeater level.

Use it for the long view: temperature curves, drift, which room is actually used.

## Searching for one address and seeing all its telegrams

Three ways, from quickest to most thorough:

1. **Click it.** On the *Telegram overview*, the address column of both unconfigured-device
   tables is a link - it opens the *Product and test inspector* with that address preselected
   and the current time range kept.
2. **Pick it.** Open the *Product and test inspector* and choose the address in the **Address**
   dropdown (it lists every address which ever sent). The whole dashboard follows: raw
   telegrams, sequence, values, payloads.
3. **Search for it.** Type a part of the address or the device name into the **Search** box of
   the inspector - it matches both, so `B6-40` and `Wall switch` both work.

The url is bookmarkable, so a specific device is one link away:

```text
http://localhost:3000/d/eltako-inspect/eltako-product-and-test-inspector?var-address=FE-DB-B6-40&from=now-24h&to=now
```

The panel *Raw telegrams* then holds every telegram of that address with direction, message
type, data and status bytes.

## How do I see incoming telegrams?

Grafana is not a live view - it queries a database. Two things have to be right:

1. **Time range includes now**: top right, e.g. *Last 15 minutes*. A range like
   *yesterday* will never show a new telegram.
2. **Auto refresh is on**: the dropdown next to it, e.g. `10s`. The inspector ships with
   `10s`, the other dashboards with `30s`.

Then a telegram appears within seconds of arriving - the export flushes every 5 seconds or
every 500 telegrams, whichever comes first.

For a real live view use the **Live telegrams** page of the ELTAKO web ui: it is pushed over
a websocket and shows every telegram the moment it arrives, decoded. Grafana is the right tool
as soon as you ask about the past or want to aggregate.

If nothing arrives at all, check in this order:

* Web ui *Live telegrams*: do telegrams arrive in Home Assistant at all? If not, it is a
  gateway problem, not a Grafana one.
* The status pills of that page: `… exported` counts what went into InfluxDB, `timeseries
  error` shows the connection error.
* *About → Active configuration*: is *Export telegrams to InfluxDB* on, and are url, token,
  org and bucket right?

Telegrams recorded **before** the export was switched on are not in the database. Import them
once from the log files with the service `eltako.export_telegram_log_to_timeseries`.

## Getting the dashboards into Grafana

Two ways, both from the same files:

* **Dev container**: it mounts the folder into Grafana's provisioning path - the dashboards
  are simply there.
* **Any other Grafana** (NAS, Grafana Cloud, hand-made container): the button **Sync
  dashboards** on the *Live telegrams* page pushes them through the Grafana HTTP API. It
  creates the folder *ELTAKO* and points every panel at the InfluxDB datasource which actually
  exists there. Needs *Grafana URL* and *Grafana API token* in the settings (a service account
  token with the role **Editor**; `admin:admin` also works for a test setup). The result lists
  every dashboard with a link.

Editing a dashboard in Grafana is fine - a sync overwrites it, so save your own panels under a
different name or in a different folder.

## Own queries

The dashboards are a starting point, not a limit. Everything above is plain InfluxDB, so
*Explore* in Grafana works on the same data. Two patterns which cover most questions:

```flux
// count telegrams, grouped by any tag
from(bucket: "eltako") |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "count")
  |> group(columns: ["device_name"]) |> sum()

// a decoded value over time
from(bucket: "eltako") |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "eltako_telegram" and r._field == "temperature")
  |> aggregateWindow(every: 10m, fn: mean, createEmpty: false)
```

The panel queries of the shipped dashboards are executed against a real InfluxDB by
`tests/test_grafana_sync.py`, so they are known to be valid Flux - copying from them is safe.
