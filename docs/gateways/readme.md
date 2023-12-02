# Gateways

A gateway is the component which builds the bridge between Home Assistant and the EnOcean wireless network or the rs485 bus. The gateways listens to telegrams on the bus or in the air and sends them to Home Assistant. On the other side Eltako Integration in Home Assistant can send telegram either into wireless network or directly on the rs485 bus.

## Types of gateways

### [**Eltako FAM14**](https://www.eltako.com/en/product/professional-smart-home-en/series-14-rs485-bus-rail-mounted-devices-for-the-centralised-wireless-building-installation/fam14/) 

FAM14 is the wireless antenna module for the Eltako RS485 bus on which actuators can be plugged in. It sends the EnOcean telegram into the wireless network and can receive them either from the bus or wireless network.
You can use its usb port and use it as Home Assistant gateway. 

<img src="FAM14.jpg" height=100/> 

| Specialty | Description |
| ----- | ----- |
| Protocol | ESP2 |
| Baud rate | 57600 |
| Configuration Tool for Eltako Bus | [PCT14](https://www.eltako.com/en/software-pct14/) | 

#### Pros
* Can read memory of actuators

#### Cons
* Overhead traffic is transferred to Home Assistant and filtered out.
* Does not support teach-in telegrams.

#### Configuration 
1. Specify the type of gateway in the configuration (/homeassistant/configuration.yaml) in Home Assistant.
2. Enter your devices. I recommend to use a baseId and add the device id so that you don't get confused with all the addresses.

```
eltako:
  gateway:
    device: fam14

  light:
  - id: FF-AA-00-01         # internal address from PCT14
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: 00-00-B0-01       # baseId (00-00-B0-00) + sender id (0-127)
      eep: A5-38-08

```



### [**Eltako FGW14-USB**](https://www.eltako.com/en/product/professional-smart-home-en/series-14-rs485-bus-rail-mounted-devices-for-the-centralised-wireless-building-installation/fgw14-usb/)

<img src="./FGW14-USB.jpg" height=100 > 

```
eltako:
  gateway:
    device: fgw14usb

  light:
  - id: FF-AA-00-01         # internal address from PCT14
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: 00-00-B0-01       # baseId (00-00-B0-00) + sender id (0-127)
      eep: A5-38-08

```


### [**Eltako FAM-USB**](https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/)

FAM-USB is a usb device which can receive and send ESP2 telegrams. You can use it as gateway in Home Assistant to receive information and to control your actuators.  

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
2. Find out your baseId (start address for sender addresses). Use [DolphinStudio](https://www.enocean.com/de/produkt/dolphinstudio/?ts=1701468463) to read meta data from the chip.
   In this example we use FF-80-00-00 as start address.
   <img src="./DoplhinStudio_baseId.png">
3. If your actuator is on a bus behind FAM14 find out the baseId of FAM14. Use [PCT14](https://www.eltako.com/en/software-pct14/) to read the meta information of FAM14.
   In this example we use FF-AA-00-00
   <img src="./FAM14_baseId.png">
4. For all actuators on the bus take the FAM14 baseId and add the internal address. For decentralized actuators just take their addresses.
5. For all senders take the baseId of FAM-USB and add a number between 0-127. 

```
eltako:
  gateway:
    device: fam-usb

  light:
  - id: FF-AA-00-01         # baseId of FAM14 + internal address
    eep: M5-38-08
    name: FSR14_4x - 1
    sender:
      id: FF-80-00-01       # baseId of FAM-USB + sender id (0-127)
      eep: A5-38-08

```

### [**EnOcean GmbH USB300**](https://www.enocean.com/en/product/usb-300/)

FAM-USB is a usb device which can receive and send **ESP3** telegrams. 

**CURRENTLY NOT SUPPORTED AS HOME ASSISTANT GATEWAY!!!**

If you want to use it anyway check out the [EnOcean Integration](https://www.home-assistant.io/integrations/enocean/).

<img src="./USB300.jpg" height=100>