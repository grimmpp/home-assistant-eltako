Eltako bus support for home assistant
=====================================

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

You can optinally also define
* name - The name, which is shown in Home Assistant
* device_class - Please refer to the device_class documentation in Home Assistant (Binary sensor and Cover)

For devices, which are controllable (like lights or covers), you have to define a sender consisting of
* id - This is the address of the sender teached into the device
* eep - The EEP of the sender (have a look at "Supported EEPs and devices")

Covers have two special attributes
* time_closes - The time it takes until the cover is completely closed (used for position calculation)
* time_opens - The time it takes until the cover is completely opened (used for position calculation)



Supported EEPs and devices
========

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



Credits
=======
Credits for this code goes to chrysn (https://gitlab.com/chrysn) who made this code publicly available on his Gitlab repo, and shared it in the Home Assistant community. This repository here on Github is meant to keep the Eltako integration alive, make it work again with the latest Home Asssistant Core and potentially add functionalities.
