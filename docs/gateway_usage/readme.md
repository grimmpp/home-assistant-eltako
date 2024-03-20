# Usage of Gatways

Hints: 
* Have you checked out the different gatewys and their characteristics? [Supported Gateways](../gateways/readme.md)
* Have you checked out the support for multiple gateways at the same time? [Multiple Gateway Support](../multiple-gateway-support/readme.md)

## How to configure gateways

In order to use a gateway you need to declare the gateway and all devices which shall interact with it in the Home Assistant Configuration (`/config/configuration.yaml`). The configuration can be e.g. edit with [File Editor](https://github.com/home-assistant/addons/tree/master/configurator).

To get familiar with the Eltako Integration configuration check out [Update Home Assistant Configuration](../update_home_assistant_configuration.md).

## Gateway Attributes
| Attribute   | Type / Values   | Description |
| :---        | :---        | :---        |
| `id` | Number | Unique arbritary number to identify the gateway. |
| `device_type` | fam14, fgw14usb, fam-usb, enocean-usb300 | The device type defines the gateway model. Base on this information other information is derived. Supported values can be found in [const.py](../../custom_components/eltako/const.py) Supported gateways are described [here](../gateways/readme.md). |
| `base_id` | enocean address format | Gateways can obviously receive and send messages. To send messages they use a hardcoded range of 128 addresses. The base_id is the first address of this range. Base_ids are used to identify the source of a message and to validate the configuration. |
| `devices` | configuration | Devices grouped by Home Assistant platform types. All devices which are listed here will be represented by this device. Device listed more than one in different devices will be recognized as two independent devices. |


### Example Configuration
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
          id: 00-00-B0-01
          eep: A5-38-08
```

## Gateway Features

* Gateways are a bridge between Home Assistant and the devices by receiving and sending messages.
* Gateways are connected via USB to the Home Assistant box. They use the protocol ESP2 or ESP3 based on serial communication. This serial commuinication can automatically reconnected in case of hiccups.


## Gateway Reprentation in Home Assistant

The following information is mainly used for debugging purposes and statistics.

| Entity   | Type | Description |
| :---        | :---        | :---        |
| `Reconnect Gateway` | Push Button | To trigger reconnection manually for testing. Reconnection actaully happens automatically  |
| `ID` | Label | Shows the base id of the gateway. |
| `Connected` | Binary State | Shows if the serial connection (USB) is established. |
| `Last Message Received` | Timestamp | Shows time passed since last message received. |
| `Received Messages per Session` | Counter | Counts messages for current connection. (Hint: There is a history for every sensor.) |
| `Serial Path` | Label | Shows the USB port/path to which the gateway is connected. |
| `USB Protocol` | Label | Shows the protocol for serial connection. |

<img src="screenshot-gateway-representation.png" height="400" />