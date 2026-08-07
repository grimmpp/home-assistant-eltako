# The websocket api of the web ui

Every page of the [web ui](../web-ui/readme.md) talks to the integration through Home Assistant's
websocket connection, and through nothing else. There is no REST endpoint, no template rendering
and no state the frontend keeps for itself: a page asks for what it needs, renders the answer, and
asks again.

**55 commands**, all named `eltako/*`. 47 of them are named in
[`const.py`](../../custom_components/eltako/const.py) as `WS_*` constants; the four
`device_tests/*` and `config/import` are named in their own module because those features are
self contained, and three legacy ones are literals in
[`core/websocket.py`](../../custom_components/eltako/core/websocket.py).

> **The rule behind the whole api:** a command returns something ready to render. Which EEPs
> exist, which fields a form has, which gateways a test may use, what a suggestion is worth - all
> of it is decided in python. When a command would return raw data that javascript then has to
> interpret, the split is in the wrong place. See
> [the web ui](readme.md#the-web-ui) in the architecture guide.

---

## Calling one by hand

Useful when a page misbehaves and you want to know whether the backend or the rendering is at
fault. Any Home Assistant websocket client works - below with `websocat` and a
[long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile):

```bash
websocat ws://localhost:8123/api/websocket
# < {"type":"auth_required", ...}
{"type":"auth","access_token":"eyJ..."}
{"id":1,"type":"eltako/devices/list"}
{"id":2,"type":"eltako/bus/read_memory","gateway_id":0}
```

Every answer carries the `id` of its request. A failing command answers with
`{"success": false, "error": {...}}` instead of raising - the page shows that message.

In the [standalone runtime](../standalone/readme.md) the same commands are served by its own small
websocket server - it implements the subset the frontend uses - so a request written against Home
Assistant works there unchanged.

### Who may call them

48 of the 55 carry `@websocket_api.require_admin` and are refused for a non-admin user. Seven do
not: the three legacy commands `eltako/info`, `eltako/configured_gateways` and
`eltako/potential_usb_ports`, which only read, and the four `device_tests/*` commands - those
**do** send telegrams onto the bus, so the missing decorator there is an asymmetry rather than a
decision. Add it when you touch that module.

---

## Integration, help and onboarding

Registered in [`core/websocket.py`](../../custom_components/eltako/core/websocket.py) and
[`core/onboarding.py`](../../custom_components/eltako/core/onboarding.py).

| Command | Parameters | What it answers |
| --- | --- | --- |
| `eltako/integration_info` | &ndash; | Everything the *about* and *overview* pages need: version, gateways, entity counts, which features are switched on |
| `eltako/info` | &ndash; | The `manifest.json` of the integration |
| `eltako/configured_gateways` | &ndash; | Every gateway object with its connection state, base id, model and whether it is simulated |
| `eltako/potential_usb_ports` | &ndash; | The serial ports which could carry a gateway |
| `eltako/help/catalog` | &ndash; | Everything the *help* page lists: devices, EEP profiles, gateways, platforms and the documentation index - compiled by [`catalog/help_catalog.py`](../../custom_components/eltako/catalog/help_catalog.py) |
| `eltako/onboarding/consume` | &ndash; | Whether this browser should be sent to the web ui once after the installation. The flag is flipped in the same call, so exactly one browser gets it |

## Settings

[`config/general_settings.py`](../../custom_components/eltako/config/general_settings.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/settings/get` | &ndash; | Every setting with its descriptor, its effective value, where that value comes from (default / yaml / ui) and whether it is locked |
| `eltako/settings/set` | `settings` | Store overrides. Only values which really differ are written, so saving a form does not detach a whole group from the yaml |
| `eltako/settings/reset` | `names` | Drop those overrides again, back to the yaml or the default |

`enable_frontend` is refused by both writing commands - an override stored there would win over
`configuration.yaml` and remove the page that could switch it back on.

## Devices

[`config/device_config.py`](../../custom_components/eltako/config/device_config.py) and
[`observation/device_activity.py`](../../custom_components/eltako/observation/device_activity.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/devices/form` | &ndash; | The form descriptor: every platform with its fields, the EEPs it accepts, the device templates of the catalog and the areas Home Assistant knows. The frontend renders it generically |
| `eltako/devices/list` | &ndash; | All devices of all gateways with their source (yaml / web ui), their entity ids and their activity |
| `eltako/devices/add` | `gateway_id`, `platform`, `device` | Validate and store a device. Adding several at once writes them in one go, so the gateway reloads exactly once |
| `eltako/devices/update` | `gateway_id`, `platform`, `address`, `device` | Change it. Fields the form does not render are kept from the stored device instead of being dropped |
| `eltako/devices/remove` | `gateway_id`, `platform`, `address` | Remove it. Devices declared in `configuration.yaml` are protected |
| `eltako/devices/remove_all` | `gateway_id` (optional) | Remove **every** device created in the web ui - of one gateway or of all of them. Each gateway is written once, so the entities are rebuilt in one reload per gateway. Gateways, stored bus memories and `configuration.yaml` devices are kept. The web ui asks before it sends this (button *Remove all & search again*) |
| `eltako/devices/activity` | &ndash; | Per address: how often it reported, when it was first and last heard from, how many sessions ago |
| `eltako/devices/activity_clear` | &ndash; | Forget all of that |

## Gateways

[`config/gateway_config.py`](../../custom_components/eltako/config/gateway_config.py) and
[`tools/gateway_scan.py`](../../custom_components/eltako/tools/gateway_scan.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/gateways/form` | &ndash; | The form descriptor for a gateway: types, their fields and what each one needs |
| `eltako/gateways/add` | `gateway` | Store it **and** create its config entry, so it is set up right away |
| `eltako/gateways/update` | `gateway_id`, `gateway` | Change name, port, host, base id, auto reconnect or message delay and reconnect with them. The id stays fixed - it is part of every entity id of that gateway |
| `eltako/gateways/remove` | `gateway_id` | Remove it together with its config entry |
| `eltako/gateways/scan` | &ndash; | Every serial port, the usb descriptor behind it, which gateway uses it and a suggestion for its `device_type`. Runs in the executor - it reads the file system |

A gateway declared in `configuration.yaml` cannot be changed here; the yaml wins and the answer
says so.

## The bus

[`observation/bus_members.py`](../../custom_components/eltako/observation/bus_members.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/bus/members` | &ndash; | Every bus position collected **passively** from the traffic - model, channels, taught-in senders from the stored memory image, and the radio devices next to it. No bus lock |
| `eltako/bus/read_memory` | `gateway_id` | The **active** scan: discovery of every position plus the complete device memories. Locks the bus for minutes and runs in its own thread with its own event loop, so nothing can delay its timing. Answers `{started: false, reason: 'already_running', busy_with: ...}` when another operation has the bus |
| `eltako/bus/teach_in_senders` | `gateway_id`, `address` (optional) | Compare the configured sender ids against the device memories and write the missing ones with `ensure_programmed`. Error `bus_busy` while a scan runs |

While one of those runs, the bus of **that** gateway belongs to it alone: commands are queued
and sent afterwards, a second scan or teach-in is refused, and `eltako/bus/members` reports it
per gateway in `scans_running` and `busy_with`. See *Exclusive access to the bus* in the
[architecture](readme.md).

## Telegrams

[`observation/enocean_logger.py`](../../custom_components/eltako/observation/enocean_logger.py)
and [`core/websocket.py`](../../custom_components/eltako/core/websocket.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/telegram_log/info` | &ndash; | Whether recording is on, which file, its size and rotation, and the state of the timeseries export |
| `eltako/telegram_log/statistics` | &ndash; | Per address: counts, intervals, message types, first and last seen - plus the ready `unknown_devices` list with EEP candidates, the best suggestion and a pastable yaml snippet |
| `eltako/telegram_log/recent` | &ndash; | The telegrams still in the ring buffer |
| `eltako/telegram_log/subscribe` | &ndash; | **Subscription**: every telegram is pushed as an event until the connection closes or unsubscribes. This is what the live view runs on |
| `eltako/telegram_log/clear` | &ndash; | Empty the buffer and the statistics |
| `eltako/telegram_log/refresh_devices` | &ndash; | Re-read the device names, areas and entity ids the recorded telegrams are annotated with |
| `eltako/send_telegram_form` | &ndash; | The form: every EEP of the library with its fields, plus the gateways and sender ids which may be used |
| `eltako/send_telegram` | `gateway_id`, and either `eep` + `fields` or `raw` | Send an arbitrary telegram - built from an EEP or as raw ESP2 hex (11 body bytes or the full 14 byte frame, checksum validated) |
| `eltako/grafana/sync` | &ndash; | Push the five dashboards shipped with the integration into the configured Grafana, pointing every panel at the InfluxDB datasource which actually exists there |

## Plug & play

[`tools/plug_and_play.py`](../../custom_components/eltako/tools/plug_and_play.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/plug_and_play/status` | &ndash; | The report of the current or last run, with a machine readable `stage` next to the readable step. Published **while the run is still going**, so the overview page fills up live |
| `eltako/plug_and_play/run` | `enable` (optional) | Switch the detection on or off and/or start a run in the background - reading a bus takes minutes, so it is never awaited |
| `eltako/plug_and_play/probe` | `include_mdns` (optional) | Detect only, create nothing, read no bus: *would this stick be recognized?* Awaited, unlike `run` - without the bus scan it takes seconds |

## Device tests

[`tools/device_tests.py`](../../custom_components/eltako/tools/device_tests.py). The names are
literals in that module - the feature is self contained.

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/device_tests/info` | &ndash; | Which tests exist, which parameters each takes, which gateways it may use (`wired_gateways_only` for the burst test) and the last result |
| `eltako/device_tests/start` | `test`, `params` (optional) | Start one. A test which cannot run is refused **with its reason** instead of producing a misleading failure |
| `eltako/device_tests/stop` | &ndash; | Stop the running one |
| `eltako/device_tests/subscribe` | &ndash; | **Subscription**: the log lines and the result as they happen |

## Simulation

[`simulation/websocket.py`](../../custom_components/eltako/simulation/websocket.py). All of these
call [`simulation/service.py`](../../custom_components/eltako/simulation/service.py), which the
command line calls too - the web ui and `python -m eltako_standalone simulate` do exactly the same
thing. See [docs/simulation](../simulation/readme.md).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/simulator/form` | &ndash; | Everything the *simulation* page shows: gateways, devices, presets, profiles and the fields of each profile |
| `eltako/simulator/preset` | `keys`, `gateway_id`, `device_keys` (all optional) | The starter set - three kinds of gateway with the devices an installation consists of, or example devices for one existing gateway |
| `eltako/simulator/activate` | `active` | Switch the whole simulation on or off. Off removes every simulated device and the config entries of the simulated gateways, so nothing of it can be used by accident. Nothing is lost - activating puts all of it back |
| `eltako/simulator/gateway_add` | `device_type`, `name` (optional) | Add a simulated gateway of a real type, or host virtual devices on a **real** one |
| `eltako/simulator/gateway_remove` | `gateway_id` | Remove it |
| `eltako/simulator/base_id` | `gateway_id` | Let it report its base id - the info telegram a real FAM14 or ESP3 stick answers with |
| `eltako/simulator/device_add` | `gateway_id`, `device` | Add a virtual device |
| `eltako/simulator/device_update` | `gateway_id`, `address`, `device` | Change its values, its name or its send interval. The interval is applied the moment the number changes |
| `eltako/simulator/device_remove` | `gateway_id`, `address` | Remove it |
| `eltako/simulator/teach_in` | `gateway_id`, `address`, `sender_id`, `sender_eep`, `name` (optional) | Teach a sender into a simulated actuator, or remove it again - including a **real** sender, so a real wall switch can switch a simulated light |
| `eltako/simulator/trigger` | `gateway_id`, `address`, `state` (optional) | Let a device send its telegram now |

## Configuration import

[`config/config_import.py`](../../custom_components/eltako/config/config_import.py).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/config/import` | `content` | Parse a `.eodm` project, a PCT14 xml export or an `eltako:` yaml - the format is detected from the content - and answer with the preview: gateways, devices, what is skipped and why. Importing the same file twice changes nothing |

## Serial bridge

[`tools/serial_bridge.py`](../../custom_components/eltako/tools/serial_bridge.py). Publishing a
serial port over tcp, or attaching a published port as a pty - the way a gateway reaches a
container on macOS or Windows. See [testing with real hardware](../hardware-testing/readme.md)
for what the bridge can and cannot carry, and [docs/dev-container](../dev-container/readme.md).

| Command | Parameters | What it does |
| --- | --- | --- |
| `eltako/bridge/list` | &ndash; | Every bridge this process runs, with its byte counters, connection count and last error |
| `eltako/bridge/start` | `role` (`publish`/`attach`), `device`, `baud_rate`, `host`, `port`, `link` | Start one. `publish` offers a local port over tcp, `attach` exposes a published port as a pty under `link`. Runs in the executor - binding a socket and opening a serial port block |
| `eltako/bridge/stop` | `name` | Stop it by the name `start` returned |

The three commands are a thin adapter over `start_bridge` / `stop_bridge` / `bridge_status`,
which take and return plain dicts and know nothing about Home Assistant - a REST endpoint or the
CLI drives the same objects.

---

## Adding a command

1. Name it in [`const.py`](../../custom_components/eltako/const.py) as a `WS_*` constant - unless
   the feature is self contained enough to own its name, like the device tests.
2. Write the handler **next to the feature it belongs to**, not in `core/websocket.py`. That
   module owns the shared part of the api, not every command.
3. Register it in that module's `register_websocket_commands()`, which
   [`core/integration.py`](../../custom_components/eltako/core/integration.py) calls during
   `async_setup()` - step 4, before anything else, because the api must answer even when the web
   ui itself is switched off.
4. Mirror the name in [`lib/api.js`](../../custom_components/eltako/frontend/lib/api.js) if a page
   uses it.

Return something the page can render. If you find yourself sending a shape that javascript has to
decide something about, move that decision into python first.
