# Changes and Feature List

## Version 2.2.0
* **The web ui has two views: simple and expert**, switched with one small button at the right end of the navigation bar. The choice is stored in the browser, so a reload and the next visit open the same view again. Home Assistant starts in the **simple** view, the standalone runtime (a tool for installation and development) in the **expert** view. See [docs/web-ui](docs/web-ui/readme.md).
  * **Simple** is the new page *My devices* (`pages/home.js`): every device as a card, grouped by room - name, kind, current state, and for lights, sockets and covers the buttons to switch or move them. Renaming a device and moving it to another room is a two field form, removing it is one button. What a user does not need to see - EEPs, bus positions, base ids, telegrams - is not on it.
  * **Add device** in the simple view asks only for what cannot be guessed: kind of device, model (fills in the EEP from the device catalog), address, name and room. The other fields of the platform keep their default, so a device created here is exactly what the expert form would have produced. The **sender address** of an actuator is suggested automatically - a bus position gets `00-00-B0-xx` (the convention of the automatic detection and of the EnOcean Device Manager), a wireless device the next free address out of the base id range of its gateway - and stays editable.
  * **"Search devices"** starts the [plug & play](docs/plug-and-play/readme.md) detection incl. re-reading every bus: gateways on the serial ports and in the network, the actuators on their bus and the sensors taught into them. The page shows the progress and afterwards in plain words what was found, added or needs a decision. Devices which sent a telegram but are not configured yet are offered as cards with a single "+ add" (profile and model come from the backend suggestion).
  * **Expert** is the panel as it was - overview, devices, live telegrams, statistics, tests and settings. A page declares which views it appears in (`modes`, default: expert only); *Control*, *Help* and *About* are in both. A bookmarked url wins over the stored view: `/eltako#/telegrams` switches to the expert view by itself.
  * The device list of the backend carries the **entity ids** of every device now (read from the live entities, not from the telegram statistics), so the simple view shows states even when telegram recording is off. Info fields which describe a device instead of measuring something (event id, address) are marked as such and left out there.
* **Installing needs no input at all** - no gateway, no serial port, no `configuration.yaml`, no restart. *Add integration &rarr; Eltako* offers "set up and detect my gateways automatically" as its first option and creates an entry which carries **no gateway**: it is the integration itself, which brings the web ui and the detection with it (new `CONF_HUB` entry, handled by `async_setup_hub_entry`). Right after it was added one [plug & play](docs/plug-and-play/readme.md) run starts: the free serial ports are probed, LAN gateways which announce themselves via mDNS are picked up, every gateway which is identified beyond doubt gets its own config entry, its bus is read and the devices which are unambiguous are added. The overview page draws that run live.
  * The run happens **once**, requested by the config flow through a flag which the setup consumes - repeating it on every restart would lock the RS485 bus for minutes each time. Whether the detection keeps running afterwards is the setting `plug_and_play` as before.
  * A gateway which **cannot be identified** - an FGW14-USB is indistinguishable from any other serial adapter, a LAN gateway which does not announce itself cannot be found at all - is added on the overview page of the web ui ("+ add gateway", the form which already existed), or in the yaml. Neither the automatic nor the manual way needs a file.
  * The two manual paths of the config flow stay: picking up a gateway which is declared in the configuration but not set up yet, and defining one in the wizard. The wizard is what a second "Add integration" leads to once the integration itself is set up.
  * Everything which iterates the config entries already skipped an entry without a gateway description, so a gateway-less entry passes through; unloading it and deleting a device "of" it are handled explicitly.
* **The web ui is on by default** (`enable_frontend`, was off): install the integration, add it in Home Assistant, and the **Eltako** panel is in the sidebar - gateways, devices and all general settings are configured there. Nothing has to be written into `configuration.yaml` for anything anymore, so the option which had to be set before the ui could be reached is gone as a first step. The yaml keeps working and keeps winning for everyone who prefers files; the panel is switched off there with `enable_frontend: False` (still not switchable from the ui itself - an override stored there would win over the yaml and take away the page that could bring it back). The documentation leads with the ui way now, the file based configuration is documented as the alternative.
* **Links between the documents are relative** instead of `https://github.com/grimmpp/home-assistant-eltako/tree/main/...` (44 of them in the readme alone). An absolute link always points at the state of `main`, so every link to a document which was added on a branch was a 404 until that branch was merged - which was the case for the whole plug & play, architecture and device test documentation - and a fork linked back into this repository instead of into itself. Relative links follow whatever branch, fork or checkout they are read in. Absolute stays where it has to: github features (issues, pull requests, commits) have no file behind them, and the help page of the web ui renders inside Home Assistant, where a relative link would point into the Home Assistant frontend. `tests/test_doc_links.py` fails on a `tree/`, `blob/` or `raw/` link into this repository and on a relative link which does not resolve - which surfaced a handful of dead ones (a badge pointing at `github.com/LICENSE`, links into the removed `eltakodevice_discovery/` folder, and two table rows in the gateway documentation whose markdown had been pasted over each other).
* **The list of supported devices and EEPs is generated** (`generate_docs.py`) instead of written down: it is rendered from the device catalog, the platform schemas and the profile registry of `eltakobus` - the same source the help page of the web ui uses - into [docs/supported-devices.md](docs/supported-devices.md) and into the marked block of the readme. A device added to the catalog or an EEP added to a schema shows up there without anyone editing markdown. `tests/test_generated_docs.py` renders them again and fails while a generated file is out of date.
* No Need for defining base id in config file except for FGW14-SUB
  * Entity Ids of gateways change so that base id is not contained anymore
* Reverse Network EnOcean Bridge to be able to connect eo_man.
  * TODO: sending of message does often not work in the beginning
  * TODO: send gateway information frequently
* FAM14 can detect bus devices and report it into eo_man 
* Support for EUL Gateway
* Gateways can be used as repeater inside HA
* Button event ids changed => INCOMPATIBILTIY to older versions
* Button events can be used for e.g. dimming therefore events contains time information when and for how long buttons were pushed
* Created blueprint for dmming and switch lights off and on which trigger by EnOcean switches and not controlled via eltako actuators. You can use EnOcean switches to e.g. controll Zigbee lights from Philips Hue or any other protocol and lights which can be controlled by Home Assistant Automations.
* Connection state fixed: Display information about gateway connection was sometimes displayed incorrectly
* added repeater mode selection field for gateways
* added support for optional area field
* Bus members are detected passively and shown hierarchically (new module `bus_members.py`)
  * polling, status answers and discovery replies of the gateway are aggregated into a table of all bus positions - no bus lock, no active scan
  * models are identified via the library (`discovery_names`, disambiguated by size: FSR14_1x vs FSR14_4x) and enriched with the mapping table of the EnOcean Device Manager: description, suggested EEP/platform and the PCT14 teach-in position (function group / key function)
  * multi-channel devices: follow-up positions are attributed to their physical device (`Pos. 1-4 FSR14_4x`)
  * the device page has a hierarchical view (default): one section per RS485 bus with the physical devices and their channels, unconfigured channels can be taken over with one click; radio devices incl. the wireless gateways are listed under "Radio devices". Several buses stay apart - one section per bus gateway.
  * rows are linked with the Home Assistant device registry: "open device" jumps to the device page (every configured device row has its own "open" button as well)
  * clicking a device highlights its teach-in relations in green (sensor -> actuators and actuator -> taught-in sensors, both directions)
  * devices of a bus gateway which is configured but not set up in Home Assistant are shown at their bus position of the live bus (tagged with their gateway) instead of a second listing - the same physical device never appears twice
