[![Generic badge](https://img.shields.io/badge/HACS-Custom-3498db.svg)](https://github.com/hacs/integration)
[![Generic badge](https://img.shields.io/github/commit-activity/y/grimmpp/home-assistant-eltako.svg?style=flat&color=3498db)](https://github.com/grimmpp/home-assistant-eltako/commits/main)
[![Generic badge](https://img.shields.io/badge/Community-Forum-3498db.svg)](https://community.home-assistant.io/)
[![Generic badge](https://img.shields.io/badge/Community_Forum-Eltako_Integration_Debugging-3498db.svg)](https://community.home-assistant.io/t/eltako-baureihe-14-rs485-enocean-debugging/49712)
[![Generic badge](https://img.shields.io/badge/License-MIT-3498db.svg)](/LICENSE)
[![Generic badge](https://img.shields.io/badge/SUPPORT_THIS_PROJECT-Donate-27ae60.svg)](https://buymeacoffee.com/grimmpp)

# Eltako Bus Integration (RS485 - EnOcean) for Home Assistant

This repo contains an Home Assistant Integration for Eltako Baureihe 14. 
This integration allows you to get all information of the Eltako 14 Bus and it allows you to control all the devices via Home Assistant. (See supported devices.) You can also react on sensors like weather station, rocker switches, window contacts ... with automations in Home Assistant.

For more details check out the provided [docs](./docs) and links listed at the end.

# Supported EEPs and devices

The following EnOcean Equipment Profiles (EEPs) and devices are currently supported. In general, this is not limited to Eltako devices, mainly to the EnOcean standard. 
Elatko devices are exemplarily mentioned. You can find [here](https://www.eltako.com/fileadmin/downloads/de/Gesamtkatalog/Eltako_Gesamtkatalog_KapT_low_res.pdf) a nice overview about which EEPs are provided/required by which Eltako devices.

**Supported sensor EEPs**
* Binary sensor
  * F6-02-01 ([Rocker switch](./docs/rocker_switch/readme.md), FTS14EM)
  * F6-02-02 ([Rocker switch](./docs/rocker_switch/readme.md))
  * F6-10-00 (Window handle, FTS14EM)
  * D5-00-01 (Contact sensor, FTS14EM) incl. signal inverter
  * A5-08-01 (Occupancy sensor, FTS14EM)
* Sensor
  * A5-04-02 (Temperature and Humidity Sensor, FLGTF, FLT58)
  * A5-09-0C (Air Quality / VOC⁠ (Volatile Organic Compounds) e.g. [FLGTF](./docs/flgtf_temp_humidity_air_quality/readme.md))
  * A5-10-06 (Temperature Sensor and Controller e.g. FUTH)
  * A5-10-12 (Temperature Sensor and Controller and Humidity Sensor e.g. FUTH)
  * A5-12-01 (Automated meter reading - electricity, FSDG14)
  * A5-12-02 (Automated meter reading - gas, F3Z14D)
  * A5-12-03 (Automated meter reading - water, F3Z14D)
  * A5-13-01 (Weather station, FWG14)
  * F6-10-00 (Window handle, FTS14EM)
* Light
  * A5-38-08 (Central command - gateway, FUD14)
  * M5-38-08 (Eltako relay, FSR14)
* Switch
  * M5-38-08 (Eltako relay, FSR14)
* Cover
  * G5-3F-7F (Eltako cover, FSB14)

**Supported sender EEPs**
* Light
  * A5-38-08 (Central command - gateway, FUD14)
* [Switch](./docs/rocker_switch/readme.md)
  * F6-02-01 (Rocker switch)
* Cover
  * H5-3F-7F (Eltako cover, FSB14)
* [Climate](./docs/heating-and-cooling/readme.md) (**Experimental** - telegram of teach-in button seems to be wrong!)
  * A5-10-06 (Eltako FAE14, FHK14, F4HK14, F2L14, FHK61, FME14)
 
**Gateway**
  * Eltako FAM14 and Eltako FGW14-USB (based on ESP2, rs485 bus and baud rate 57600, uses library [eltako14bus](https://github.com/grimmpp/eltako14bus)) 
  * EnOcean USB300 (**NOT YET IMPLEMENTED**) (based on ESP3 and baud rate 57600, uses library [Python EnOcean](https://github.com/kipe/enocean))
    * Library is integrated and USB300 can be configured. Message conversion from ESP3 to ESp2 and back is not yet implemented. This means this dongle is not yet working.
