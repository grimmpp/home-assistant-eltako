# Web UI of the Eltako Integration

The integration brings its own web ui (Home Assistant panel). It is part of the integration
(folder [`custom_components/eltako/frontend`](../../custom_components/eltako/frontend)) &ndash; there is
**no additional package** and **no build step** involved. The pages are plain javascript modules which
talk to the integration through the Home Assistant websocket connection.

## It is there by default

**Nothing has to be configured.** As soon as the integration is set up in Home Assistant
(*Settings &rarr; Devices & services &rarr; Add integration &rarr; Eltako*), the entry **Eltako** is in the
sidebar &ndash; visible for administrators only. There is no `configuration.yaml` involved, and the
settings of the integration are edited on the *Settings* page of this panel.

It is the place the integration is meant to be used from:

* **Gateways** are created, edited and removed on the *Overview* page. Adding the integration already
  detects what it can ([plug & play](../plug-and-play/readme.md) probes the serial ports and listens for
  mDNS); a gateway which cannot be identified - an FGW14-USB looks like any other serial adapter, a LAN
  gateway which does not announce itself is invisible - is added with **"+ add gateway"**: type, serial
  port or host, id. The ports of a scan are offered as suggestions and the base id is queried from the
  hardware, so nothing has to be looked up.
* **Devices** are added on the *Devices* page: by hand with the device catalog as a template, taken over
  from a bus scan or from the telegrams of an unconfigured address, or imported from an EnOcean Device
  Manager project, a PCT14 export or an existing yaml.
* The telegrams of the bus are watched on the *Live telegrams* and *Statistics* pages.

<details>
<summary>Switching it off</summary>

The panel can only be removed in `configuration.yaml`, not from the panel itself &ndash; a value changed
in the web ui is stored as an override which wins over the yaml, so switching it off there would take
away the very page that could switch it back on.

```yaml
eltako:
  general_settings:
    enable_frontend: False
```

`enable_frontend` is the only setting which needs a restart of Home Assistant to take effect.

</details>

### Telegram pages

The live view and the statistics need the telegram recording, which is **off** by default (it keeps
every telegram in a ring buffer):

```yaml
eltako:
  general_settings:
    log_enocean_telegrams: True                     # records all telegrams
    telegram_log_filename: enocean_telegrams.jsonl  # optional: also write them into a file
```

The same two settings are on the *Settings* page of the panel and take effect immediately &ndash; the yaml
above is only needed if the configuration is kept in files. If recording is switched off, the telegram
pages explain what to enable instead of staying empty.

## Two views: simple and expert

The panel comes in two views, switched with the button at the right end of the navigation bar:

* **Simple** &ndash; one page with all your devices as cards, grouped by room: name, current state, a
  switch for lights, sockets and covers, rename, move to another room, remove. Adding a device asks for
  the few things which cannot be guessed (kind of device, model, address, name, room), the automatic
  detection is one button, and devices which sent a telegram but are not set up yet are offered with a
  single "+ add". No EEPs, no bus positions, no base ids.
* **Expert** &ndash; everything the panel can do: gateways, plug &amp; play, the hierarchical bus view,
  live telegrams, statistics, device tests and all settings. This is the panel as it was.

The choice is stored in the browser, so a reload opens the same view again. Home Assistant starts in the
**simple** view, the [standalone runtime](../standalone/readme.md) &ndash; a tool for installation and
development &ndash; in the **expert** view. A bookmarked url wins over the stored view: opening
`/eltako#/telegrams` switches to the expert view by itself.

## Pages

The panel has its own navigation. Every page has its own url and can be bookmarked,
e.g. `/eltako#/telegrams`. The *View* column says in which of the two views a page appears.

| Page | Url | View | Content |
|---|---|---|---|
| **My devices** | `/eltako#/home` | simple | All devices as cards, grouped by room: state, on/off and up/down for what can be operated, rename, move to another room, remove. Plus the automatic detection ("Search devices"), a reduced add form and the devices which were discovered but are not set up yet. |
| **Overview** | `/eltako#/overview` | expert | One tile per gateway (type, protocol, base id, connection, serial path, recorded telegrams) with "edit gateway" and "remove gateway" for gateways created here, counters for devices, entities and telegram rate, the [plug & play](../plug-and-play/readme.md) push button with the report of the last detection run, the serial port scan, entities per platform and the configured areas. |
| **Control** | `/eltako#/control` | both | Use the configured devices: switch, dim, move covers, adjust temperatures. |
| **Devices** | `/eltako#/devices` | expert | All configured devices of all gateways with their source (yaml / web ui), the hierarchical view of every RS485 bus incl. the passively detected bus members and the active bus scan, add/edit/remove, the import of `.eodm` projects, PCT14 exports and yaml - and the **unknown devices**: addresses which sent telegrams but are not configured yet, incl. their EEP (from a 4BS teach-in telegram if available, otherwise guessed). One click opens the device form prefilled. |
| **Live telegrams** | `/eltako#/telegrams` | expert | Live stream of all telegrams: time, direction, gateway, address, device name, entity ids, EEP, message type, raw data and decoded values. Filterable by text, direction and "only unknown", can be paused, exported as CSV, and a click on a row shows the complete record. Telegrams can be sent from here as well. |
| **Statistics** | `/eltako#/statistics` | expert | One row per EnOcean address: number of telegrams (incoming/outgoing), average/min/max interval, first/last seen, message types, platform, area, entity ids, current state and the last decoded values. Sortable and exportable. |
| **Tests** | `/eltako#/tests` | expert | [Functional device tests](../device-tests/readme.md) against the real hardware: configuration check, teach-in test, burst test, cover travel times. |
| **Settings** | `/eltako#/settings` | expert | The general settings of the integration, editable. Values changed here are stored as overrides which win over `configuration.yaml`. |
| **Help** | `/eltako#/help` | both | Documentation and tutorials, plus every supported device, EEP, gateway and platform. The lists are compiled by the backend from the device catalog, the platform schemas and the EEP registry of `eltakobus`, so they always match the version you run. |
| **About** | `/eltako#/about` | both | Information about the integration: version, Home Assistant version, gateways, devices/entities, the feature list and the dependencies. |

