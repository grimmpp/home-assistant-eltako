# Gateways

A gateway is the component which builds the bridge between Home Assistant and the EnOcean wireless network or the RS485 bus. The gateway listens to telegrams on the RS485 bus or in the wireless network and transfers them to Home Assistant. In Home Assistant the Eltako Integration can send telegram either into wireless network or directly on the RS485 bus dependent on the type of gateway (USB based connection or radio transmitter). Based on the delivered EnOcean telegrams the Eltako Integration can the display the state of the actuators or send commands to change those states.

## Summary of Supported Gateways
What gateway is preferred for what?

### FAM-USB
* Is a good match for controlling actuators mounted on a RS485 bus with FAM14 and especially for decentralized actuators in Home Assistant.
* It also allows to send teach-in telegrams so that you can teach-in actuators by using the Eltako Integration in Home Assistant.

### FGW14-USB
* Has good performance because it filters out polling messages from FAM14 what makes Home Assistant faster.
* Like FAM14, it can transfer states of actuators mounted on the same RS485 bus to Home Assistant. It can also send telegrams to the actuators to change their states.
* Has better physical USB connector than FAM14.
* Cannot read memory of actuators thus it has better security measurements.
* Cannot control and send telegrams to decentralized actuators. Only to the RS485 bus on which it is mounted.

### FAM14 
* Can read memory of actuators. You can use it to [auto-generate configuration for Home Assistant](../../eltakodevice_discovery/readme.md).
* Quite a lot of unnecessary telegrams are sent to Home Assistant. Home Assistant could become slower.
* In operation it does the same like FGW14-USB.
* Like FGW14-USB, it can transfer states of actuators mounted on the same RS485 bus to Home Assistant. It can also send telegrams to the actuators to change their states.

### Conclusion
* Use FAM-USB for operations with Home Assistant. FAM-USB is a must for decentralized actuators. If your setup only have actuators mounted on the RS485 bus FGW14-USB is a good choice. <br />
* Use FAM14 to [generate Home Assistant configuration](../../eltakodevice_discovery/readme.md).


### Limitations
Currently all gateways are limited to control 128 devices. It is wished to support more than one gateway in parallel and then you could operate as many devices as you like. 


## Types of gateways

### [**Eltako FAM14**](https://www.eltako.com/en/product/professional-smart-home-en/series-14-rs485-bus-rail-mounted-devices-for-the-centralised-wireless-building-installation/fam14/) 

FAM14 is the wireless antenna module for the Eltako RS485 bus on which actuators can be plugged in. It sends the EnOcean telegram into the wireless network and can receive them either from the bus or wireless network.
You can use its usb port to connect it to Home Assistant. 

<img src="FAM14.jpg" height=100/> 

