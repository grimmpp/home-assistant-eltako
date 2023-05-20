# Eltako Bus Integration (rs485 - enocean) for Home Assistant
<!-- [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration) -->
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This repo contains an Home Assistant Integration for Eltako Baureihe 14. 
This integration allows you to get all information of the Eltako bus and it allows you ton control all the devices via Home Assistant. (See supported devices.) Reaction on sensor data like weather station, rocker switches, ... can be use in Home Assistant automations as well.

For more details check out the provided tutorials and links.

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

# Installation and Configuration

While this is not integrated into home assistant's repositories. You need to install first [Home Assistant Commuinty Sore (HACS)](https://hacs.xyz/) in order to install custom components. After that you need to do the following steps:
1. **Install repo via HACS**: Simply enter the URL of this repo. It will then be listed in HACS and also shows when new updates are available. [Add Custom Repo in HACS](https://hacs.xyz/docs/faq/custom_repositories/)

   *Alternative 2:* Copying directory ``eltako``** from this repository into your home assistant's ``/config/custom_components`` directory.
   For easy installation just clone this repository ``git clone https://github.com/grimmpp/home-assistant-eltako.git`` and execute the installation script of this repo ``./install_custom_component_eltako.sh``. 
2. To **enable this component**, go to your integrations, press the "add" button and select "Eltako". In the presented sheet either select the detected USB gateway or enter the path manually.
3. **Update Home Assistant configuration** ``/config/configuration.yaml`` and add all devices and sensors you want to integrate. See [How to update Home Assistant Configuration](./tutorials/update_home_assistant_configuration.md) to see how the configuration should look like. 
There is also a scipt which can detect devices and sensors and creates a prepared configuration because in big setups it can be a little effort doing that manually. For more details have a look into [Device and Sensor Discovery for Home Assistant Configuration](./eltakodevice_discovery/)

# Testing

Testing this integration via Home Assistant development container or updating it in a Home Assistant instance is quite time consuming. Therefore I've added some basic tests to ensure quickly a base quality. 

Unit and component tests for this integration are located in the folder tests. There is already a vscode settings.json prepared to start them via vscode or you can just run the following command from the repo folder.

```
python -m unittest discover tests -v
```

# Tutorials
* [Create Home Assistant Configuration File for Eltako Integration](./eltakodevice_discovery/)
* [Eltako Home Automation](https://github.com/cvanlabe/Eltako-home-automation) from [Cedric Van Labeke](https://github.com/cvanlabe)
* [Simple Eltako Setup](./tutorials/simple_eltako_setup.md)
* [How to detect Switch Signals and react on thoese in Home Assistant](./tutorials/rocker_switch/readme.md)


# Dependencies
* [Eltako Software PCT14](https://www.eltako.com/en/software-pct14/) for programming and configuring Eltako Baureihe 14 devices natively.
* [Home Assistant Community Store](https://hacs.xyz/) is needed to be able to install this repository. It allows you to install custom_components.
* [Eltako14Bus Python Library](https://github.com/grimmpp/eltako14bus) is used by this Home Assistant Integration.


# Usefull Home Assistant Addons
* [File Editor](https://github.com/home-assistant/addons/tree/master/configurator)
* [Log Viewer](https://github.com/hassio-addons/addon-log-viewer)
* [Terminal & SSH](https://github.com/home-assistant/addons/tree/master/ssh)
* [Studio Code Server](https://github.com/hassio-addons/addon-vscode)


# Documentation
* [Home Assistant Developer Docs](https://developers.home-assistant.io/)
* [EnOcean Equipment Profiles - EEP2.1](https://www.trio2sys.fr/images/media/EnOcean_Equipment_Profiles_EEP2.1.pdf)
* [EnOcean Equipment Profiles - EEP v2.6.7](https://www.enocean-alliance.org/wp-content/uploads/2017/05/EnOcean_Equipment_Profiles_EEP_v2.6.7_public.pdf)


# Credits
Credits for this code goes to [chrysn](https://gitlab.com/chrysn) and [Johannes Bosecker](https://github.com/JBosecker) who made this code publicly available on their Gitlab repos, and shared it in the Home Assistant community ([Eltako “Baureihe 14 – RS485” (Enocean) Debugging](https://community.home-assistant.io/t/eltako-baureihe-14-rs485-enocean-debugging/49712)).  This repository here on Github is meant to keep the Eltako integration alive, make it work again with the latest Home Asssistant Core and potentially add functionalities.
