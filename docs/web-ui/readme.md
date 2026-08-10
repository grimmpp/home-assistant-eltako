# Web UI of the ELTAKO Integration

The integration brings its own web ui (Home Assistant panel). It is part of the integration
(folder [`custom_components/eltako/frontend`](../../custom_components/eltako/frontend)) &ndash; there is
**no additional package** and **no build step** involved. The pages are plain javascript modules which
talk to the integration through the Home Assistant websocket connection.

## It is there by default

**Nothing has to be configured.** As soon as the integration is set up in Home Assistant
(*Settings &rarr; Devices & services &rarr; Add integration &rarr; ELTAKO*), the entry **ELTAKO** is in the
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
* The telegrams of the bus are watched on the *Live telegrams* and *Statistics* pages, and
  *Radio reception* compares what several gateways made of the very same radio telegram -
  who received it, who missed it, and whether they read it the same way.

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
| **My devices** | `/eltako#/home` | simple | All devices as cards, grouped by room: state, on/off and up/down for what can be operated, rename, move to another room, remove. **The state is the switch**: the chip of a light, a socket or a cover toggles it when it is clicked - it is the element which says "on", so it is the element people press; the explicit buttons stay for the direction of a cover. **"details"** opens a popup with everything about that device (address, profile, gateway, sender and whether it is taught in, entities with their state, when it last reported, where it comes from) and, inside Home Assistant, the button *Open in Home Assistant* which goes to its device page. The **gateways** are cards of their own at the top - connected or not, how many devices are on them, with the same details popup (port, base id, protocol) - including a gateway which is configured but was never set up, which is otherwise invisible in this view. On a bus installation the page starts with **Initial Setup** at the very top - the instruction as four steps (connect the FAM14 &rarr; *Search devices* &rarr; check the list &rarr; optionally move to an everyday gateway), each step ticked off as soon as it is done; step 2 carries the search button itself and step 4 the gateway which is to operate the installation from then on. Step 4 lists **every** gateway, the ones on the bus included - going back to the FAM14 means the local `00-00-B0-xx` senders and is a change of the Home Assistant configuration just like going away from it - with the gateway which carries the installation right now preselected. Written into the actuators is only what is missing there, so a change which needs no write needs no connected FAM14 either (the local senders have been in the memories since the search). Every actuator card additionally carries a **teach-in** button, and the popup behind it is the answer to "this device does not react": it names the gateway which switches the device and the sender address it uses, and offers the gateways it can be moved to. A bus device gets that address **written into its memory** (only a FAM14 can write; an address which is already in there is left alone), a wireless one **learns it from a telegram** - press *Send teach-in* while the device is in learn mode. In both cases the address becomes the sender of that device in Home Assistant. The button is only on the cards where the choice is real: not on a sensor (nothing switches it) and not on a device out of `configuration.yaml`. It **folds away** and stays folded: the state lives in the browser (`localStorage`, `eltako-simple-setup-open`), so an installation which is set up keeps one line with the progress ("3/4") there instead of a block it has already read. Plus the automatic detection ("Search devices"), **"Remove all & search again"** (deletes every device created here and detects from scratch - for a configuration which drifted; asks once for both halves and names the number, keeps the gateways and everything from `configuration.yaml`, and waits for the gateways to be back before it searches - removing the devices reloads them), a reduced add form and the devices which were discovered but are not set up yet. |
| **Overview** | `/eltako#/overview` | expert | One tile per gateway (type, protocol, base id, connection, serial path, recorded telegrams) with "edit gateway" and "remove gateway" for gateways created here, counters for devices, entities and telegram rate, the [plug & play](../plug-and-play/readme.md) push button with the report of the last detection run, the serial port scan, entities per platform and the configured areas. |
| **HA Entities** | `/eltako#/control` | both | Use the configured devices: switch, dim, move covers, adjust temperatures. Grouped by room, and inside a room ordered by what a row is for - lights, sockets, covers, heating, then the buttons (teach-in, reconnect). A teach-in button carries the same name as its device, so every row says which kind it is. The toolbar carries a **type bar**: one button per kind of entity (lights, switches, covers, heating, selections, buttons, contacts, sensors, teach-in buttons) with its own icon and the number of rows behind it - a click switches that kind on or off, **All** shows everything, **Reset** goes back to the devices you operate (sensors and teach-in buttons off). Kinds which no entity has are left out. Every device additionally has **"telegram&hellip;"**: the values of its profile as input fields - dropdowns with names ("on", "up", "closed"), numbers with their unit and range - and a send button. For an actuator that is the profile of its **sender** (what it listens to), for a sensor its own. An actuator whose sender is not in its memory carries a **"teach in"** button; the teach-in button *entities* are left out here, their action sits in the row of the device itself. |
| **Devices** | `/eltako#/devices` | expert | All configured devices of all gateways with their source (yaml / web ui), **"details"** per row (the same popup as in the simple view: address, profile, gateway, sender and whether it is taught in, entities with their state, last report, origin - and *Open in Home Assistant*), the same button on every **gateway** (bus heading and wireless gateway row: status, port, base id, protocol, how many devices talk through it) and on a **bus position** which carries a configured device, the hierarchical view of every RS485 bus incl. the passively detected bus members and the active bus scan, **add/edit/remove** (the form opens as a popup in front of the page, so a row far down the list is still where it was afterwards), a column **Taught in** with every sender in the memory of that actuator - each named by the gateway it belongs to (or as somebody else's, e.g. a switch taught in with the PCT14) and removable one by one, **program senders of &hellip;** on the bus of a FAM14 (writes the sender addresses of a chosen wireless gateway into every actuator, so the installation can be operated with that gateway afterwards - only a FAM14 can write them), a **"switched by"** picker in every actuator row (which gateway is to switch *this* device: the chosen gateway's address goes into the actuator - written over the bus, or as a teach-in telegram for a wireless one - and becomes the sender of the device in Home Assistant, because a sender which is in no device is a device which looks configured and does nothing), the import of `.eodm` projects, PCT14 exports and yaml - and the **unknown devices**: addresses which sent telegrams but are not configured yet, incl. their EEP (from a 4BS teach-in telegram if available, otherwise guessed). One click opens the device form prefilled. |
| **Live telegrams** | `/eltako#/telegrams` | expert | Live stream of all telegrams: time, direction, gateway, address, device name, entity ids, EEP, message type, raw data and decoded values. A row of an address which is **not configured yet** carries **"identify&hellip;"**: a popup with everything which was seen (message types, count, first/last seen, last data, signal), which profiles fit - each with the confidence, the reason, the models of the catalog which speak it and **what this telegram would mean read as that profile** (`22.4 °C, 41 %` against `-13.2 °C` tells the candidates apart at a glance) - and **+ Add device**, which opens the device form prefilled with the suggestion. The values belong to the telegram of that row: the backend decodes exactly it with every candidate (`eltako/telegram_log/suggestions`), not the last one of the address. A telegram which comes from a [simulated](../simulation/readme.md) gateway is marked as such. Filterable by text, direction and "only unknown", can be paused, exported as CSV, and a click on a row shows the complete record. Telegrams can be sent from here as well: the values of a profile as input fields, raw ESP2 hex, or one of the two **teach-in telegrams** - the *profile teach-in* a sensor announces itself with (4BS states function, type and manufacturer; RPS has none, so a button press and its release are sent) and the *ELTAKO teach-in* an actuator learns a sender from, the telegram the teach-in button of a device produces. Both modes offer the sender profiles the integration teaches in (the table of `catalog/teach_in.py`), and the form says what it will send. |
| **Radio reception** | `/eltako#/radio` | expert | **The same radio telegram as every gateway received it.** Several transceivers in one installation receive every telegram; in the live view those receptions are consecutive rows, and whether they really say the same thing is left to the reader. This page groups the receptions of one transmission (same address within the time window) and compares them. Recording and analysis are separate, so everything is a **control**: the **window** (50&nbsp;ms &hellip; 2&nbsp;s &ndash; a gateway on a LAN connection or behind repeaters reports later than a stick), the **view**, and the restriction to **selected gateways** and **one sender** &ndash; which is the direct comparison of two gateways for one device. What it shows: **per gateway** how many telegrams it received of everything which happened, how many it *missed* while another gateway had them, how often it was first, how often alone, whether the telegrams arrived **directly or through repeater level 1 / 2**, and its average/best/worst signal strength &ndash; including a configured gateway which received nothing at all. **Gateway against gateway**: one row per pair with both / only A / only B / neither, how many of the shared ones differed, and how much stronger one of them hears the same telegram (dB). **Where the differences are**: one row per compared field (message type, ORG, data bytes, status byte, repeater hops, profile, values), sorted into the three groups which have different causes &ndash; *received differently* (the bytes out of the air), *read differently* (the same bytes, another meaning) and *different path* (a repeater hop, which is normal). Each row says in how many telegrams it happened and what share of everything that is, **on which device** (a button which restricts the whole page to that sender) and **which gateway reported something else than the majority** &ndash; or that the values were evenly split, which happens with two gateways and means no single gateway can be named. Below it, how many gateways heard the same transmission, as bars. **Which gateway receives which device**: one column per gateway, one row per address, with count, rate, average signal and the path tags (`direct` / `L1` / `L2`) &ndash; an empty cell means "this gateway never hears this device". And the **single telegram**: a click unfolds the reception of every gateway side by side &ndash; offset, message type, data with the **differing byte marked**, status, path, signal, **the profile it was read with and the values which came out of it** (a gateway can receive the same bytes and still *interpret* them differently), plus the gateways which did not receive it at all. The **view** buttons (all, identical, received differently, read differently, repeater hop only, somebody missed it, only one gateway, repeated &ndash; each with its count) sit directly above that table and filter **only** it: the counters and the per gateway / per address numbers always describe everything which was recorded, otherwise a filter could make a gateway look better than it is. **Problems are coloured**: red where the gateways did not receive or read the same thing and where a gateway hears nothing at all, yellow where something is worth a look (a telegram somebody missed, a device which only arrives over a repeater, a signal without reserve) &ndash; inside a telegram the deviating *cell* is coloured too, not just its row. A repeater hop alone stays uncoloured, because it is normal. Exportable as CSV, resettable without touching the live telegrams. |
| **Statistics** | `/eltako#/statistics` | expert | One row per EnOcean address: number of telegrams (incoming/outgoing), average/min/max interval, first/last seen, message types, platform, area, entity ids, current state and the last decoded values. Sortable and exportable. An address which is **not configured yet** carries the same **"identify&hellip;"** button as the live view: the popup with everything which was seen, the possible profiles with their values and models, and **+ Add device**. |
| **Reception** | `/eltako#/reception` | expert | [Site survey](../reception/readme.md): how well the gateways hear. One card per gateway with the average signal strength, its quality and the share of telegrams which arrived through a repeater, one row per link (a transmitter as heard by one gateway) with last/average/min/max dBm, and **save this spot** - the current reading is kept under a name so positions can be compared instead of remembered. Built for walking: a one-minute window by default, a filter for the one transmitter you carry, spots which survive a reload and a CSV export. |
| **Logs** | `/eltako#/logs` | expert | [What the integration itself writes](../logging/readme.md) - without file access and without the log of every other integration in between. The records of the `eltako` logger are kept in a ring buffer in memory and shown here, newest at the bottom like `tail -f`, with the time to the millisecond, the level, the child logger (`telegrams`) and the traceback of an error. Filterable by level and by text (the search runs in the backend, so it also finds records which are not on screen), downloadable as a text file, and the buffer can be emptied. The **log level of the integration** is set on the same page: it takes effect immediately, without a restart and without reloading the gateways, is remembered across restarts, and `inherit` gives it back to the `logger:` section of Home Assistant. |
| **Tests** | `/eltako#/tests` | expert | [Functional device tests](../device-tests/readme.md) against the real hardware: configuration check, teach-in test, burst test, cover travel times. |
| **Simulation** | `/eltako#/simulation` | expert | [Gateways and devices without hardware](../simulation/readme.md): create a simulated LAN gateway, USB300 or FAM14 (starter set in one click), put virtual devices behind it, define the values they report, trigger their telegrams, let them send periodically on their own and announce their profile (teach-in) with one button. Simulated devices are marked as such in every list. |
| **Settings** | `/eltako#/settings` | expert | The general settings of the integration, editable. Values changed here are stored as overrides which win over `configuration.yaml`. |
| **Help** | `/eltako#/help` | both | Documentation and tutorials, plus every supported device, EEP, gateway and platform. The lists are compiled by the backend from the device catalog, the platform schemas and the EEP registry of `eltakobus`, so they always match the version you run. |
| **About** | `/eltako#/about` | both | Information about the integration: version, Home Assistant version, gateways, devices/entities, the feature list and the dependencies. |

