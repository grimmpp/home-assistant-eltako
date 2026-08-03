# Changes and Feature List

## Version 2.2.0
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
* "check & teach in HA senders" per FAM14: verifies the configured sender ids against the device memories and writes missing ones with `ensure_programmed` (bus locked, standard procedure of the EnOcean Device Manager)
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
* new test which statically detects undefined names (missing imports) in all modules of the integration
* Bugfixes found on a live installation
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
* Device and sensor discovery and automatic generation of configuration improved and GUI added (See [docs](./eltakodevice_discovery/readme.md))
* &#x1F41E; Fixed Bug &#x1F41E;: Device names fixed.
* Improved config flow
* Support for serial over ethernet added

## Version 1.2.3 Improvements in Device Discovery
* &#x1F41E; Fixed Bug &#x1F41E;: Entity grouping for devices were broken.
* Eltako FMZ14 is working and tested ([Multifunction Time Relay](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FMZ14_30014009-2_gb.pdf))
* Adjusted and extended [device discovery](./eltakodevice_discovery/readme.md) to multi-gateway support
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