## Structure of the frontend

Frontend and backend code are strictly separated. The frontend folder contains javascript only and is
served as a static path (`/eltako_frontend`), the backend lives in the python modules of the integration.

```
custom_components/eltako/
    frontend/                     # frontend only, no python
        eltako-panel.js           # entry point: shell, navigation, routing, live subscription
        lib/api.js                # websocket commands
        lib/form.js               # forms rendered from the schemas of the backend
        lib/styles.js             # styles (uses the Home Assistant theme variables)
        lib/utils.js              # formatting helpers
        pages/home.js             # 'My devices' - the page of the simple view
        pages/overview.js         # one module per page
        pages/control.js
        pages/devices_config.js   # 'Devices'
        pages/telegrams.js
        pages/devices.js          # 'Statistics'
        pages/tests.js
        pages/settings.js
        pages/help.js
        pages/about.js
    websocket.py                  # backend: general information about the integration
    enocean_logger.py             # backend: telegram recording, statistics and live stream
```

Every page module exports one object with this contract:

| Member | Purpose |
|---|---|
| `id`, `title`, `subtitle`, `icon`, `glyph` | identity and navigation entry |
| `load(ctx)` | loads the data the page needs (optional) |
| `render(ctx)` | returns the html of the content area |
| `renderToolbar(ctx)` / `bindToolbar(ctx, root)` | optional toolbar and its event handlers |
| `renderStatus(ctx)` | optional status pills next to the page title |
| `afterRender(ctx, root)` | event handlers of the content (optional) |
| `onTelegram(ctx, telegram)` | called for every telegram of the live stream (optional) |
| `badge(ctx)` | optional badge in the navigation |
| `modes` | views the page appears in, e.g. `["user", "expert"]` (optional, default: expert only) |
| `refreshMs` | reload interval of the page (optional) |
| `needsRecording` | if true, the page shows a hint when telegram recording is off |

`ctx` gives access to `hass`, the websocket api, the shared `state` (loaded data and view state), the
current view (`ctx.mode`, `ctx.setMode(mode, pageId)`) and to the render/navigation functions of the
shell. The shell owns the telegram subscription, so the live data keeps running while another page is
open.

To add a page: create a module in `pages/`, export a `page` object and add it to the `PAGES` array in
`eltako-panel.js`. Without `modes` it belongs to the expert view; `modes: ["user", "expert"]` puts it
into both.

## Websocket API

| Command | Result |
|---|---|
| `eltako/integration_info` | version, Home Assistant version, effective general settings, gateways, entity/device counts |
| `eltako/configured_gateways` | all configured gateways incl. connection state |
| `eltako/potential_usb_ports` | serial ports which could be a gateway |
| `eltako/info` | content of `manifest.json` |
| `eltako/gateways/form` | everything the "add gateway" wizard needs (types, ports, next free id) |
| `eltako/gateways/add` / `eltako/gateways/update` / `eltako/gateways/remove` | create, change and remove a gateway of the web ui |
| `eltako/devices/form` | fields and device templates per platform (derived from the schemas) |
| `eltako/devices/list` | all configured devices incl. their source (yaml or web ui) and activity |
| `eltako/devices/add` / `eltako/devices/update` / `eltako/devices/remove` | create, change and remove a device of the web ui |
| `eltako/plug_and_play/status` | state, progress and report of the [plug & play](../plug-and-play/readme.md) detection |
| `eltako/plug_and_play/run` | switches plug & play on/off and/or starts a detection run |
| `eltako/telegram_log/info` | status and counters of the telegram logger |
| `eltako/telegram_log/statistics` | summary and per device statistics |
| `eltako/telegram_log/recent` | last telegrams from the ring buffer (parameter `limit`) |
| `eltako/telegram_log/subscribe` | live stream of recorded telegrams |
| `eltako/telegram_log/clear` | resets statistics and buffer |
| `eltako/telegram_log/refresh_devices` | rebuilds the list of known devices |

All commands require an administrator, except the three legacy commands `eltako/info`,
`eltako/configured_gateways` and `eltako/potential_usb_ports`.

## Development

Because the frontend consists of plain javascript modules, no toolchain is required: edit the files in
`custom_components/eltako/frontend`, reload the browser (the files are served without cache headers) and
the change is active. Only when the integration is (re)started the panel itself gets registered again.

The unit test `tests/test_enocean_logger.py` verifies that all frontend modules exist and that the folder
which is served statically really contains frontend code only.