## What runs right now

Some operations of this integration take minutes and block the RS485 bus while they run: an
active bus scan, a teach-in, the base id request of a FAM14 and a plug &amp; play detection.
While one of them has the bus, the devices on it do not react and every other bus operation is
refused &ndash; a fact the user has to *see*, otherwise a button which does nothing looks like a
defect.

The panel therefore polls `eltako/activity` (`core/websocket.get_activity`, cheap: no io, only
the state which is kept anyway) and shows a banner **above the content of every page** &ndash;
independent of who started the job, on which page, in which browser tab, and whether the page
was reloaded since:

* what is running, in plain words ("Reading the bus of FAM14"), one line per job
* how far it is: one progress bar per bus with its position and memory counters
* since when it has been running
* and what it means: it takes a few minutes, the devices on that bus do not react, other
  buttons are refused &ndash; and nothing has to be pressed, the page updates itself and shows
  the result when it is done.

Buttons which would collide are disabled instead of failing: a page marks such a button with
`data-busy-block` (`any`, `bus`, `detection` or `gateway:<id>` &ndash; the tokens a job reports
in `blocks`), the shell disables it while a matching job runs and puts the reason into its
tooltip. When the job is done the buttons come back with their own tooltip, and the page is
reloaded once so the result is on screen without anybody pressing anything.

