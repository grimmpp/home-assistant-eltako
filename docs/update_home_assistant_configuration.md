# Update Home Assistant Configuration

Before you can start and see your devices and sensors in Home Assistant you need to enter them unfortunately manually into the Home Assistant Configuration ``/config/configuration.yaml``. 
You can edit the configuration file e.g. with the add-on [File Editor](https://github.com/home-assistant/addons/tree/master/configurator). In this repository the is also a script which can read all devices mounted on the eltako bus.

After you have finished the configuration changes **don't forget to restart Home Assistant so that the changes will be applied.** You can trigger the restart in the menu of File Editor.

## Schema of the configuration file:
If the documentation might be outdated and not complete you can always find the truth in [schema.py](../custom_components/eltako/schema.py).

A device inside a device type alway consists of
* id - This is the address of the device on the bus
* eep - The EEP of the device (have a look at "Supported EEPs and devices")

You can optionally also define
* name - The name, which is shown in Home Assistant
* device_class - Please refer to the device_class documentation in Home Assistant (Binary sensor and Cover)

For devices, which are controllable (like lights or covers), you have to define a sender consisting of
* id - This is the address of the sender teached into the device
* eep - The EEP of the sender (have a look at "Supported EEPs and devices")

All devices need to be listed under a gateway which connects them to Home Assistant.

For details checkout other documentations about the devices.

```
# always starts with 'eltako'
eltako:

  # optional section 'general_settings'
  general_settings:
    fast_status_change: False   # True: Changes status in HA immediately without waiting for actuator response. Default: False

  # section 'gateway'
  # Currently only devices based on ESP2 protocol are supported. In future ESP3 protocol shall be extended. 
  # 
  gateway:
  - id: 1                       # virtual id
    base_id: FF-AA-80-00        # Address which is used to send telegrams into wireless network. Mainly important for transceivers like FAM-USB
    device_type: fgw14usb            # Supported gateways: gam14, fgw14usb, fam-usb
    devices:                    # list here all devices connected to this gateway

      # binary sensors can be switches, door or window contacts, ...
      # This section contains a list of sensor entities
      binary_sensor:
        - id: ff-bb-0a-1b                 # address (HEX) 
          eep: F6-02-01                   # Supported EEP telegrams: F6-02-01, F6-02-02, F6-10-00, D5-00-01, A5-08-01
          name: "window contact kitchen"  # optional: display name
          device_class: window            # optional: device class - will be distinguished in Home Assistant.
          invert_signal: True             # optional: inverts value

      # in the light section all actuators/relays are represented.
      light:
      - id: 00-00-00-01           # address (HEX) 
        eep: M5-38-08             # Supported EEP telegrams: A5-38-08, M5-38-08
        name: FSR14_4x - 1        # optional: display name
        sender:                   # virtual switch in Home Assistant.
          id: 00-00-B0-01         # every sender needs it's own address which needs to be entered in PCT14 / actuator with function group 51 for FSR14.
          eep: A5-38-08   

      # switches are a generalization of lights and will be displayed differently in Home Assistant. 
      switch:
      - id: 00-00-00-02           # address (HEX) 
        eep: M5-38-08             # Supported EEP telegrams: M5-38-08 (1byte telegram)
        name: "Socket Basement"   # optional: display name
        sender:                   # virtual switch in Home Assistant.
          id: 00-00-B0-02         # every sender needs it's own address which needs to be entered in PCT14 / actuator with function group 51 for FSR14.
          eep: F6-02-01 

      # sensor can be almost everything what can send data.
      sensor:
      - id: 05-EE-88-15           # address (HEX) 
        eep: A5-13-01             # Supported EEP telegrams: A5-04-02, A5-09-0C, A5-10-06, A5-10-12, A5-12-01, A5_12_02, A5_12_03, A5_13_01, F6_10_00
        name: "Weather Station"   # optional: display name
        language: "en"            # optional and only for FLGT (air quality). Supported values: en, de
        voc_type_indexes: [0]     # optional and only for FLGT (air quality). Index mapping can be found here: https://github.com/grimmpp/eltako14bus/blob/master/eltakobus/eep.py
        meter_tariffs: [1]        # optional and only for electric meter. Supported values: 1-16

      # list of covers actuators
      cover:
      - id: 00-00-00-06           # address (HEX) 
        eep: G5-3F-7F             # Supported EEP telegrams: G5-3F-7F
        name: FSB14 - 6           # optional: display name
        sender:                   # virtual switch in Home Assistant.
          id: 00-00-B0-06         # every sender needs it's own address which needs to be entered in PCT14 / actuator with function group 31 for FSB14.
          eep: H5-3F-7F
        device_class: shutter     # optional for showing the right icon and panels in Home Assistant
        time_closes: 24           # optional: The time it takes until the cover is completely closed (used for position calculation)
        time_opens: 25            # optional: The time it takes until the cover is completely opened (used for position calculation)

      # list of temperature controller. Can be used for heating and cooling
      # for details check out the documentation 'heating and cooling'
      climate:
      - id: 00-00-00-08           # address (HEX) 
        eep: A5-10-06             # Supported EEP telegrams: A5-10-06
        name: FAE14SSR - 8        # optional: display name
        sender:                   # virtual switch in Home Assistant.
          id: 00-00-B0-08         # every sender needs it's own address which needs to be entered in PCT14 / actuator with function group 30 for FHK14 and FAE14.
          eep: A5-10-06           
        temperature_unit: °C        # optional: Supported values: °C, °F, K 
        min_target_temperature: 17  # optional: Supported values: 17-25
        max_target_temperature: 25  # optional: Supported values: 17-25
        cooling_mode:               # optional
          sensor:
            id: ff-bb-0a-1b         # usually a binary_sensor like a rocker switch which must be defined in binary_sensors. Eltako uses a physical switch to detect if the cooling mode of the e.g. heat pump is activated.
            switch-button: 0x50     #optional and only for rocker switch. contacts don't need this information. button of the switch in (HEX) 


logger:
  default: info
  logs:
    eltako: debug     # to change log level and to see messages on the bus switch from info to debug
```

## Home Assistant Entities

The entity types above are mainly predefined in Home Assistant.
Check out the detailed documentation about the [Home Assistant Entity Type](https://developers.home-assistant.io/docs/core/entity) to find more configuration possibilities.

## Example Configuration File
Another example file can be found [here](../ha.yaml).

~~~~~~~~
eltako:
  general_settings:
    fast_status_change: False   # True: Changes status in HA immediately without waiting for actuator response. Default: False
  gateway:
  - device: fgw14usb            # Supported gateways: gam14, fgw14usb
    base_id: FF-AA-80-00        # Offset address for sending telegrams into wireless network
    devices:
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
          invert_signal: True   # value is inverted and shows closed contact as open.
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
