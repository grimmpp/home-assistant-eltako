# Eltako Bus Integration (rs485 - enocean) for Home Assistant

This repo contains an Home Assistant Integration for Eltako Baureihe 14. 
This integration allows you to get all information of the Eltako bus and it allows you ton control all the devices via Home Assistant. (See supported devices.) Reaction on sensor data like weather station, rocker switches, ... can be use in Home Assistant automations as well.

For more details check out the provided tutorials and links.

# Installation

While this is not integrated into home assistant's repositories, this can be installed by copying over the eltako directory from this repository into your home assistant's ``/config/custom_components`` directory.

To enable this component, go to your integrations, press the "add" button and select "Eltako".
In the presented sheet either select the detected USB gateway or enter the path manually.

The devices themselves have to be added to your ``/config/configuration.yaml`` file.

A full configuration can thus look like this:

~~~~~~~~
eltako:
  binary_sensor:
    - id: "00-00-10-70"
      eep: "D5-00-01"
      device_class: window
    - id: "00-00-10-77"
      eep: "D5-00-01"
      device_class: smoke
    - id: "00-00-10-91"
      eep: "A5-08-01"
      device_class: motion
    - id: "FE-EF-09-3B"
      eep: "F6-10-00"
      device_class: door
  sensor:
    - id: "00-00-18-00"
      eep: "A5-13-01"
    - id: "00-00-00-2A"
      eep: "A5-12-01"
    - id: "00-00-00-2D"
      eep: "A5-12-02"
    - id: "00-00-00-2E"
      eep: "A5-12-03"
  light:
    - id: "00-00-00-02"
      eep: "A5-38-08"
      sender:
          id: "00-00-00-03"
          eep: "A5-38-08"
    - id: "00-00-00-08"
      eep: "M5-38-08"
      sender:
          id: "00-00-00-0F"
          eep: "A5-38-08"
  switch:
    - id: "FE-FE-FE-71"
      eep: "M5-38-08"
      sender:
          id: "00-00-01-71 left"
          eep: "F6-02-01"
  cover:
    - id: "00-00-00-1B"
      eep: "G5-3F-7F"
      sender:
          id: "00-00-00-45"
          eep: "H5-3F-7F"
      time_closes: 24
      time_opens: 25
      device_class: shutter
~~~~~~~~

As you can see, there has to be a custom section for your Eltako devices.
Under this section you can define the supported platforms.
A device inside a platform alway consists of
* id - This is the address of the device on the bus
* eep - The EEP of the device (have a look at "Supported EEPs and devices")

You can optionally also define
* name - The name, which is shown in Home Assistant
* device_class - Please refer to the device_class documentation in Home Assistant (Binary sensor and Cover)

For devices, which are controllable (like lights or covers), you have to define a sender consisting of
* id - This is the address of the sender teached into the device
* eep - The EEP of the sender (have a look at "Supported EEPs and devices")

Covers have two special attributes
* time_closes - The time it takes until the cover is completely closed (used for position calculation)
* time_opens - The time it takes until the cover is completely opened (used for position calculation)



# Supported EEPs and devices

EEPs and devices currently supported for the different platforms are:
* Binary sensor
  * F6-02-01 (Rocker switch, FTS14EM)
  * F6-02-02 (Rocker switch)
  * F6-10-00 (Window handle, FTS14EM)
  * D5-00-01 (Contact sensor, FTS14EM)
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



# Tutorials
* [Create Home Assistant Configuration File for Eltako Integration](./eltakodevice_discovery/)
* [Eltako Home Automation](https://github.com/cvanlabe/Eltako-home-automation) from [Cedric Van Labeke](https://github.com/cvanlabe)
* [Simple Eltako Setup](./tutorials/simple_eltako_setup.md)
* [How to detect Switch Signals and react on thoese in Home Assistant](./tutorials/rocker_switch/readme.md)


# Dependencies
* [Eltako Software PCT14](https://www.eltako.com/en/software-pct14/) for programming and configuring Eltako Baureihe 14 devices natively.
* [Home Assistant Community Store](https://hacs.xyz/) is needed to be able to install this repository. It allows you to install custom_components.
* [Eltako Baureihe 14 Python Library](https://github.com/michaelpiron/eltako14bus) is used by this Home Assistant Integration.


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