The wording lives in `frontend/lib/activity.js`, the banner in the shell (`eltako-panel.js`);
`ctx.isBusy(token)` / `ctx.busyReason(token)` answer the same question inside a page, and
`ctx.refreshActivity()` makes the banner appear the moment a page starts something long.

## Structure of the frontend

Frontend and backend code are strictly separated. The frontend folder contains javascript only and is
served as a static path (`/eltako_frontend`), the backend lives in the python modules of the integration.

```
custom_components/eltako/
    frontend/                     # frontend only, no python
        eltako-panel.js           # entry point: shell, navigation, routing, live subscription
        lib/api.js                # websocket commands
        lib/entity_hub.js         # live entity states: an element registers, a signal reaches it
        lib/bus_scan.js           # progress of the running bus scans - one row per bus
        lib/form.js               # forms rendered from the schemas of the backend
        lib/styles.js             # styles (uses the Home Assistant theme variables)
        lib/utils.js              # formatting helpers
        pages/home.js             # 'My devices' - the page of the simple view
        pages/overview.js         # one module per page
        pages/control.js
        pages/devices_config.js   # 'Devices'
        pages/telegrams.js
        pages/radio.js            # 'Radio reception' - one telegram as every gateway got it
        pages/devices.js          # 'Statistics'
        pages/logs.js             # 'Logs' - the log of the integration and its level
        pages/tests.js
        pages/simulation.js       # 'Simulation' - gateways and devices without hardware
        pages/settings.js
        pages/help.js
        pages/about.js
    core/websocket.py             # backend: general information about the integration
    observation/enocean_logger.py # backend: telegram recording, statistics and live stream
    observation/radio_comparison.py  # backend: one telegram as several gateways received it
    simulation/websocket.py       # backend: the simulation page
```

