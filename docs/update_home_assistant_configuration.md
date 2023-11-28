# Update Home Assistant Configuration

You need to enter all devices and sensors you want to use Home Assistant into the Home Assistant Configuration ``/config/configuration.yaml``. 
I can recommend to install the add-on [File Editor](https://github.com/home-assistant/addons/tree/master/configurator) for updating the configuration file. 

**Don't forget to restart Home Assistant so that the changes will be applied.** You can trigger the restart in the menu of File Editor.

## Example Configuration File

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
