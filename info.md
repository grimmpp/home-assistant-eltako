[![Generic badge](https://img.shields.io/badge/HACS-Custom-3498db.svg)](https://github.com/hacs/integration)
[![Generic badge](https://img.shields.io/github/commit-activity/y/grimmpp/home-assistant-eltako.svg?style=flat&color=3498db)](https://github.com/grimmpp/home-assistant-eltako/commits/main)
[![Generic badge](https://img.shields.io/badge/Community-Forum-3498db.svg)](https://community.home-assistant.io/)
[![Generic badge](https://img.shields.io/badge/Community_Forum-Eltako_Integration_Debugging-3498db.svg)](https://community.home-assistant.io/t/eltako-baureihe-14-rs485-enocean-debugging/49712)
[![Generic badge](https://img.shields.io/badge/License-MIT-3498db.svg)](/LICENSE)
[![Generic badge](https://img.shields.io/badge/SUPPORT_THIS_PROJECT-Donate-27ae60.svg)](https://buymeacoffee.com/grimmpp)

# Eltako Bus Integration (RS485 - EnOcean) for Home Assistant

This repo contains an Home Assistant Integration for Eltako Baureihe 14. 
This integration allows you to get all information of the Eltako 14 Bus and it allows you to control all the devices via Home Assistant. You can also react on sensors like weather station, rocker switches, window contacts ... with automations in Home Assistant.

See more details on GitHub: [home-assistant-eltako](https://github.com/grimmpp/home-assistant-eltako)

# Supported EEPs and devices

EEPs and devices currently supported for the different platforms are:
* Binary sensor
  * F6-02-01 (Rocker switch, FTS14EM)
  * F6-02-02 (Rocker switch)
  * F6-10-00 (Window handle, FTS14EM)
  * D5-00-01 (Contact sensor, FTS14EM) incl. signal inverter
  * A5-08-01 (Occupancy sensor, FTS14EM)
* Sensor
  * A5-13-01 (Weather station, FWG14)
  * F6-10-00 (Window handle, FTS14EM)
  * A5-12-01 (Automated meter reading - electricity, FSDG14)
  * A5-12-02 (Automated meter reading - gas, F3Z14D)
  * A5-12-03 (Automated meter reading - water, F3Z14D)
* Light
  * A5-38-08 (Central command - gateway, FUD14)
  * M5-38-08 (Eltako relay, FSR14)
* Switch
  * M5-38-08 (Eltako relay, FSR14)
* Cover
  * G5-3F-7F (Eltako cover, FSB14)

Sender EEPs currently supported for the different platforms are:
* Light
  * A5-38-08 (Central command - gateway, FUD14)
* Switch
  * F6-02-01 (Rocker switch)
* Cover
  * H5-3F-7F (Eltako cover, FSB14)