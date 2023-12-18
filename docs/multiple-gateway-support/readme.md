# Multiple Gateway Support

<img src="./HA-Eltako-2Hubs.png" height="365">

There are two types of gateways supported:
1. Eltako gateways based on ESP2 protocol (old) which are e.g. **Eltako FAM14**, **Eltako FGW14-USB**, **Eltako FAM-USB**
2. Mordern Enocean gateways based ESP3 protocol (new) which is e.g. **EnOcean USB300**

Currently only ESP2 devices are supproted.

All gateways (hubs) need explicitely configured and devices connected through this gateway to Home Assistant need to be listed below the gateway section. Every gateway needs to have an unique id whicht is an arbritatry number which can be changed and exchanged. This number will be part of the device identifiers. If you want to change a gateway you can keep the id of the previouse gateway and with it all ids and histories of its devices can be kept.
After you provided the configuration + restart of Home Assistant you can add the gateways as hubs in Home Assistant.

## Example
In this example two gateways are connected to Home Assistant. The first one `Eltako FGW14-USB` connected directly to the Eltako RS485 bus builds a bridge for the communication to a light relay. The second one is a wireless transceiver `Eltako FAM-USB` which connects a weather station to Home Assistant.
```
eltako:
  general_settings:
    fast_status_change: False
    show_dev_id_in_dev_name: True

  gateway:
  - id: 1
    device_type: fgw14usb
    base_id: FF-AA-00-00
    devices:
      light:
      - id: 00-00-00-01
        eep: M5-38-08
        name: "FSR14_4x - 1"
        sender:
          id: 00-00-B1-01
          eep: A5-38-08

  - id: 2
    device: fam-usb
    base_id: FF-BB-00-00
    devices:
      sensor:
      - id: 05-1E-83-15
        eep: A5-13-01
        name: "Weather Station"
 ...
```