* Active bus scan with memory read-out ("scan bus & read memory" per FAM14)
  * own paced scan instead of `request_memory_of_all_devices` of the library: its sleeps are not awaited, which overruns the bus and killed the serial connection with write timeouts on a real FAM14
  * the scan runs in a dedicated thread with its own event loop, so nothing in Home Assistant can delay it, and every request is followed by a real pause - the bus timing stays intact
  * the taught-in senders of every device are extracted from the memory image (`get_all_sensors` of the library): sensor id, key function, channel and target address are shown per device, and the configured HA senders get a "taught in / not taught in" badge
  * the memory image survives the periodic re-enumeration of the FAM14 (a routine discovery reply no longer wipes it)
  * the memory content opens in a side panel on the right ("memory: n senders" per device) instead of cluttering the table
  * taught-in senders which are not configured yet appear in the device list: their EEP is derived from the key function (classification of the EnOcean Device Manager: EEP in the function name, push buttons F6-02-01, ids below 0x1500 are FTS14EM inputs, 00-00-B*.. are the virtual HA senders) - "+ add device" opens the form prefilled, so the device is registered correctly with one click. Wireless senders are listed under "Radio devices", wired FTS14EM inputs under their bus.
  * a watchdog reloads the config entry of the gateway if no telegram arrives after a scan
  * the memory images are persisted in the Home Assistant storage, so the taught-in senders are known right after a restart without scanning again (the scan locks the bus for minutes). Only the scan result is stored - the passively collected counters describe the current session. An image is discarded when the next discovery reply reports a different model or memory size, i.e. when the actuator behind that bus position was actually swapped; images which were not confirmed for a year are dropped. The comparison runs against the persisted (model, memory size) signature and not against the previous discovery reply, because the reply objects do not survive a restart.
* "check & teach in HA senders" per FAM14: verifies the configured sender ids against the device memories and writes missing ones with `ensure_programmed` (bus locked, standard procedure of the EnOcean Device Manager)
* **Plug & play** (new module `plug_and_play.py`, general setting `plug_and_play`, off by default): detects a gateway which was plugged in, reads its bus and adds every device which can be identified without any doubt. Switched on with a checkbox in the configuration, and the same switch sits as a push button on the overview page ("Plug & Play on/off", plus "Detect now" and "Detect + re-read all buses"). See [docs/plug-and-play](docs/plug-and-play/readme.md).
  * **Gateway (serial)**: every serial port which is not used by one of our gateways is probed actively (ported from the `SerialPortDetector` of the EnOcean Device Manager): a FAM14 is recognized because only its adapter echoes back what is written to it, an ESP3 stick (USB300) and a FAM-USB because they answer a base id request. Those three are created including their config entry, so their entities exist a few seconds later. An **FGW14-USB cannot be proven** - the test matches every port which is reachable and does not echo - so it is only suggested with a "+ add" button and never created behind the back of the user.
  * **Gateway (network)**: LAN gateways which announce themselves via **mDNS** are picked up in every run (ported from the `LanServiceDetector` of the EnOcean Device Manager): `_bsc-sc-socket._tcp` with `SmartConn` in its name becomes a `lan` gateway, `_tcm515._tcp` with `EUL` an `eul_lan` gateway - both with the ip address and port from the announcement. A service states its own type and name, which is a positive identification, so those are created. The only exception is `Virtual-Network-Gateway-Adapter`: **this integration publishes it itself** for the EnOcean Device Manager, so creating a gateway for it would connect Home Assistant to itself - it is only suggested. A gateway which is already configured with that address (or host name) and port is skipped. Uses the Zeroconf instance of Home Assistant (now declared as a dependency in the manifest, the reverse bridge used it undeclared before). A gateway which does not announce itself still has to be added once by hand.
  * The detection runs **once a day** by default (`plug_and_play_interval: 1440`, plus once a minute after a restart) and can be set to anything between hourly and weekly, or to 0 for "only when the button is pressed". Probing opens every free serial port and a bus scan locks the bus, so a tighter interval buys nothing - a gateway is plugged in rarely, and for that moment there is the button.
  * A port whose usb descriptor is known but fits no Eltako/EnOcean gateway (Zigbee/Z-Wave sticks, ...) is not opened at all; a port without a descriptor is probed, because inside a container only the device nodes are passed through. A stick which another program holds open cannot be opened twice, so it is skipped by the probe itself.
  * **Bus**: a bus gateway gets its bus read once (discovery plus the complete memory of every device - the same paced scan as the button on the device page). Reading it locks the bus for minutes, therefore the periodic check skips a bus which was already scanned; re-reading is the explicit second button.
  * **Devices**: added are only those which are unambiguous - a bus position whose discovery reply names a model which maps to exactly one device class and which the device catalog knows (one device per channel of a multi channel device, sender ids `00-00-B0-<position>` like the EnOcean Device Manager uses), a sender which was found in the memory of a bus actuator (its key function names the EEP) and an address which sent a 4BS teach-in telegram (the telegram states the EEP). Everything else - position not identified, model shared by several device classes, EEP only guessed from the data bytes, actuator which needs a sender to be taught in - is listed as "needs a decision" with its reason and stays a manual step on the device page.
  * Detected devices are stored like devices created in the web ui, so **their attributes can be changed and they can be removed again**. Nothing is written into any device: the sender ids of added actuators still have to be taught in ("check & teach in HA senders").
  * The overview page draws the run as the flow it is: three tiles (gateway &rarr; bus &rarr; devices) with the result of each stage, the stage which is currently running highlighted and its arrow animated, an indeterminate progress bar with the current step, and the switch of the configuration as a real toggle. The report (new gateways, added devices, what needs a decision, warnings) is folded out below it and remembers which block the user opened - the page rebuilds itself every few seconds. Only the brand tokens are used, so a dark or custom Home Assistant theme keeps working; the stacked layout on a phone was verified with a real layout engine.
  * The report is published **while the run is still going**, so the stages fill up live instead of showing the numbers of the previous run. It can be polled with `eltako/plug_and_play/status` (with a machine readable `stage` next to the readable step); a run happens in the background because reading a bus takes minutes. A newly created transceiver or LAN gateway is no longer waited for - only a bus gateway, whose bus is read in the next step.
* **Gateways of the web ui can be edited** ("edit gateway" on their tile), until now they could only be created and removed. Name, type, serial port or host/port, base id, auto reconnect and message delay are changeable and are validated with the same schema as the yaml; description and connection are written back into the config entry and the gateway reconnects with the new settings. The id stays fixed - it is part of every entity id of that gateway. A gateway declared in `configuration.yaml` is not editable here (it wins over the ui anyway) and says so.
* Editing a device in the web ui dropped the settings the **form cannot show**: the schemas support more than the form offers (`cooling_mode` of a climate device, `voc_type_indexes` and `language` of a sensor), and the ui sends exactly the fields it rendered. Saving an imported or hand written device therefore silently lost them. Such a field is taken from the stored device now, while every field the form does offer still comes from the ui - so it can be cleared by emptying it.
* Adding many devices at once reloaded the gateway once **per device**: every write of the options of a config entry triggers a reload, which rebuilds the serial connection and all entities. With a config import (or a plug & play run) that meant dozens of reloads racing each other - and a device edited afterwards kept its old name until the next restart, because the new entities were rejected as duplicates of the ones a parallel reload had just registered. `device_config.async_add_ui_devices()` validates all devices first and writes them in one go; config import and plug & play use it, so a gateway is reloaded exactly once. An invalid device is reported and skipped instead of stopping the others.
* The base id of a gateway is queried from the hardware after it connects; for gateways created in the web ui the reported base id is stored automatically - no need to know it upfront (a wrong overwrite of the base id by the repeater-mode answer was fixed on the way)
* The statistics page shows the current state of every entity next to its entity id
* Arbitrary EnOcean telegrams can be sent from the web ui (button "Send telegram" on the live view)
  * either built from an EEP: the form offers every EEP of the library with its fields (A5-38-08 central command with the flat fields of its switching/dimming variants), sender id and gateway are selectable
  * or as raw ESP2 hex: 11 body bytes or the full 14 byte frame (checksum is validated)
  * the sent telegram appears in the live list right away (direction "out"); the live rendering pauses while the form is open, so nothing typed gets lost
  * new websocket commands `eltako/send_telegram` and `eltako/send_telegram_form` - complements the per-gateway `send_message` services
