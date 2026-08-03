# Web UI of the Eltako Integration

The integration brings its own web ui (Home Assistant panel). It is part of the integration
(folder [`custom_components/eltako/frontend`](../../custom_components/eltako/frontend)) &ndash; there is
**no additional package** and **no build step** involved. The pages are plain javascript modules which
talk to the integration through the Home Assistant websocket connection.

## Activation

```yaml
eltako:
  general_settings:
    enable_frontend: True
```

After a restart of Home Assistant the entry **Eltako** appears in the sidebar (visible for
administrators only). Activating the frontend also makes the telegram pages available &ndash; to actually
see telegrams, recording has to be enabled as well:

```yaml
eltako:
  general_settings:
    enable_frontend: True
    log_enocean_telegrams: True                     # records all telegrams
    telegram_log_filename: enocean_telegrams.jsonl  # optional: also write them into a file
```

If recording is switched off, the telegram pages explain what to configure instead of staying empty.

## Pages

The panel has its own navigation. Every page has its own url and can be bookmarked,
e.g. `/eltako#/telegrams`.

| Page | Url | Content |
|---|---|---|
| **Overview** | `/eltako#/overview` | One tile per gateway (type, protocol, base id, connection, serial path, recorded telegrams), counters for devices, entities and telegram rate, entities per platform and the configured areas. |
| **Live telegrams** | `/eltako#/telegrams` | Live stream of all telegrams: time, direction, gateway, address, device name, entity ids, EEP, message type, raw data and decoded values. Filterable by text, direction and "only unknown", can be paused, exported as CSV, and a click on a row shows the complete record. |
| **Device statistics** | `/eltako#/devices` | One row per EnOcean address: number of telegrams (incoming/outgoing), average/min/max interval, first/last seen, message types, platform, area, entity ids and the last decoded values. Sortable and exportable. |
| **Unknown devices** | `/eltako#/unknown` | Addresses which sent telegrams but are missing in `configuration.yaml`, incl. EEP (from a 4BS teach-in telegram if available, otherwise guessed) and a ready to use yaml snippet. The navigation shows their number as a badge. |
| **About** | `/eltako#/about` | Information about the integration: version, Home Assistant version, gateways, devices/entities, links to all tutorials, the effective `general_settings` (helpful for bug reports) and the dependencies. |

## Structure of the frontend

Frontend and backend code are strictly separated. The frontend folder contains javascript only and is
served as a static path (`/eltako_frontend`), the backend lives in the python modules of the integration.

```
custom_components/eltako/
    frontend/                     # frontend only, no python
        eltako-panel.js           # entry point: shell, navigation, routing, live subscription
        lib/api.js                # websocket commands
        lib/styles.js             # styles (uses the Home Assistant theme variables)
        lib/utils.js              # formatting helpers
        pages/overview.js         # one module per page
        pages/telegrams.js
        pages/devices.js
        pages/unknown.js
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
| `refreshMs` | reload interval of the page (optional) |
| `needsRecording` | if true, the page shows a hint when telegram recording is off |

`ctx` gives access to `hass`, the websocket api, the shared `state` (loaded data and view state) and to
the render/navigation functions of the shell. The shell owns the telegram subscription, so the live data
keeps running while another page is open.

To add a page: create a module in `pages/`, export a `page` object and add it to the `PAGES` array in
`eltako-panel.js`.

## Websocket API

| Command | Result |
|---|---|
| `eltako/integration_info` | version, Home Assistant version, effective general settings, gateways, entity/device counts |
| `eltako/configured_gateways` | all configured gateways incl. connection state |
| `eltako/potential_usb_ports` | serial ports which could be a gateway |
| `eltako/info` | content of `manifest.json` |
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