| Specialty | Description |
| ----- | ----- |
| Protocol | ESP2 |
| Baud rate | 57600 |
| Configuration Tool for Eltako Bus | [PCT14](https://www.eltako.com/en/software-pct14/) | 
| Manual | [en](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FAM14_30014000-2_gb.pdf), [de](https://www.eltako.com/fileadmin/downloads/de/_bedienung/FAM14_30014000-3_dt.pdf) |
| Address space | 128 internal address can be used for actuators. If you need more you can increase your setup by a second RS485 bus incl. dedicated FAM14. |

#### Pros
* Can read memory of actuators. You can use it to [auto-generate a configuration file for Home Assistant](../../eltakodevice_discovery/readme.md). 
* Not dependent on wireless network. Very stable connection.

#### Cons
* **Overhead traffic** is transferred to Home Assistant. It can slow down Home Assistant, better use FGW14-USB it delivers only status telegrams to Home Assistant. FGW14-USB is not allowed to access memory of actuators mounted on the bus. Thus it doesn't support auto-generation of Home Assistant configuration.
* **Only sends status updates into the wireless network.** If you want to send commands to decentralized actuators then you need to use EnOcean Transceiver like FAM-USB.
* **Teach-in telegrams cannot be sent with FAM14 nor with FGW14-USB** out of Home Assistant into the wireless network. 

#### FAM14 BaseId
FAM14 is setting its baseId automatically and sends telegrams out into the wireless network but only for status telegrams of the actuators.
This is only relevant for out going communication to devices in wireless network like decentralized actuators. 
You can find the baseId of FAM14 in PCT14 (Configuration Software).

#### Configuration 
1. Specify the type of gateway in the configuration (/homeassistant/configuration.yaml) in Home Assistant.
2. Enter your devices. I recommend to use a baseId and add the device id so that you don't get confused with all the addresses. 

**Configuration Example**:
Hint: Addresses in PCT14 are displayed in DEZ and in Home Assistant configuration in HEX.
```
eltako:
  gateway:
    device: fam14

  light:
  - id: 00-00-00-01         # internal address from PCT14
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: 00-00-B0-01       # HA sender baseId (00-00-B0-00) + internal address (0-80 HEX/128 DEZ)
      eep: A5-38-08

```




### [**Eltako FGW14-USB**](https://www.eltako.com/en/product/professional-smart-home-en/series-14-rs485-bus-rail-mounted-devices-for-the-centralised-wireless-building-installation/fgw14-usb/)

Is mounted on the rs485 bus and can read incoming telegrams from the wireless network, status telegrams of actuators mounted on the bus and can send commands to only the actuators mounted on the same rs485 bus. 

<img src="./FGW14-USB.jpg" height=100 > 

| Specialty | Description |
| ----- | ----- |
| Protocol | ESP2 |
| Baud rate | 57600 | 
| Manual | [de](https://www.eltako.com/fileadmin/downloads/de/_bedienung/FGW14-USB_30014049-1_dt.pdf), [en](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FGW14-USB_30014049-1_gb.pdf) |


#### Pros
* Less traffic overhead than FAM14.
* Not dependent on wireless network. Very stable connection.

#### Cons
* FGW14-USB is not allowed to access memory of actuators mounted on the bus. Thus it doesn't support auto-generation of Home Assistant configuration. You can use FAM14 for it.
* **Only sends status updates into the wireless network** via FAM14. If you want to send commands to decentralized actuators then you need to use EnOcean Transceiver like FAM-USB.
* **Teach-in telegrams cannot be sent via FAM14** out of Home Assistant into the wireless network. 

#### Configuration
Same like for FAM14.




### [**Eltako FAM-USB**](https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/)

FAM-USB is a usb device which can receive and send ESP2 telegrams. You can use it as gateway in Home Assistant to receive information and to control your actuators. It is connected to the decentralized actuators and to the actuators mounted on a RS485 bus via wireless network.

<img src="FAM-USB.jpg" height=100>

| Specialty | Description |
| ----- | ----- |
| Chip Set | [TCM300](https://www.enocean.com/en/product/tcm-300/?frequency=868), [Datasheet](https://www.enocean.com/wp-content/uploads/downloads-produkte/en/products/enocean_modules/tcm-300/data-sheet-pdf/TCM_300_TCM_320_DataSheet_May2019.pdf), [User Manual](https://www.enocean.com/wp-content/uploads/downloads-produkte/en/products/enocean_modules/tcm-300/user-manual-pdf/TCM300_TCM320_UserManual_Nov2021.pdf), [Firmeware](https://www.enocean.com/en/support/software-tools-kits) |
| Protocol | ESP2 |
| Baud rate | 9600 |
| Tool for chip configuration | [DolphinStudio](https://www.enocean.com/de/produkt/dolphinstudio/?ts=1701468463) |
| Sender Address Range | TCM300 has 128 address in the range of 0xFF80_0000 to 0xFFFF_FFFE starting at a base address (BaseId).  |

#### Configuration 
1. Specify the type of gateway in the configuration (/homeassistant/configuration.yaml) in Home Assistant.
2. Find out  baseId of FAM-USB (start address for sender addresses). Use [DolphinStudio](https://www.enocean.com/de/produkt/dolphinstudio/?ts=1701468463) to read meta data from the chip.
   In this example we use FF-80-80-00 as start address.
   <img src="./DoplhinStudio_baseId.png">
   Or use [eltakotool.py](https://github.com/grimmpp/eltako14bus) `./eltakotool.py --eltakobus /dev/ttyUSB1 --baud_rate 9600 send_raw ab 58 00 00 00 00 00 00 00 00 00` 
3. If your actuator is on a RS485 bus behind FAM14 find out the baseId of FAM14. Use [PCT14](https://www.eltako.com/en/software-pct14/) to read the meta information of FAM14.
   In this example we use FF-AA-00-00
   <img src="./FAM14_baseId.png">
4. For all actuators on the bus take the FAM14 baseId and add the internal address. In PCT14 all actuator address are displayed in DEZ. You need to convert them to HEX. (E.g. 26 in DEZ = 1A in HEX) For decentralized actuators just take their addresses.
5. For all Home Assistant senders take the baseId of FAM-USB and add the internal address from PCT14. 

```
eltako:
  gateway:
    device: fam-usb

  light:
  - id: FF-AA-00-01         # baseId of FAM14 (FF-AA-00-00) + internal address
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: FF-80-80-01       # baseId of FAM-USB (FF-80-80-00) + sender id (0-80 HEX/128 DEZ)
      eep: A5-38-08

```

### [**EnOcean GmbH USB300**](https://www.enocean.com/en/product/usb-300/)

FAM-USB is a usb device which can receive and send **ESP3** telegrams. 

**CURRENTLY NOT SUPPORTED AS HOME ASSISTANT GATEWAY!!!**

If you want to use it anyway check out the [EnOcean Integration](https://www.home-assistant.io/integrations/enocean/).

<img src="./USB300.jpg" height=100>