* If the configured serial port of a gateway does not exist (the kernel renumbers /dev/ttyUSB* on re-plugging), the stick is searched by its usb serial number and, as a fallback, by an unambiguous usb descriptor match - reception no longer dies silently after re-plugging
* General settings can be edited in the web ui (new module `general_settings.py`)
  * the section "Active configuration" on the about page is an editable form now, structured in the groups *General*, *Web UI*, *Telegram recording* and *Log levels of telegrams*
  * values changed there override `configuration.yaml` (opposite precedence to the device configuration - on purpose, otherwise a yaml value could never be changed from the ui), every override shows its origin and can be reset to the yaml/default value
  * changes are applied immediately: the telegram logger is re-created and the gateways are reloaded. No restart needed except for `enable_frontend`.
  * stored in the Home Assistant storage and validated with the same voluptuous schema as the yaml
* Log levels per telegram category (logger `eltako.telegrams`)
  * new settings `log_level_incoming`, `log_level_outgoing`, `log_level_unknown_devices`, `log_level_bus_messages`, `log_level_polling` and `log_level_decode_errors` with the values `off`, `debug`, `info`, `warning` (all `off` by default)
  * useful for troubleshooting: set unknown devices to `warning` to make a newly pressed button stand out, outgoing commands to `info` to check whether a command really goes onto the bus, decode errors to `warning` to find a wrong EEP
  * polling is logged without being buffered, so the flood of a FAM14 can be analysed without filling the ring buffer
  * the logger level is raised automatically so the messages are not dropped by the level of the `eltako` logger
* USB/serial port scan for gateways (new module `gateway_scan.py`)
  * button "Scan USB ports" on the overview page: shows every serial port, the usb descriptor behind it, which gateway uses it and a suggestion for the `device_type`
  * works inside a docker container as well: `/dev/serial/by-id` is created by udev and does not exist there, so the devices are globbed directly and the usb descriptor is read from sysfs. (The former `gateway.detect()` finds nothing in container setups.)
  * warns about configured gateways whose serial port does not exist right now
* Live telegram view: filter by gateway
* Send telegram form: the EEP dropdown shows the description next to the EEP number (`A5-38-08 - Central Command Gateway (central command - PREFERRED for lights and switches)`) and repeats it under the field for the selected EEP. Same source as the device form (`describe_eep`), so both dropdowns read identically.
* Device list: the row of a device flashes blue when one of its telegrams (or one of its sender) is received
* Long term activity per EnOcean address (new module `device_activity.py`)
  * counts telegrams per address and remembers first/last time seen, number of Home Assistant sessions, message types and average telegrams per day
  * persisted in the Home Assistant storage, so the information survives restarts (debounced writes, old entries are pruned after 180 days, at most 2000 addresses)
  * runs independently of the telegram logging: the information is needed exactly when something does not work
  * the device page shows per device how often it reported and when it was heard from the last time. Devices which never reported are highlighted (wrong address, wrong gateway or device does not exist) and can be filtered.
  * for actuators the activity of their sender address is used as fallback
  * new websocket commands `eltako/devices/activity` and `eltako/devices/activity_clear`
* Devices can now be created in the web ui in addition to `configuration.yaml` (new module `device_config.py`)
  * new page **Devices**: all devices of all gateways incl. their source (yaml/web ui), add/edit/remove for devices of the web ui
  * the form fields and EEP lists are derived from the voluptuous schemas of the integration, so the ui always offers exactly what is supported. Both sources are validated identically.
  * devices of the web ui are stored in the options of the config entry of their gateway. The gateway is reloaded automatically, so new devices appear without restarting Home Assistant.
  * devices declared in `configuration.yaml` always win and cannot be edited in the ui
  * unknown devices can be taken over with one click: the form opens prefilled with address and detected EEP
  * devices can be deleted in the Home Assistant device page now (`async_remove_config_entry_device`); devices of the yaml are protected
  * config entries unload their platforms properly now, which is the prerequisite for reloading without duplicated entities
* Multiple gateways on one bus and devices taught into several gateways are fully supported
  * telegrams arriving through more than one gateway are fine and all commands are idempotent - nothing breaks
  * bus devices (local 00-00-.. addresses) may be declared for more than one gateway: every declaration becomes its own working entity (the unique id contains the gateway id)
  * the radio is treated as one virtual bus with several gateways and repeaters attached to it: a wireless device declared for more than one gateway gets ONE entity (it receives through all gateways anyway), and every command is repeated with the sender of each taught-in gateway (`collect_additional_senders`) - a gateway only transmits senders of its own base id range, so each gateway needs its own sender variant. Before, the second declaration was dropped completely and its sender was lost.
  * the only collision still removed with a warning: the same device declared twice for the same gateway
  * the configuration import (.eodm / PCT14 export / yaml) imports **all** gateways of the file - also several on the same bus (identity: type + base id + name instead of the base id alone). Devices of gateways which already exist are merged: missing ones are added, existing ones stay untouched. Importing the same file twice changes nothing, an extended file adds exactly the new parts (`skipped_devices` in the result).
* **Exports of the Eltako PCT14 tool (.xml) can be imported** as well - next to `.eodm` projects of the EnOcean Device Manager and an `eltako:` yaml. The format is detected from the content, the file extension does not matter, and the preview before applying is the same for all three.
  * the `<rootdevice>` of the export (the FAM14 the pc tool was connected to) becomes the gateway with the base id and the description of the export
  * every bus device becomes one device **per channel** at its bus address; EEP, sender EEP and platform come from the central device catalog, the descriptions typed into PCT14 become the names ("FSR14-4x - Light Kitchen - Light 4"), and a channel without its own description keeps its number so no two devices are named alike. Sender ids follow the rule of the EnOcean Device Manager (`00-00-B0-<bus address>`), covers and climate devices get its defaults.
  * the senders **taught into** the actuators become devices too: radio pushbuttons and FTS14EM inputs (F6-02-01) and the sensors whose EEP the key function of the teach-in names - classified exactly like a bus scan does (`bus_members.classify_taught_in_sensor`). A switch taught into several actuators is imported once, the virtual senders of Home Assistant itself (`00-00-B*`) are skipped, and a sender whose address is a bus position of the export is the actuator itself (central function, feedback) and no device of its own.
  * skipped and reported in the preview: bus devices whose type the catalog does not know (no EEP can be guessed) and further bus gateways of the same rack - a PCT14 export describes one bus, so an FGW14-USB or FTD14 next to the FAM14 would only duplicate its gateway
  * the xml is parsed with `defusedxml` when Home Assistant provides it, otherwise with the standard library; a broken file is reported as an invalid file instead of raising
* Central device catalog (new module `device_catalog.py`, ported from the complete EEP_MAPPING of the EnOcean Device Manager)
  * the device form of the web ui offers the known devices as templates - selecting e.g. "FSR14_4x - Relay (4 channels)" prefills device EEP and sender EEP, shows the PCT14 teach-in position and how many addresses the device occupies. All values stay editable.
  * one single source: the device page (identified bus devices) and the device form read the same catalog, served through the form websocket - the frontend hardcodes no device knowledge
  * templates are filtered against the EEPs the platform schema supports, so the form can never offer a combination the validation would reject
* The area of a device is picked from a dropdown with all areas Home Assistant knows (rooms/areas of the area registry). Free text stays possible - a new area is created automatically. The list is injected by the backend into the form descriptor.
* Time based rotation of the telegram log file (`telegram_log_rotate_days`, default 7)
  * the file rotates when its oldest telegram is older than the limit **or** when the size limit is reached - whichever comes first. The rotated files then align with time ranges ("last week" = `<name>.1`).
  * the age survives restarts: it is read back from the first record of the existing file
