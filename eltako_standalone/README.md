# ELTAKO Standalone

Runs the ELTAKO integration **without Home Assistant** - as a daemon with the
same web ui, or as a fast command line tool for testing and calibration.

> Full documentation: **[docs/standalone](../docs/standalone/readme.md)**

The integration code in `custom_components/eltako` runs **unchanged**. A small
shim package (`hass_shim/homeassistant`) provides exactly the subset of the
Home Assistant API the integration uses (entities, dispatcher, storage,
websocket commands, registries). Everything standalone-specific lives in this
folder - nothing in `custom_components/` depends on it.

```text
eltako_standalone/
├── hass_shim/homeassistant/   the Home Assistant API shim (activated via sys.path)
├── runtime.py                 boots the integration: config, gateways, entities
├── entity_api.py              eltako/entities/* websocket commands (list/control/subscribe)
├── server.py                  aiohttp web server: web ui + websocket endpoint
├── shell/                     browser bootstrap that loads the unchanged web ui
├── cli.py                     command line interface
└── tests/                     run with:  pytest eltako_standalone/tests
```

## Configuration

A config folder (default `~/.eltako-standalone`, override with `--config` or
`ELTAKO_CONFIG_DIR`) that works like the Home Assistant one:

```text
<config>/configuration.yaml         the same `eltako:` section as in Home Assistant
<config>/.storage/                  settings/gateways/devices created in the web ui
<config>/eltako-standalone.log      process log of `serve`/`run` (like home-assistant.log)
<config>/enocean_telegrams.jsonl    telegram recording (on by default)
```

Minimal `configuration.yaml`:

```yaml
eltako:
  general_settings:
    enable_frontend: True
    log_enocean_telegrams: True
  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-80-00
    serial_path: /dev/ttyUSB0
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        name: Ceiling light
        sender: {id: 00-00-B0-01, eep: A5-38-08}
```

You can also start with an **empty** `eltako:` section and create gateways and
devices completely in the web ui - they are stored in `.storage/` and survive
restarts. The `.storage` format matches Home Assistant, so a standalone
instance pointed at a copy of an HA config folder picks up the same settings,
ui gateways and ui devices.

## Web ui

```text
python -m eltako_standalone serve [--host 0.0.0.0] [--port 8124] [--token SECRET]
```

Serves the **same web ui** as inside Home Assistant (overview, telegram live
view, device statistics, device config, unknown devices, settings) plus a
standalone-only page **HA Entities**: all entities grouped by area with buttons,
sliders and dropdowns - switch lights, move covers, set temperatures like on a
Home Assistant dashboard.

By default the server binds to localhost without authentication. For remote
access use `--host 0.0.0.0 --token <secret>` and open the ui as
`http://<host>:<port>/?token=<secret>`.

## CLI

Startup takes about a second (no Home Assistant import), so it is practical
for testing and calibration:

```bash
python -m eltako_standalone scan                       # serial ports + gateway suggestions (no runtime)
python -m eltako_standalone listen                     # decoded live telegram stream (--json for jsonl)
python -m eltako_standalone devices                    # all entities with state (--platform light)
python -m eltako_standalone state cover.eltako_gw_1_00_00_00_06
python -m eltako_standalone control light.eltako_gw_1_00_00_00_01 turn_on brightness=128
python -m eltako_standalone control cover.eltako_gw_1_00_00_00_06 set_cover_position position=50
python -m eltako_standalone send --gateway 1 --sender 00-00-B0-01 --eep A5-38-08 \
        --field command=1 --field switching_command=1
python -m eltako_standalone send --gateway 1 --raw "0b 07 00 64 00 00 00 00 b0 01 00"
python -m eltako_standalone run                        # headless daemon (no web ui)
python -m eltako_standalone test [--list] [suite...]   # run the test suites (see below)
```

All commands accept `--config <folder>` and `--debug`.

## Example data / importing configurations

```text
python -m eltako_standalone --demo serve               # load the EnOcean Device Manager demo data
python -m eltako_standalone --import my_project.eodm serve
```

`--demo` loads the bundled example data of the EnOcean Device Manager
(`examples/demo.eodm`: a FAM14 bus with FSR14/FSB14/FMZ14 actuators, FTS14EM
inputs, radio buttons and a weather station) - ideal to explore the web ui and
the CLI without hardware. `--import FILE` does the same with your own file.

**All gateways and all devices of the file are imported** - also several
gateways on the same bus (e.g. a FAM14 plus an FGW14-USB): telegrams arriving
through more than one gateway are fine and all commands are idempotent. The
import itself is idempotent as well: a gateway which is already configured
(same type, base id and name) is not created again, but its devices are still
merged - missing ones are added, existing ones stay untouched. Importing the
same file twice changes nothing, importing an extended file adds exactly the
new parts.

The same import is available in the web ui: **Device config -> Import...**
accepts an `.eodm` project of the EnOcean Device Manager or an `eltako:` yaml
and shows a preview before anything is written. Imported gateways/devices are
stored like the ones created in the ui (they can be edited and removed there,
and yaml declarations always win). An `.eodm` file does not know the serial
port of this machine - a placeholder is used and reported, correct it
afterwards.

## Device tests (page "Tests" / CLI `devicetest`)

The functional device tests of the EnOcean Device Manager, running on the
gateways of this runtime - from the CLI and from the web ui page **Tests**:

```text
# bus burst test: gateway 1 sends a telegram burst, gateway 2 must receive all of it
python -m eltako_standalone devicetest burst --gateway1 1 --gateway2 2 \
        [--count 44] [--delay 0.01] [--runs 1]

# cover travel time test: drives the covers and measures their real travel
# times - the basis for time_closes/time_opens of an FSB actuator
python -m eltako_standalone devicetest cover --gateway 1 \
        [--covers 00-00-00-05,00-00-00-06] [--senders 00-00-B0-05,00-00-B0-06] \
        [--sequence "up:25,pause:2,down:25"] [--runs 1]
```