Which backend module answers a page is not arbitrary: every feature registers the websocket
commands of its own page. The layout of the python side is described in
[the architecture guide](../architecture/readme.md#the-layout).

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
| `leave(ctx)` | the page is closed: give listeners and timers back (optional) |
| `badge(ctx)` | optional badge in the navigation |
| `modes` | views the page appears in, e.g. `["user", "expert"]` (optional, default: expert only) |
| `refreshMs` | reload interval of the page (optional - see *live updates* below) |
| `needsRecording` | if true, the page shows a hint when telegram recording is off |

`ctx` gives access to `hass`, the websocket api, the shared `state` (loaded data and view state), the
current view (`ctx.mode`, `ctx.setMode(mode, pageId)`), the entity hub (`ctx.entities`) and to the
render/navigation functions of the shell. The shell owns the telegram subscription, so the live data
keeps running while another page is open.

### Live updates

`refreshMs` renders the whole content of a page again, which is right for a page whose data only
exists in the backend (statistics, a running bus scan) and wrong for anything a user operates: the
answer to a click arrives with the next tick, and a form which is open while the timer fires loses
what was typed. The simple view therefore has no interval at all - it updates per element:

* the panel hands every `hass` it receives to the **entity hub** ([`lib/entity_hub.js`](../../custom_components/eltako/frontend/lib/entity_hub.js)).
  Home Assistant sets a new one on every state change; the standalone shell re-sets its own after
  each pushed state event,
* a page registers the entity ids it displays (`ctx.entities.subscribe(ids, callback)`) and patches
  exactly the element which shows them - see `_watchEntities`/`_applyEntityState` in
  [`pages/home.js`](../../custom_components/eltako/frontend/pages/home.js),
* the listeners belong to the rendered dom: they are dropped before the next render and in
  `leave(ctx)`, which the shell calls when another page is opened,
* a page which shows what the *backend* computed can follow the telegram stream as well instead of
  polling: *Radio reception* has no `refreshMs` at all &ndash; its `onTelegram` hook collects the
  receptions of one transmission and asks for the analysis once, when the comparison window of that
  transmission has passed (`Analyse now` in its toolbar covers a quiet bus and a paused live view),
* the telegram stream keeps the rest current: a card flashes and says "last reported just now"
  without anything being loaded again.

The same idea carries the bus scans ([`lib/bus_scan.js`](../../custom_components/eltako/frontend/lib/bus_scan.js)).
Several buses are read **in parallel** - plug & play scans every bus at once, and the device page has
a scan button per gateway - and each scan takes minutes, so they are listed one below the other with
their own position/memory counters instead of one bar over their average. While a scan runs the
device page polls its counters and patches those rows only; the tables around them keep their dom.

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

Those are the ones the main pages use. There are **55 in total** - the bus scan, the device tests,
the simulation, the configuration import, the serial bridge and the settings have their own.

**&rarr; [The full reference](../architecture/websocket-api.md)**: every command with its
parameters, what it answers, which module owns it, and how to call one by hand against a running
Home Assistant.

Almost all of them require an administrator. The exceptions are the three legacy commands
`eltako/info`, `eltako/configured_gateways` and `eltako/potential_usb_ports`, and the four
`device_tests/*` commands.

## Development

Because the frontend consists of plain javascript modules, no toolchain is required: edit the files in
`custom_components/eltako/frontend`, reload the browser (the files are served without cache headers) and
the change is active. Only when the integration is (re)started the panel itself gets registered again.

The unit test `tests/test_enocean_logger.py` verifies that all frontend modules exist and that the folder
which is served statically really contains frontend code only.
