# Changes and Feature List

## Version 2.0.0
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

TODO: improve performance of controlling groups. (send only one group telegram instead of many indivitual commands)

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