* Telegrams can be exported into a timeseries database ([docs](docs/telegram-analysis/readme.md))
  * new settings `timeseries_enabled`, `timeseries_url`, `timeseries_token`, `timeseries_org`, `timeseries_bucket`, `timeseries_measurement` - editable in the web ui as well
  * every telegram is written into InfluxDB (2.x or 1.8+) with its correlated meta data as tags (device name, EEP, area, platform, direction, known/unknown) and the decoded EEP values as fields - built for analysing tests, calibrations and long term behaviour with Grafana
  * batched line protocol from an own worker thread, no client library, never blocks the bus
  * new service `eltako.export_telegram_log_to_timeseries`: backfill of the complete history from the rotating jsonl log files
  * the statistics page shows recording, rotation and export state (written/exported counters, errors)
* Web ui: app header with the standard Home Assistant menu button above the navigation - on a smartphone the sidebar could not be opened from inside the panel before, there was no way to navigate back
* A serial gateway can be used from the dev container although docker on macOS/Windows has no usb access: `dev/share-serial.sh` publishes the port with socat and the gateway is configured as `lan-gw-esp2`. Two bugs had to be fixed for that, both verified with a real FAM-USB - it answers the base id request through the bridge and forwards its radio telegrams into the container:
  * an ESP2 gateway over tcp was opened with the bare host name. `RS485SerialInterfaceV2` hands it to pyserial, which needs the url `socket://<host>:<port>` - nothing built that url, so `lan-gw-esp2` could not connect at all.
  * its baud rate is `-1` (meaningless for tcp), which pyserial rejects with "Not a valid baudrate" even for a socket url - the reader thread crashed and retried forever without a usable message.
  * `lan-gw-esp2` queries its base id now as well, so it does not have to be entered by hand
  * on a LINUX host the device is passed through instead (`devices:` in docker-compose.yml, documented there)
* Documentation for the standalone runtime: [docs/standalone](docs/standalone/readme.md) - why it exists next to Home Assistant (comparison table), install and start, configuration, the defaults it seeds, the CLI, the device tests incl. the actuator/sender arrays, importing an eo_man project, platform differences and what the shim does *not* provide.
* Documentation for the dev container: [docs/dev-container](docs/dev-container/readme.md) - quick start, what is seeded, which change needs which restart, using a real USB gateway per host platform, the Grafana dashboards and the host requirements.
* Dev container ([dev/](dev/README.md)): `cd dev && ./start.sh` starts a ready-to-use Home Assistant - onboarding done, admin user seeded (admin/admin), the Eltako config entry pre-provisioned, `ha.yaml` included as package (25 example devices over all platforms) and 24 h of example telegram history. `./start.sh analytics` adds InfluxDB + Grafana (datasource preconfigured) for the timeseries export. The integration code is mounted live from the repository. Tests keep the seed in sync with the integration (`tests/test_dev_container.py`).
* new test which statically detects undefined names (missing imports) in all modules of the integration
* Sensor values were written to the read-only property `native_value` instead of `_attr_native_value` in five places (`sensor.py`, `datetime.py`). Home Assistant entities expose their value as a property **without setter**, so the assignment raised `AttributeError: property 'native_value' has no setter` inside the event listeners - the affected sensors never updated. Two of them additionally swallowed it with `except AttributeError: pass` ("Home Assistant not ready yet"), which is why it stayed invisible; they log a warning now. Affected: last message received, received messages per session, base id of a gateway, the event driven info fields (e.g. repeater mode) and the datetime entity. A new static test (`tests/test_readonly_entity_properties.py`) walks the AST of every module and reports such an assignment with its line number - verified by re-introducing the original bug.
* The **Tests page was never shown in Home Assistant** although the setting `enable_test_page` said it was on: the page was marked `standaloneOnly` and got filtered out of the navigation, and its backend (`device_tests.py`) was registered by the standalone runtime only. The module has no dependency on that runtime - it drives the gateways of whichever runtime is running - so it moved into the integration (`custom_components/eltako/device_tests.py`) and registers its websocket commands there. The burst test and the cover travel time measurement are now available in Home Assistant as well, and the setting does what it says. Four tests guard it.
* New **[architecture documentation for developers](docs/architecture/readme.md)**: how the integration is built, in the order someone new needs it - the overall shape, what happens during startup and why the order of `async_setup()` is load-bearing, and the path a telegram takes from the wire to an entity (with mermaid diagrams for both). Then a reference part: every module with what it owns, the four `Store`s, the websocket api, the frontend structure and its "no domain knowledge in the frontend" rule, the standalone runtime and why the two test suites must not share a pytest process. Ends with recipes (adding a device type, a setting, a websocket command), the traps that cost time (the serial reader thread, the FAM14 base id lock, `_attr_*` versus read-only properties, timeseries timestamps) and a "where to look first" table.
  17 tests keep it from rotting: every module, symbol, storage key, platform, page and link it names is checked against the code, the mermaid blocks are checked for the html-like placeholders that silently break rendering, and the documented startup order is compared with the actual order of the calls in `async_setup()`.
* The **burst test** only offers gateways on the RS485 bus now. It sends with the fixed addresses `FF-00-00-01..` of the EnOcean Device Manager, which are not derived from any base id - and a wireless transceiver only transmits telegrams whose sender address lies inside its own base id range (base id .. base id + 127, valid base ids start at `FF-80-00-00`). A FAM-USB or USB300 therefore dropped them silently, and the test reported every single telegram as missing without a hint at the cause. The web ui leaves those gateways out of both dropdowns, explains what is missing when fewer than two wired ones are configured, and the backend refuses the run with the reason instead of producing a misleading failure. Whether a gateway counts as wired comes from the existing `GatewayDeviceType.is_bus_gateway()` - no second definition. The restriction belongs to this one test: it is declared by the test descriptor (`wired_gateways_only`), and the cover test keeps seeing every gateway, because its actuators may well be taught into a wireless one. 16 tests. The two-gateway fixture of the standalone tests had a FAM-USB as the receiving gateway - a constellation no real burst test could have used - and is a bus gateway now.
* **New page "Settings"**: the general settings moved out of the *About* page onto one of their own (`#/settings`). They were a section at the bottom of a page which is otherwise pure information - editing the live configuration deserves its own place.
* **New page "Help"** (`#/help`): the documentation and tutorials of the project, plus complete tables of everything supported - devices, EEP profiles, gateways and platforms. Nothing on it is a written-down list; the backend (`help_catalog.py`) compiles it from the sources which already exist:
  * devices from `DEVICE_CATALOG`, with the profiles of a device that speaks several EEPs collected into one row,
  * EEPs from the profile registry of `eltakobus`, described by the docstring of the profile class and cross-referenced with the platforms that accept them and the devices that use them,
  * gateways from `GatewayDeviceType` (its aliases collapse to one entry each) plus their catalog entry,
  * platforms and their EEPs by walking the voluptuous schemas. Reading a class attribute would have missed `binary_sensor` and `climate`, which keep their list elsewhere - the `vol.In` behind the `eep` key is unambiguous,
  * documentation from the `docs/` directory, each entry titled by the heading of its readme.
  A tutorial, a device or an EEP added to the project therefore appears on the page by itself. Since HACS installs `custom_components/eltako/` only and there is no `docs/` to scan there, the scan result is generated into `docs_index.json` which ships with the integration - a test compares it against a fresh scan so it cannot go stale (`python -m custom_components.eltako.help_catalog` regenerates it). 32 tests.
* The setting **"Web ui enabled"** was a trapdoor: switching it off in the web ui removed the page the switch is on, and there was no way back. The yaml cannot undo it - an override stored by the web ui wins over `configuration.yaml`, so `enable_frontend: true` has no effect against it; recovery meant deleting `.storage/eltako_general_settings` by hand. Its help text claimed the opposite.
  The field is still shown with its current value (greyed out, with a lock next to the label) but cannot be changed here anymore - `configuration.yaml` remains the place for it, where switching it back on works. Both ways into the trap are closed in the backend, not only in the ui: writing the override is dropped, and so is *resetting* it - the default of the setting is `False`, so "Reset all overrides" would have disabled the web ui just as effectively. Saving the form still works: the page sends every field back, and the locked one is skipped instead of rejecting the whole call. 17 tests; verified against the running dev container.
  `renderFields()` supports disabled fields for every input type now, driven by a `locked` flag on the setting descriptor - so a second setting can be protected the same way without touching the frontend.