`--covers` and `--senders` are the actuator and sender addresses, used pairwise
by position:

| given | tested |
| --- | --- |
| neither | every configured cover of the gateway with its configured sender |
| only `--covers` | those configured covers (a filter) |
| both | exactly these pairs - **also actuators which are not configured yet**, which is the point when calibrating a fresh FSB. For a configured address the given sender overrides the configured one, its known travel times are kept. |
| `--senders` with one entry | that sender is used for every actuator (one HA sender taught into several channels) |

The **Tests** page of the web ui runs the same tests: pick the gateways/covers
or type the two address lists into *Actuator addresses* / *Sender addresses*
(they override the checkboxes), adjust the sequence (prefilled from the
configured travel times), watch the live telegram log and get the result incl.
runtime recommendations. The page
is controlled by the general setting `enable_test_page` (default: on during
development - switch it off in the settings without restarting, or set it to
`False` in the yaml for production).

The pytest suites of the project stay available on the command line:
`python -m eltako_standalone test [--list] [integration|standalone|device-manager]`.

## Telegram recording and Grafana (on by default)

Home Assistant records telegrams only on request - the standalone runtime is a test and
analysis tool, so it does the opposite. On the **first** start of a config folder these
settings are seeded into `.storage/eltako_general_settings`:

| Setting | Default | |
| --- | --- | --- |
| `log_enocean_telegrams` | on | record every telegram |
| `telegram_log_filename` | `enocean_telegrams.jsonl` | persisted, rotated after 7 days |
| `timeseries_enabled` | on | export into InfluxDB |
| `timeseries_url` | `http://localhost:8086` | `ELTAKO_INFLUX_URL` |
| `timeseries_token` / `_org` / `_bucket` | `eltako-dev-token` / `home` / `eltako` | `ELTAKO_INFLUX_TOKEN`, `..._ORG`, `..._BUCKET` |
| `grafana_url` | `http://localhost:3000` | `ELTAKO_GRAFANA_URL` |

They are **seeded once**, not enforced: everything changed afterwards in the web ui
(*Settings*) is kept, and a value set explicitly in
`configuration.yaml` is never seeded, so it is not shadowed. To get the defaults back,
delete `<config>/.storage/eltako_general_settings`.

Start InfluxDB and Grafana (no Home Assistant involved):

```bash
cd dev && ./start-analytics.sh          # docker compose --profile analytics up -d influxdb grafana
```

Two dashboards are provisioned automatically (folder *ELTAKO*, tag `eltako`):

* **ELTAKO - Telegram overview** - telegram rate by direction and gateway, most active
  addresses, distribution over message type and EEP, and a table of the addresses which are
  not configured yet. This is the Grafana home dashboard.
* **ELTAKO - Device analysis** - any decoded EEP value over time (temperature, humidity,
  illumination, meter reading, ...), switching states of the actuators, when each address was
  heard from last, telegrams per hour and area, and the average repeater level per address.

The **Grafana** button in the live telegram view of the web ui links straight to them (it is
shown as soon as `grafana_url` is set and the export is on).

If no InfluxDB is running the exporter reports the connection error in the web ui and keeps
retrying - the recording itself and the live view are not affected. To import the history
which was recorded before InfluxDB was up, call the service
`eltako.export_telegram_log_to_timeseries`.

## Windows, macOS, Linux

The runtime is plain Python and runs on all three platforms:

| | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Runtime, web ui, CLI | yes | yes | yes |
| Serial gateway path | `/dev/ttyUSB0` (or `/dev/serial/by-id/...`) | `/dev/cu.usbserial-XXXX` | `COM3` |
| `scan` command / port scan of the web ui | udev + sysfs (full detail) | via pyserial | via pyserial |
| USB re-plug relocation (find the stick by its usb serial number) | yes | no (needs sysfs) | no (needs sysfs) |
| Ctrl+C shutdown | signal handler | signal handler | `KeyboardInterrupt` (handled) |

Use the `cu.*` device on macOS (not `tty.*` - it blocks until DCD). LAN gateways
(`address`/`port` instead of `serial_path`) behave identically everywhere.

## Requirements

Python 3.11+ and the packages in `requirements-standalone.txt` (the bus
libraries of the integration plus aiohttp/pyyaml - **no** homeassistant):

```bash
pip install -r eltako_standalone/requirements-standalone.txt
```

Important: the standalone runtime must run in a process where the real
`homeassistant` package has not been imported (it may be installed, that is
fine - the shim wins via `sys.path`).

## Tests

```bash
pytest eltako_standalone/tests     # must run in its own pytest process
pytest tests                       # the tests of the integration, unchanged
```

## How it works / limits

* `runtime.py` puts `hass_shim/` at the front of `sys.path`, so
  `import homeassistant` resolves to the shim, then calls the normal
  `async_setup` / `async_setup_entry` of the integration. Config entries are
  created automatically for every configured gateway.
* Entity states live in a small state machine and are persisted on shutdown
  (`RestoreEntity` works like in Home Assistant).
* The web server implements the small websocket protocol subset the frontend
  uses (`auth_required/auth_ok`, `result`, `event`, `unsubscribe_events`).
* Not implemented (because the integration does not use it standalone):
  automations, scripts, recorder/history, HA cloud, other integrations.
* The shim mirrors the HA API of the version the integration is developed
  against. When the integration starts using a new HA API, the shim needs the
  matching addition - the standalone tests catch that immediately.
