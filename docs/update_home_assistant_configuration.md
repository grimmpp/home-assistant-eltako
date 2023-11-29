# Update Home Assistant Configuration

Before you can start and see your devices and sensors in Home Assistant you need to enter them unfortunately manually into the Home Assistant Configuration ``/config/configuration.yaml``. 
You can edit the configuration file e.g. with the add-on [File Editor](https://github.com/home-assistant/addons/tree/master/configurator). In this repository the is also a script which can read all devices mounted on the eltako bus.

After you have finished the configuration changes **don't forget to restart Home Assistant so that the changes will be applied.** You can trigger the restart in the menu of File Editor.

## Schema of the configuration file:
If the documentation might be outdated and not complete you can always find the truth in [schema.py](../custom_components/eltako/schema.py).

```
# always starts with 'eltako'
eltako:

  # optional section 'general-settings'
  general-settings:
    fast-status-change: False   # True: Changes status in HA immediately without waiting for actuator response. Default: False

  # optional section 'gateways'
  # currently it makes no differences which devices is configured because all supported devices behave the same. In future ESP3 protocol shall be supported. 
  gateway:
    device: fgw14usb            # Supported gateways: gam14, fgw14usb
    serial_path: "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10MAMIG-if00-port0"   # example value


```


## Example Configuration File
Another example file can be found [here](../ha.yaml).

~~~~~~~~
eltako:
  general-settings:
    fast-status-change: False   # True: Changes status in HA immediately without waiting for actuator response. Default: False
  gateway:
    device: fgw14usb            # Supported gateways: gam14, fgw14usb
  sensor:
  - id: 05-EE-88-15
    eep: A5-13-01
    name: "Weather Station"
  - id: ff-aa-dd-81
    eep: A5-04-02
    name: "Temperature and Humidity Sensor - FLGTF55"
  - id: ff-66-dd-81
    eep: A5-04-02
    name: "Temp. Sensor 2 - FLGTF55"
  - id: ff-ee-55-81
    eep: A5-10-06
    name: "Temp. Sensor and Controller - FUTH A5-10-06"
  - id: ff-ee-55-92
    eep: A5-10-12
    name: "Hygrostat - FUTH"
  - id: ff-66-dd-80
    eep: A5-09-0C
    name: "Air Quality Sensor - FLGTF55"
  light:
  - id: 00-00-00-01
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: 00-00-B0-01
      eep: A5-38-08
  - id: 00-00-00-02
    eep: M5-38-08
    name: FSR14_4x - 2
    sender:
      id: 00-00-B0-02
      eep: A5-38-08
  - id: 00-00-00-03
    eep: M5-38-08
    name: FSR14_4x - 3
    sender:
      id: 00-00-B0-03
      eep: A5-38-08
  - id: 00-00-00-04
    eep: M5-38-08
    name: FSR14_4x - 4
    sender:
      id: 00-00-B0-04
      eep: A5-38-08
  - id: 00-00-00-05
    eep: A5-38-08
    name: FUD14 - 5
    sender:
      id: 00-00-B0-05
      eep: A5-38-08
  binary_sensor:
    - id: ff-bb-0a-1b
      eep: F6-02-01
    - id: ff-bb-da-04
      eep: F6-02-01     # rocker switch 1
    - id: ff-dd-b6-40
      eep: F6-02-01     # rocker switch 2
    - id: 00-00-10-08   # address from FTS14EM (wired switch)
      eep: D5-00-01
      name: window 8
      device_class: window  # is displayed as window contact
      invert-signal: True   # value is inverted and shows closed contact as open.
  cover:
  - id: 00-00-00-06
    eep: G5-3F-7F
    name: FSB14 - 6
    sender:
      id: 00-00-B0-06
      eep: H5-3F-7F
    device_class: shutter
    time_closes: 24
    time_opens: 25
  - id: 00-00-00-07
    eep: G5-3F-7F
    name: FSB14 - 7
    sender:
      id: 00-00-B0-07
      eep: H5-3F-7F
    device_class: shutter
    time_closes: 24
    time_opens: 25
  climate:
  - id: 00-00-00-08
    eep: A5-10-06
    name: FAE14SSR - 8
    sender:
      id: 00-00-B0-08
      eep: A5-10-06
  - id: 00-00-00-09
    eep: A5-10-06
    name: FAE14SSR - 9
    sender:
      id: 00-00-B0-09
      eep: A5-10-06

logger:
  default: info
  logs:
    eltako: debug     # to change log level and to see messages on the bus switch from info to debug

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