* Web ui in the Eltako colours:
  * The **Eltako logo** sits at the right of the white bar and is noticeably larger (52 px, 40 px on a phone). The white bar is the header *and* the navigation below it, so the logo lives next to both and is centred over their combined height - inside the header it would sit in the upper half of the white area. Measured with a real layout engine at 340, 600, 900 and 1400 px: vertical offset 0 everywhere, 16 px to the right edge, and neither the title nor the navigation runs into it (the title truncates with an ellipsis instead).
  * **Lighter and bluer**, closer to eltako.com. Everything neutral - page background, borders, hover, table striping, code blocks - carries a light wash of the brand blue instead of plain grey (`#F0F4F7`, `#F0F6FA`, `#DEEBF5`, the same family as eltako.com's `#F8F9FA`/`#E9ECEF`/`#CCE5FF`). The wash is mixed into the *theme* colour with `color-mix`, so a custom or dark Home Assistant theme keeps working and only gains a blue cast.
  * The ui no longer reads as "orange": the strong amber of the Home Assistant badges marked plain counters as well, and a whole table of unknown devices sat in an amber wash. The counters next to the navigation entries are brand blue now and the unknown rows carry the blue wash - the amber is left for genuine warnings and goes through a single `--eltako-warn` token. All resulting contrasts are WCAG AA (6.1 for the blue, 7.6 for the amber).
  * 17 tests pin the branding: the logo's alignment and size, the palette tokens, and that no plain grey or a second hardcoded blue creeps back in. the accent of the whole panel (heading, icons, active navigation entry, links, primary buttons, sort indicators, highlighted rows) is **#0064AF** - taken from the official logo and confirmed as the dominant colour of eltako.com. On a dark theme it switches to a lightened variant, because the brand blue only reaches a contrast of 2.79:1 on the dark Home Assistant background while the lighter one reaches 5.89:1 (measured, AA needs 4.5).
* Web ui: the **official Eltako logo** sits at the right end of the header. `img/eltako-logo.svg` is Eltako's own vector file (from the theme of eltako.com), so it stays sharp at any size; the png next to it is the raster version Home Assistant shows for this integration in its settings and is used if the svg is missing.
* Web ui: the panel is called **ELTAKO - EnOcean** now - in the Home Assistant sidebar, as the heading of the web ui and as the browser tab of the standalone runtime. 'EnOcean' used to be a placeholder in the version field which vanished as soon as the version was loaded. The heading is bigger (1.05 -> 1.35 rem) and has real space to the navigation below it, and the **Eltako logo** sits at the right end of the header.
* Web ui: 'Possible devices' groups the models per EEP (`eep: model model ...`) in an aligned grid instead of one flat row of chips; at most six models per profile, the rest as '+N more' with the full list in the tooltip.
* Web ui: the periodic refresh keeps the scroll positions. Replacing the content clamped the vertical scroll of the page to the top and reset the horizontal scroll of every table - on pages which refresh every few seconds (device list 15 s, live telegrams on every telegram) a wide table could not be read. The panel captures and restores the scroll offset of the page, of every table/log/side panel and of the navigation (which scrolls horizontally on a smartphone). A deliberate jump still wins: opening the device form scrolls to it as before.
* Web ui changes were invisible until a hard reload: the frontend folder was served with `cache_headers=False`, which only means "do not add long lived cache headers" - the response carried `ETag`/`Last-Modified` only, and browsers cache ES modules heuristically from `Last-Modified` **without** revalidating. The integration serves the folder through its own view now (`EltakoFrontendView`) which sends `Cache-Control: no-cache, must-revalidate`; the standalone server does the same with a middleware. Requests are contained inside the folder (an escaping path is rejected).
* Device list: a device is everything which exists on the installation - the cards count **gateways plus sensors/actuators** and show the split, with an own card for the gateways and one for the addresses which are not configured yet. The radio block is named after what it contains (gateways / sensors / actuators) instead of "Radio devices".
* The separate page 'Unknown devices' is gone - its addresses are the last block of the device page (incl. its 'copy yaml' per address and 'copy all as yaml'), so everything which exists on the bus and in the air is in one place. A new test walks the import graph of the panel, because a missing module aborts the whole module graph instead of breaking one page.
* Unknown addresses get **EEP and device candidates** derived from their telegrams (new module `telegram_suggestions.py`), shown as two own columns of the block:
  * a 4BS teach-in telegram states the EEP - that is `confirmed`, not a guess
  * the message type is the hard limit (an RPS telegram never carries an A5 profile)
  * the **data bytes decide** between the remaining profiles: every candidate is decoded and its values are range checked, so a profile which yields a humidity of 300% drops out
  * a local bus address below 0x1500 identifies an FTS14EM input
  * the device suggestions are the models of the central device catalog which speak that EEP; profiles for which the catalog knows no device rank lower
* All of that logic lives in the **backend**: the statistics deliver a ready `unknown_devices` list (filtered, sorted, with candidates, the best suggestion and a pastable `configuration.yaml` snippet). The frontend module which used to guess the EEP from the message type in javascript is gone - the web ui only renders backend fields now, so the suggestions cannot drift away from the schemas and the catalog. Reusable by services and the CLI.
* Device list: addresses which send telegrams but are not configured yet are shown as their own block **Unknown devices** at the end of the hierarchy - everything which exists on the bus and in the air is visible in one place, with "+ add device" opening the form prefilled. Senders which were found in the memory of a bus actuator are not repeated there: they are listed at their bus position, where the key function reveals the EEP reliably instead of guessing it from the message type. The EEP suggestion is shared with the 'Unknown devices' page (new module `frontend/lib/unknown_devices.js`), so the prefilled form is identical wherever it is opened.
* Cover travel time test: the actuator addresses and the sender addresses can be passed as two arrays (`--covers` / `--senders`, or the two fields on the **Tests** page), used pairwise by position. Before, only configured covers could be tested - now a fresh FSB actuator can be calibrated before it is configured, an explicit sender overrides the configured one, and a single sender can be used for several channels. The result reports both arrays back.
* Documentation for the analysis: [docs/grafana](docs/grafana/readme.md) - which tags and fields land in the database (incl. the raw data bytes), which dashboard answers which question, how to see incoming telegrams (time range + auto refresh - Grafana is not a live view) and two query patterns for own questions.
* The raw ESP2 frame (`raw`) is exported to InfluxDB as well, and the *Product and test inspector* can filter by **data payload** - so the telegrams of one product can be analysed down to the single byte.
* Grafana: unconfigured devices are shown on the *Telegram overview* next to the configured ones - on a fresh installation they are usually the majority (576 of 683 telegrams in the test setup). New: *Configured vs. unconfigured addresses over time* and *Most active unconfigured addresses* incl. their last data payload. In *Telegrams per EEP* they appear as **not configured** instead of a nameless slice holding most of the traffic. The address column of both unconfigured tables links into the *Product and test inspector* with that address preselected, so one click shows all telegrams of a device.
  * fixed on the way: every chart labelled by device name showed **nameless bars** for unconfigured devices. They have no `device_name` tag, and `group()` turns that into an empty string - so `exists r.device_name` was true and the label stayed empty instead of falling back to the address.
* Grafana: five dashboards now ship **with the integration** (`custom_components/eltako/grafana/dashboards/`) instead of only with the dev container, so they are versioned together with the data model they query. New next to *Telegram overview* and *Device analysis*:
  * **Telegrams per device** - per device over time, totals, first/last telegram and the average interval between two telegrams (a battery sensor with a long interval may be empty, a very short one floods the bus)
  * **Errors and bus health** - telegrams whose configured EEP cannot decode them, unconfigured addresses, repeated telegrams and the signal strength per device
  * **Product and test inspector** - search for a device, product or test run (free text over address and name, plus device/address/EEP pickers) and look at its **raw telegrams**: direction, message type, data and status bytes, the round trip of command and answer, and which distinct payloads a product sent
* The dashboards can be **synced from the web ui**: the button *Sync dashboards* in the live telegram view pushes them through the Grafana HTTP API (new module `grafana_sync.py`, new setting `grafana_token`). It creates the folder *Eltako*, points every panel at the InfluxDB datasource which actually exists in that Grafana (by uid, falling back to the first InfluxDB datasource) and reports per dashboard what happened. The dev container mounts the very same files into its provisioning path, so a dashboard cannot drift between the two ways. Verified against Grafana 13.
* Telegrams whose **configured EEP cannot decode them** are marked per telegram now (`decode_error`) instead of only being counted globally - that is the basis of the error dashboard and makes a wrong EEP findable in the log file. The signal strength (`rssi_dbm`) is exported to InfluxDB as well.
* Two tests keep the dashboards honest: every field a panel queries must either be exported by `timeseries.py` or be a decodable property of an EEP class of the library, and every tag it filters on must be exported - a typo like `rssi_dbmm` fails with the panel name instead of showing an empty graph.
* Standalone runtime: telegram recording and the Grafana analysis are set up out of the box
  * on the **first** start of a config folder the standalone runtime seeds its own defaults (new module `eltako_standalone/defaults.py`): recording on, telegrams persisted into `enocean_telegrams.jsonl`, InfluxDB export on (`http://localhost:8086`, bucket `eltako`) and the Grafana url. Home Assistant keeps its opt-in defaults - the standalone runtime is a test/analysis tool, so the opposite makes sense there.
  * the defaults are seeded, not enforced: everything changed afterwards in the web ui is kept, and a value set explicitly in `configuration.yaml` is never seeded so it cannot be shadowed. Delete `.storage/eltako_general_settings` to get them back.
  * new setting `grafana_url`: the live telegram view shows a **Grafana** button linking to the dashboards as soon as the export is on
  * two Grafana dashboards are provisioned automatically (`dev/grafana/provisioning/dashboards/eltako/`): *Telegram overview* (rate by direction/gateway, most active addresses, distribution over message type and EEP, unconfigured addresses) and *Device analysis* (any decoded EEP value over time, switching states, silent devices, telegrams per hour and area, average repeater level). `dev/start-analytics.sh` starts InfluxDB + Grafana without Home Assistant.
  * **telegrams were lost in the InfluxDB export**: a point is identified by measurement + tags + timestamp, and the record timestamp had only millisecond resolution - a burst of telegrams with the same address and type (repeaters, a command repeated through several gateways) overwrote each other. Verified against a real InfluxDB: 20 telegrams became 2 points. Records carry microseconds now and the sequence number fills the nanoseconds below it, which keeps every telegram its own point (time error below one microsecond).
* FAM-USB fixed (found with real hardware on macOS)
  * the base id of a **FAM-USB** was never queried: it was excluded together with the FGW14-USB and the reverse network bridge, although it is a transceiver with its own base id and answers the normal ESP2 request (ORG 0x58). Since the gateway wizard offers `00-00-00-00` as base id, a FAM-USB created there stayed unusable - no sender and no device address of that gateway validated. It reports its base id automatically now, like a FAM14 and the ESP3 gateways.
  * `is_bus_gateway()` classified the FAM-USB as bus gateway: `EltakoFAMUSB` has the same enum value as `GatewayEltakoFAMUSB` and is therefore an *alias* of it, so the FAM-USB was a bus gateway and a transceiver at the same time - it was offered for the RS485 memory scan and labelled 'bus gateway (RS485)' in the wizard.
  * two `LOGGER.debug` calls in the gateway setup were missing their argument (`[Id: %d]` with only one value) and produced a logging error instead of the message on every start
  * the port scan explains the dual port of the FAM-USB (it registers as 'EnOcean Programmer' with if00/if01 - only if01 carries the telegrams) and suggests `fam-usb` before `enocean-usb300`, because the two need different baud rates (9600 vs. 57600)
* Bugfixes found on a live installation
  * the device page showed every channel of a multi channel device (e.g. the four positions of an FSR14-4x) as its own device instead of grouping them under their physical device. The whole bus member registry was only fed from the telegram logger, which is disabled by default (`log_enocean_telegrams`) - so `device_class` and `size` of the discovery replies, the only source of the channel layout, never arrived. The gateway feeds the registry directly now (`bus_members.note_telegram`), independently of the recording setting.
  * covers were not added at all (`Error adding entity cover...`, entity stayed unavailable) when the restored state had no `current_position` attribute ([#141](https://github.com/grimmpp/home-assistant-eltako/pull/141), thanks to [@stixif](https://github.com/stixif)). Restoring a state can no longer prevent an entity from being registered - it is now caught centrally in `device.py` and logged as a warning. A cover state which cannot be interpreted is reported with a warning instead of being ignored silently.
  * priority selection of climate devices got an entity id of the `climate` domain although it belongs to the `select` platform (collided with the climate entity of the same device, would break in HA 2027.5)
  * gateway entities without description key produced an invalid entity id ending with `_` (e.g. `select.eltako_gw_0_`). The entity id is sanitized now, the unique id (identity in the entity registry) stays unchanged.
  * devices which are declared for more than one gateway created entities with duplicated unique ids which Home Assistant rejected with `Platform eltako does not generate unique IDs`. Duplicates are now dropped deliberately (first declaration wins) and reported with a clear warning naming the address and the gateways.
  * the error paths of `async_setup_entry` returned `None` instead of `False`, so a handled configuration problem (missing gateway description, missing base id, missing serial path, no matching yaml section) ended up in the log as `eltako.async_setup_entry did not return boolean` instead of the readable warning of the integration ([#142](https://github.com/grimmpp/home-assistant-eltako/pull/142), thanks to [@stixif](https://github.com/stixif)). Three of those warnings printed a literal `{LOG_PREFIX}` because the f-string prefix was missing, and the wrong-domain warning mixed `%s` placeholders into an f-string, which made the log call fail. A new static test (`tests/test_setup_entry_return_values.py`) keeps the callbacks returning a bool.
* frontend/web ui is now part of the integration ([docs](docs/web-ui/readme.md))
  * removed dependency to the separate package `home_assistant_eltako_frontend`
  * frontend code (plain javascript modules, no build step) lives in `custom_components/eltako/frontend`, backend code stays in the python modules
  * panel with sub pages: overview (gateways, devices, entities), live telegrams, device statistics, unknown devices and about
  * `general_settings` cleaned up: `enable_frontend` is the only option for the web ui. Deprecated and ignored: `enable-frontend` (old name, still enables the frontend), `frontend-dev-url`, `enable_telegram_web_ui`
  * new websocket command `eltako/integration_info`
* added EnOcean telegram logging and analysis ([docs](docs/telegram-analysis/readme.md)) in own module `enocean_logger.py`
  * new general settings: `log_enocean_telegrams`, `telegram_log_filename`, `telegram_log_format` (jsonl/csv), `telegram_log_max_file_size_mb`, `telegram_log_backup_count`, `telegram_log_include_polling`, `telegram_log_decode_eep`, `telegram_log_buffer_size`
  * telegrams are recorded with EEP, decoded values, device name, area and references to the Home Assistant entities
  * rotating log file (JSON lines or CSV) written in a separate thread
  * per device statistics (counts, intervals, message types, first/last seen) and detection of devices which are not configured yet
  * live view, device statistics and detection of unconfigured devices are available in the web ui (see above)
  * new service `eltako.clear_telegram_log` and websocket api `eltako/telegram_log/*`

* The about page of the web ui lists the **features of the integration**: 33 entries in six areas (gateways and connection, devices and entities, insight into the RS485 bus, telegram analysis, automations, operation and development). Each entry links to its documentation, and features which depend on a general setting show whether they are switched on in this installation. Two tests keep the list honest: every documentation link has to point at an existing file and every referenced setting has to exist.
* Two new **device tests**, in the web ui and on the command line ([docs](docs/device-tests/readme.md)). Every test of the page is available as `python -m eltako_standalone devicetest <test>` - the page and the CLI call the same runners, `devicetest list` prints what exists, and the exit code says whether the test passed (0), failed (1) or could not start (2).
  * **Configuration check** (`config`, new module `config_check.py`) - the only test which sends nothing and the one to run first: it checks the configuration against everything the integration already knows. Address class against the gateway type (a local bus address cannot be reached by a wireless transceiver), a missing sender, a sender outside the base id range of its gateway (those telegrams are dropped **silently** - the most invisible mistake there is), duplicate addresses, a shared sender, the model which actually answered at that bus position against the configured EEP, whether the sender of Home Assistant is in the memory image of the actuator, whether the device was ever heard from, and covers without travel times. Every finding has a severity (error/warning/hint) and a sentence that says what to do; hints alone still count as success. On the command line with `--severity`, `--gateway` and `--json` for scripts.
  * **Actuator / teach-in test** (`actuator`) - the answer to "Home Assistant sends but nothing happens": it switches every selected switch or light with the sender of the configuration and waits for the status telegram of the actuator. An Eltako actuator only answers a command whose sender is taught into it, so an answer proves the whole chain (configuration, gateway, bus/radio, teach-in) and the round trip time comes along, which shows an overloaded bus. The telegrams are byte for byte the ones `light.py`/`switch.py` send - a test with its own encoding would prove something the integration never does. Devices without a sender are listed as not testable instead of failing the run.
  * Both tests read the devices of **configuration.yaml and of the web ui** (new `device_config.get_devices_of_gateway`). The cover test did the same thing wrong before: it only saw the yaml, so a cover created in the web ui was invisible to it.
  * Fixed on the way: `--command` of the actuator test overwrote `args.command` of argparse, which is the top level subcommand - the CLI would have stopped dispatching `devicetest` at all. Caught by the new CLI test.
* The **Tests page** got the look of the rest of the web ui: every test sits in a card with the same form grid as the settings (labels, help texts under the fields), the state is summarized in cards on top (connected gateways, running test, last result), and a running test is marked with a pulsing indicator while both start buttons are disabled - which they now also *look* like. The results are readable instead of raw: the burst test shows telegrams sent/received/lost with the loss rate, the cover test shows the measured travel times next to the configured `time_opens`/`time_closes` with a concrete suggestion, and every row carries an OK/problem badge. The log has a copy button, its colours follow the theme (a hardcoded green was unreadable on a dark theme), and the page tells you when the burst test cannot run because only one gateway is connected. New tests pin the contract between page and backend (websocket commands, parameter and result field names) and, for every page of the web ui, that no handler looks up an element id which is never rendered - the mistake a build-less frontend cannot report.
* Web ui fixes
  * The link "Eltako series 14" of the help page pointed at `eltako.com/en/product/professional-standard-en/`, which answers with 404 since the product pages moved into the catalog (`/en/catalog/categories/<id>`). It links to the catalog category "Professional Smart Home" now, which holds the series 14. All other external links of the help page were checked and still answer with 200.
  * Chips (the small rounded tags for EEPs, platforms and device models) overlapped each other as soon as they wrapped onto a second line, and a device name with a hyphen was broken in the middle - visible in the "Devices" column of the EEP table on the help page. They are `inline-block` with `white-space: nowrap` now: an inline element does not grow the line box by its vertical padding, which is what made the borders collide.
* Bugfixes for reported issues
  * Restoring the last value of a counter (`state_class: total_increasing`, e.g. an electricity meter) failed with `ValueError: invalid literal for int() with base 10: '36231.4'` and Home Assistant dropped the entity. States are strings and can contain decimals, so they are parsed as number now and only narrowed to int if there is no fractional part (`config_helpers.parse_number_state`). Applies to `measurement`, `total` and `total_increasing` alike. ([#175](https://github.com/grimmpp/home-assistant-eltako/issues/175))
  * No more false `Maybe have wrong device id configured!` warnings for gateway and metadata entities. Gateway diagnostics, info fields, event listeners and the repeater mode use the base id or `00-00-00-00` by design, but were validated as actuators (`_attr_is_actuator_entity = False` marks them now). In return the **sender ids of actuators are really validated**: light/switch/cover/climate store it as `_sender_id`, which the check never looked at - a sender id outside the base id range of a transceiver (the gateway silently drops those telegrams) went unnoticed. The warnings name the offending address, the gateway type and the expected format, and the sender id is not validated while the base id of the gateway is still unknown. ([#203](https://github.com/grimmpp/home-assistant-eltako/issues/203))
  * The `gateway_<id>_send_message` service accepts the sender address as `id`, `sender_id`, `sender` or `address` and as string (`FF-A7-96-82`) or number (`0xFFA79682`). Only `id` was read before, so the natural guess `sender_id` ended in `No valid sender id defined. (Given sender id: None)` and nothing was sent. A sender id outside the base id range of the gateway is reported as warning now (usual cause of "nothing happens"), a wrong eep no longer produces a misleading message about the sender id, and values which do not fit the eep are reported instead of crashing the service call. ([#194](https://github.com/grimmpp/home-assistant-eltako/issues/194))
  * Tilting slats does not block Home Assistant anymore: the wait between the move and the stop telegram used `time.sleep()` in a worker thread (up to 25 s per call) and crashed with a `TypeError` if the tilt position was unknown after a restart. It is `async_set_cover_tilt_position` with `asyncio.sleep()` now, and an unknown position is taken from the end position of the requested direction.
  * Covers: the runtime of a full travel (`time_opens`/`time_closes` + 1 s) is capped at 255, the maximum the telegram can carry - with a configured runtime of 255 s encoding the telegram failed. Setting an intermediate position while the position is unknown is rejected with a clear warning instead of a `TypeError`; 0 and 100 still work and recalibrate the cover. ([#103](https://github.com/grimmpp/home-assistant-eltako/issues/103))

TODO: improve performance of controlling groups. (send only one group telegram instead of many individual commands)

## Version 1.5.9
* Replaced deprecated log function warn through warning
* Fixed deprecation warning for async_forward_entry_setup

## Version 1.5.8
* Fixed dependency incompatibility with HA 2024.9

## Version 1.5.7
* Tested new devices: FB55EB, FWZ12
* Added EEP F6-01-01 and tested FMH1W

## Version 1.5.6 Added EEP A5-10-03 for current and target temperature
* Only for sensors available

## Version 1.5.5 Added message-delay for GWs as config parameter
* Added argument `message_delay` to config distance of bulk messages being translated in the gateway so that buffer overflows can be prevented.

## Version 1.5.4 Cover motion fixed
* changed min movement time from 0 to 1 so that covers won't move completely up or down.

## Version 1.5.3 Added auto-reconnect for GWs as config parameter
* Added argument `auto_reconnect` to disable auto-reconnect for all Gateways

## Version 1.5.2 BugFix for LAN Gateway Connection 
* Added argument port for LAN Gateway. Default port = 5100

## Version 1.5.1 Added into HACS list
* Added Eltako Intgration into list of HACS

## Version 1.5 MGW LAN Support
* Added support for [MGW Gateway](https://www.piotek.de/PioTek-MGW-POE) (ESP3 over LAN)

## Version 1.4.4 
* Thread sync clean up
* Lazy loading for ESP3 libs to prevent dependency issues

## Version 1.4.3 Compatibility to HA 2024.5
* 🐞 Incompatibility with HA 2024.5 fixed. (Cleaned up event loop synchronization)

## Version 1.4.2 Added EEPs A5-30-01 and A5-30-03
* Added EEPs (A5-30-01 preferred) for digital input which is used in water sensor (FSM60B)

## Version 1.4.1 Support for sending arbitrary messages
* Added Service for sending arbitrary EnOcean (ESP2) messages. Intended to be used in conjunction with [Home Assistant Automations](https://www.home-assistant.io/getting-started/automation/).
* 🐞 Fix for TargetTemperatureSensor (EEP: A5-10-06 and A5-10-12)
* 🐞 Fix for unknown cover positions and intermediate state + unit-tests added.
* Unit-Tests added and improved for EEP A5-04-01, A5-04-02, A5-10-06, A5-10-12, A5-13-01, and F6-10-00.
* EEP A5-04-03 added for Eltako FFT60 (temperature and humidity)
* EEP A5-06-01 added for light sensor (currently twilight and daylight are combined in one illumination sensor/entity)
* Bug fixes in EEPs (in [eltako14bus library](https://github.com/grimmpp/eltako14bus))

## Version 1.4.0 ESP3 Support (USB300)
* Docs about gateway usage added.
* Added EEPs F6-02-01 and F6-02-02 as sender EEP for lights so that regular switch commands can be sent from Home Assistant.
* &#x26A0; Changed default behavior of switches and lights to 'direct pushbutton top on' and 'left rocker' for sender EEP F6-02-01/-02
* Logging prettified.
* Added library for ESP3 (USB300 Support) => [esp2_gateway_adapter](https://github.com/grimmpp/esp2_gateway_adapter)
* Better support for Teach-In Button

## Version 1.3.8 Fixes and Smaller Improvements
* Fixed window handle F6-10-00 in binary sensor
* Added better tests for binary sensors
* Fixed covers which behaved differently after introducing recovery state feature.
* Added additional values (battery voltage, illumination, temperature) for A5-08-01 as sensor
* Occupancy Sensor of A5-08-01 added as binary sensor
* Improved ESP3 adapter for USB300 support. Sending telegrams works now but actuators are not accepting commands for e.g. lights - EEP: A5-38-08 😥
* Teach-In buttons for lights, covers, and climate are available.
* Static 'Event Id' of switches (EEP: F6-02-01 and F6-02-02) is displayed on entity page.
* Docs about how to use logging added.
* Updated docs about how to trigger automations with wall-mounted switches.

## Version 1.3.7 Restore Device States after HA Restart
* Trial to remove import warnings 
  Reported Issue: https://github.com/grimmpp/home-assistant-eltako/issues/61
* &#x1F41E; Removed entity_id bug from GatewayConnectionState &#x1F41E; => Requires removing and adding gateway again ❗
* Added state cache of device entities. When restarting HA entities like temperature sensors will show previous state/value after restart. 
  Reported Feature: https://github.com/grimmpp/home-assistant-eltako/issues/63

## Version 1.3.6 Dependencies fixed for 1.3.5
* &#x1F41E; Wrong dependency in manifest &#x1F41E; 

## Version 1.3.5 Prevent Message overflow for FGW14-USB
* Added info field for which button of a wall-mounted switch was pushed down
* Added static info filed for device id 
* Fixes for ESP3 to ESP2 messages converter (Still not stable)
* Message delay added to eltako14bus so that buffer overflow in FGW14-USB gets prevented. (When sending many messages, messages get lot.)

## Version 1.3.4 Improved FTS14EM and Gateway Support
*  &#x1F41E; ESP3 Serial Communicator bug fix  &#x1F41E; 
*  Support for FTS14EM sending switches (EEP: F6-02-01, F6-02-02) and contacts (EEP: D5-00-01) telegram. (There are different FTS14EM versions sending different message types. Depending on that you need to choose the correct EEP)
*  Added sender_eep A5-38-08 support for swtiches
*  Filter for EltakoPoll messages inserted so that those messages won't span the whole Home Assistant bus.
*  Gateway reconnect button added.
*  Info fields added for Gateway (Id, Base Id, Serialo Port Path, Connected State, Last Received Message Timestamp, Received Message Count)

## Version 1.3.3 Added Temp and Humidity (EEP A5-04-01) and Occupancy Sensor (EEP A5-07-01)
* Added support for EEP A5-04-01 and A5-07-01
* Wrapper for ESP3 serial communication added. (It can automatically reconnect as well.) (Experimental Support)
* Converter for ESP3 to ESP2 messages added

## Version 1.3.2 Correction of Window Handle Positions (EEP F6-10-00)
*  &#x1F41E; Fixed Bug &#x1F41E;: Window handle status was not evaluated correctly

## Version 1.3.0 Reliable Serial Communication
* Switched to new **serial communication which automatically reconnect** in case of temporary connection/serial port loss.
  E.g. USB cable can be disconnected and plugged back in again and it will automatically reconnect without manual HA restart.

## Version 1.2.4 GUI for Automatic Generation of Configuration
* Device and sensor discovery and automatic generation of configuration improved and GUI added (See [docs](https://github.com/grimmpp/enocean-device-manager))
* &#x1F41E; Fixed Bug &#x1F41E;: Device names fixed.
* Improved config flow
* Support for serial over ethernet added

## Version 1.2.3 Improvements in Device Discovery
* &#x1F41E; Fixed Bug &#x1F41E;: Entity grouping for devices were broken.
* Eltako FMZ14 is working and tested ([Multifunction Time Relay](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FMZ14_30014009-2_gb.pdf))
* Adjusted and extended [device discovery](https://github.com/grimmpp/enocean-device-manager) to multi-gateway support
* Windows support for device discovery added
* Device discovery detects base id of FAM14 automatically
* Device discovery detects a few registered sensors and puts them into the auto generated configuration.

## Version 1.2.2 Support for Multiple Gateways
* Full support for gateway [Eltako FAM-USB](https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/)
* Target temperature synchronization between climate panel in Home Assistant and thermostat implemented.
* BaseId validation for gateways introduced. It will show warnings as output logs.
* Device Id can be displayed in device name optionally.
* Home Assistant eventing prepared to support more than one gateway
* Introduced ids for gateways.
* Manual installation of multiple gateways/hubs implemented. 
* **&#x26A0; Breaking Changes &#x26A0;**
  * All devices get a new identifier. Unfortunately, all devices need to be deleted and recreated. History of data gets lost!!!
  * Configuration: 'id' in 'gateway' is mandatory. See [docs](./docs/update_home_assistant_configuration.md)
  * Events in Home Assistant for switch telegrams have got different event_ids. This affects automations reacting on old event ids. See [docs](./docs/rocker_switch/readme.md)

## Version 1.1.3
* Added read-only support for gateway [Eltako FAM-USB](https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/)

## Version 1.1.2
* Docs for configuration added
* USB port for serial communication can be configured in gateway section.
* Configuration keys were made consistent. Replaced '-' through '_'. This change may require adaptation to existing configurations.

## version 1.1.1 - BugFix
* Problems with general-settings in configuration file.

## version 1.1.0 - Heating and Cooling
* Change file introduced
* **Climate Panel introduced** incl. support for actors like FAE14, FHK14, F4HK14, F2L14, FHK61, FME14 and EEP A5-10-06 as well as control panels like FTAF55ED.
* Docs for Climate Panel/Heating and Cooling
* Refactoring
  * Introduced many explicit types.
  * Logging improved
* Prepared config for other gateway types. (Currently supported Eltako fam14 and fgw14-usb)
* Support of different gateways e.g. enOcean USB300 with different protocol version (ESP3)
* Added teach-in buttons for climate and temperature controller
* Added Air Quality Sensor with EEP A5-09-0C for e.g. FLGTF
* Integrate Eltako FUTH ([Wireless thermo clock/hygrostat](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FUTH65D_12-24VUC_30065741-1_gb.pdf))
  * Temperature synchronization with FUTH and Home Assistant Climate (temperature controller) not yet properly working.
* Fast status change added. You can set per configuration is you want to wait for actuator response or if you directly want to see the status change in HA.

## Version 1.0.0 Baseline

