# Supported devices and EEPs

*This page is generated from the code by [`generate_docs.py`](../generate_docs.py) &ndash; do not edit it by hand.*

The integration knows **240 device types** and **71 EnOcean Equipment Profiles**, of which **60** can become a Home Assistant entity on one of **6 platforms**. It is not limited to ELTAKO hardware - any device which speaks one of these profiles works.

The **Help** page of the web ui shows the same lists for the version you actually run.

## Platforms

A device is configured for the platform which matches what it does. The platform decides which
EEPs are accepted - anything else is rejected by the configuration check.

| Platform | What it covers | EEP of the device | Sender EEP (what Home Assistant sends) |
| --- | --- | --- | --- |
| **binary sensor** | Contacts, rocker switches, occupancy and water sensors - everything with a state of on/off. | `A5-07-01`, `A5-07-02`, `A5-07-03`, `A5-08-01`, `A5-14-09`, `A5-14-0A`, `A5-30-01`, `A5-30-03`, `D5-00-01`, `F6-01-01`, `F6-02-01`, `F6-02-02`, `F6-05-01`, `F6-05-02`, `F6-10-00` | &ndash; |
| **[climate](heating-and-cooling/readme.md)** | Heating and cooling: room thermostats and the actuators they control. | `A5-10-06` | `A5-10-06`, `F6-02-01`, `F6-02-02` |
| **[cover](relays-and-switches/readme.md)** | Blinds and shutters incl. travel times and tilt. | `G5-3F-7F` | `H5-3F-7F` |
| **[light](lights-tutorial/readme.md)** | Switchable and dimmable lights. | `A5-38-08`, `M5-38-08` | `A5-38-08`, `F6-02-01`, `F6-02-02` |
| **sensor** | Measured values: temperature, humidity, brightness, air quality, meter readings, weather. | `A5-02-01`, `A5-02-02`, `A5-02-03`, `A5-02-04`, `A5-02-05`, `A5-02-06`, `A5-02-07`, `A5-02-08`, `A5-02-09`, `A5-02-0A`, `A5-02-0B`, `A5-02-10`, `A5-02-11`, `A5-02-12`, `A5-02-13`, `A5-02-14`, `A5-02-15`, `A5-02-16`, `A5-02-17`, `A5-02-18`, `A5-02-19`, `A5-02-1A`, `A5-02-1B`, `A5-02-20`, `A5-02-30`, `A5-04-01`, `A5-04-02`, `A5-04-03`, `A5-06-01`, `A5-06-02`, `A5-06-03`, `A5-07-01`, `A5-07-02`, `A5-07-03`, `A5-08-01`, `A5-09-04`, `A5-09-05`, `A5-09-0C`, `A5-10-03`, `A5-10-06`, `A5-10-12`, `A5-12-01`, `A5-12-02`, `A5-12-03`, `A5-13-01`, `A5-20-04`, `F6-10-00` | &ndash; |
| **[switch](relays-and-switches/readme.md)** | Relays and everything else which is switched on and off. | `F6-02-01`, `F6-02-02`, `M5-38-08` | `A5-38-08`, `F6-02-01`, `F6-02-02` |

## Devices

Hardware types the integration knows by name. Selecting one in the device form of the web ui
prefills its EEP, sender EEP and platform, and *addresses* is how many bus addresses a device
occupies (a four channel actuator takes four). Devices which are not listed here still work as
long as they speak one of the profiles below.

| Device | Brand | What it is | Connection | Addresses | Platform | EEP | Sender EEP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **DSZ14DRS** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **DSZ14WDRS** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **F1FT65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **F1T55E** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **F1T65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **F2FT65** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2FT65B** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2FZT65B** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2L14** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **F2T55E** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2T55EB** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2T65** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2T65B** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2ZT55E** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F2ZT65** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F3Z14D** | ELTAKO | Electricity/Gas/Water Meter | RS485 bus | 3 | sensor | `A5-12-01`, `A5-12-02`, `A5-12-03` | &ndash; |
| **F4FT65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4FT65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4HK14** | ELTAKO | Heating/Cooling (4 channels) | RS485 bus | 4 | climate | `A5-10-06` | `A5-10-06` |
| **F4PT** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4PT55** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4SR14-LED** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **F4SR14_LED** | ELTAKO | Relay for LED (4 channels) | RS485 bus | 4 | light | `M5-38-08` | `A5-38-08` |
| **F4T55B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4T55E** | ELTAKO | Wireless 4-way pushbutton (E-Design55) | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F4T55EB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4T65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F4T65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **F6T55B** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **F6T65B** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FABH130** | ELTAKO | Occupancy sensor | wireless | 1 | binary_sensor | `A5-07-01` | &ndash; |
| **FABH65S** | ELTAKO | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FAE14** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FAE14LPR** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FAE14SSR** | ELTAKO | Heating/Cooling | RS485 bus | 2 | climate | `A5-10-06` | `A5-10-06` |
| **FAH65S** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-06-01` | &ndash; |
| **FASM60** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-10-00` | &ndash; |
| **FB55B** | ELTAKO | Temperature sensor | wireless | 1 | sensor, binary_sensor | `A5-07-01`, `A5-08-01` | &ndash; |
| **FB55EB** | ELTAKO | Occupancy sensor | wireless | 1 | binary_sensor | `A5-07-01` | &ndash; |
| **FB65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor, binary_sensor | `A5-07-01`, `A5-08-01` | &ndash; |
| **FBH55SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor, binary_sensor | `A5-04-03`, `A5-07-01`, `A5-08-01` | &ndash; |
| **FBH65** | ELTAKO | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FBH65S** | ELTAKO | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FBH65SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor, binary_sensor | `A5-04-03`, `A5-07-01`, `A5-08-01` | &ndash; |
| **FBH65TF** | ELTAKO | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FBHF65SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor, binary_sensor | `A5-04-03`, `A5-07-01`, `A5-08-01` | &ndash; |
| **FCO2TF65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-09-04` | &ndash; |
| **FCO2TS** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-09-04` | &ndash; |
| **FD2G14** | ELTAKO | Dali Gateway | RS485 bus | 16 | light | `A5-38-08` | `A5-38-08` |
| **FD62NP-230V** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FD62NPN-230V** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDG14** | ELTAKO | Dali Gateway | RS485 bus | 16 | light | `A5-38-08` | `A5-38-08` |
| **FDG71** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDG71L** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDH62** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDT55B** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDT55EB** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDT65B** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDTF65B** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FET55E** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **FF8** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FFG7B** | ELTAKO | Window/door contact | wireless | 1 | binary_sensor | `A5-14-09`, `F6-10-00` | &ndash; |
| **FFGB-hg** | ELTAKO | Contact and vibration sensor | wireless | 1 | binary_sensor | `A5-14-03`, `A5-14-05`, `A5-14-07`, `A5-14-08`, `A5-14-09`, `A5-14-0A` | &ndash; |
| **FFKB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `D5-00-01` | &ndash; |
| **FFR14** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FFT55B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FFT60** | ELTAKO | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02` | &ndash; |
| **FFT60SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FFT65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FFTE** | ELTAKO | Window/door contact | wireless | 1 | binary_sensor | `F6-10-00` | &ndash; |
| **FFTF65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FGW14** | ELTAKO | Bus Gateway | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FHD60SB** | ELTAKO | Twilight and daylight sensor | wireless | 1 | sensor | `A5-06-01` | &ndash; |
| **FHD62NP** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FHD65SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-06-02` | &ndash; |
| **FHK14** | ELTAKO | Heating/Cooling | RS485 bus | 2 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61-230V** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61SSR** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61SSR-230V** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61U** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHK61U-230V** | ELTAKO | Heating/Cooling | wireless | 1 | climate | `A5-10-06` | `A5-10-06` |
| **FHMB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-30-03` | &ndash; |
| **FHS2** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FHS4** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FIH65B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-06-02` | &ndash; |
| **FIH65S** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-06-01` | &ndash; |
| **FJ62/12-36V DC** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FJ62NP-230V** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FKD** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **FKLD61** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FKS-H** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-20-04` | &ndash; |
| **FL62** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FL62-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FL62NP** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FL62NP-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FLC61** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FLC61NP** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FLC61NP-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FLD61** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FLGTF** | ELTAKO | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02`, `A5-09-0C` | &ndash; |
| **FLGTF55** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-09-0C` | &ndash; |
| **FLGTF65** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-09-0C` | &ndash; |
| **FLT58** | ELTAKO | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02`, `A5-09-05` | &ndash; |
| **FMH1W** | ELTAKO | Wireless single button | wireless | 1 | binary_sensor | `F6-01-01` | &ndash; |
| **FMH2** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FMH2S** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FMH4** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FMH4S** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FMH8** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FMMS44SB** | ELTAKO | Room controller with environment data | wireless | 1 | sensor | `A5-02-05`, `A5-04-01`, `A5-04-03`, `A5-06-02`, `A5-06-03`, `D2-00-01` | &ndash; |
| **FMS14** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FMS55ESB** | ELTAKO | Indoor multisensor with contact | wireless | 1 | sensor | `A5-02-05`, `A5-04-01`, `A5-04-03`, `A5-06-02`, `A5-06-03`, `D2-14-41` | &ndash; |
| **FMS55SB** | ELTAKO | Indoor multisensor | wireless | 1 | sensor | `A5-02-05`, `A5-04-01`, `A5-04-03`, `A5-06-02`, `A5-06-03`, `D2-14-40` | &ndash; |
| **FMS61** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FMS61NP-230V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FMS65ESB** | ELTAKO | Indoor multisensor with contact | wireless | 1 | sensor | `A5-02-05`, `A5-04-01`, `A5-04-03`, `A5-06-02`, `A5-06-03`, `D2-14-41` | &ndash; |
| **FMSR14** | ELTAKO | Multisensor relay | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FMZ14** | ELTAKO | Relay (multifunction) | RS485 bus | 1 | light | `M5-38-08` | `F6-02-01` |
| **FMZ61** | ELTAKO | Relay (multifunction) | wireless | 1 | light | `M5-38-08` | `F6-02-01` |
| **FMZ61-230V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FNS55B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **FNS55EB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **FNS65EB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-01-01` | &ndash; |
| **FPE-1** | ELTAKO | Wireless pushbutton | wireless | 1 | binary_sensor | `F6-01-01` | &ndash; |
| **FR62** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FR62-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FR62NP** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FR62NP-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FRGBW71L** | ELTAKO | Cover actuator | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FRWB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-30-03` | &ndash; |
| **FS55** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FS55E** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FS65E** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FSB14** | ELTAKO | Cover | RS485 bus | 2 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61-230V** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61NP** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61NP-230V** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB71** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB71NP** | ELTAKO | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSDG14** | ELTAKO | Electricity Meter | RS485 bus | 1 | sensor | `A5-12-01` | &ndash; |
| **FSG14_1_10V** | ELTAKO | Dimming for electr. ballasts (1-10V) | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSG71/1-10V** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSHA** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSHA-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSM14** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-10-00` | &ndash; |
| **FSM60B** | ELTAKO | Digital input with battery status | wireless | 1 | binary_sensor | `A5-30-01` | &ndash; |
| **FSM61** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-10-00` | &ndash; |
| **FSR14** | ELTAKO | Relay | RS485 bus | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR14M_2x** | ELTAKO | Relay (2 channels, with metering) | RS485 bus | 2 | light, sensor | `A5-12-01`, `M5-38-08` | `A5-38-08` |
| **FSR14SSR** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSR14_1x** | ELTAKO | Relay (1 channel) | RS485 bus | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR14_2x** | ELTAKO | Relay (2 channels) | RS485 bus | 2 | light | `M5-38-08` | `A5-38-08` |
| **FSR14_4x** | ELTAKO | Relay (4 channels) | RS485 bus | 4 | light | `M5-38-08` | `A5-38-08` |
| **FSR61** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61/8-24V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSR61/8-24V UC** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61G** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61G-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61LN** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61LN-230V** | ELTAKO | Relay | wireless | 2 | light | `M5-38-08` | `A5-38-08` |
| **FSR61NP** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61NP-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61VA** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **FSR61VA-10A** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **FSR70S** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR70S-230V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSR71** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR71NP-4x** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSSA** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSSA-230V** | ELTAKO | Socket switch actuator | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSSG** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSTAP** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-03` | &ndash; |
| **FSU14** | ELTAKO | Clock/timer module | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FSU55D/230V** | ELTAKO | Clock and weekday transmitter | wireless | 1 | sensor | `A5-13-04` | &ndash; |
| **FSU65D/230V** | ELTAKO | Clock and weekday transmitter | wireless | 1 | sensor | `A5-13-04` | &ndash; |
| **FSUD** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSUD-230V** | ELTAKO | Cover | wireless | 1 | cover, light | `A5-38-08`, `G5-3F-7F` | `A5-38-08`, `H5-3F-7F` |
| **FSVA** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSVA-230V** | ELTAKO | Electricity meter | wireless | 1 | sensor, light | `A5-12-01`, `M5-38-08` | `A5-38-08` |
| **FSVA-230V-10A** | ELTAKO | Socket switch actuator | wireless | 1 | light, sensor | `A5-12-01`, `M5-38-08` | `A5-38-08` |
| **FT4F** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `F6-02-01` | &ndash; |
| **FT55** | ELTAKO | Wireless 4-way pushbutton | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FTAF65D** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTF65S** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-02-05` | &ndash; |
| **FTFB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FTFSB** | ELTAKO | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02`, `A5-04-03` | &ndash; |
| **FTK** | ELTAKO | Window/door contact | wireless | 1 | binary_sensor, sensor | `D5-00-01`, `F6-10-00` | &ndash; |
| **FTKB-RW** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `D5-00-01` | &ndash; |
| **FTKB-gr** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `D5-00-01` | &ndash; |
| **FTKE** | ELTAKO | Window/door contact | wireless | 1 | binary_sensor | `F6-10-00` | &ndash; |
| **FTN14** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FTN61** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FTN61NP-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FTR55DSB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR55HB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR55SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR65DSB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR65HB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR65HS** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR65SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTR78S** | ELTAKO | Thermostat | wireless | 1 | sensor | `A5-10-03` | &ndash; |
| **FTR86B** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTRF65HB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTRF65SB** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06` | &ndash; |
| **FTS14EM** | ELTAKO | Wired inputs (switches, contacts) | RS485 bus | 1 | binary_sensor | `A5-08-01`, `D5-00-01`, `F6-02-01`, `F6-02-02`, `F6-10-00` | &ndash; |
| **FTTB** | ELTAKO | Wireless pushbutton | wireless | 1 | binary_sensor | `F6-01-01` | &ndash; |
| **FUA12-230V** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FUD14** | ELTAKO | Light dimmer | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD14_800W** | ELTAKO | Light dimmer | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NP** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NP-230V** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NPN** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NPN-230V** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD70S** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD70S-230V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD71** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD71L** | ELTAKO | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUTH** | ELTAKO | Temperature sensor and controller | wireless | 1 | sensor | `A5-10-06`, `A5-10-12` | &ndash; |
| **FUTH55D** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06`, `A5-10-12` | &ndash; |
| **FUTH65D** | ELTAKO | Temperature sensor | wireless | 1 | sensor | `A5-10-06`, `A5-10-12` | &ndash; |
| **FWG14MS** | ELTAKO | Weather Station Gateway | RS485 bus | 1 | sensor | `A5-13-01` | &ndash; |
| **FWS61** | ELTAKO | Weather Station | wireless | 1 | sensor | `A5-13-01`, `A5-13-02` | &ndash; |
| **FWS81** | ELTAKO | Water leakage detector | wireless | 1 | binary_sensor | `F6-05-01` | &ndash; |
| **FWWKW71L** | ELTAKO | Cover actuator | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FWZ12** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **FWZ14** | ELTAKO | Electricity meter | wireless | 1 | sensor | `A5-12-01` | &ndash; |
| **FWZ14_65A** | ELTAKO | Electricity Meter | RS485 bus | 1 | sensor | `A5-12-01` | &ndash; |
| **FZK14** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FZK61NP** | ELTAKO | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FZK61NP-230V** | ELTAKO | Light actuator | wireless | 1 | light | `A5-38-08`, `M5-38-08` | `A5-38-08` |
| **FZS65** | ELTAKO | Smoke detector | wireless | 1 | binary_sensor | `F6-05-02` | &ndash; |
| **FZT55** | ELTAKO | Wireless rocker switch | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **MS** | ELTAKO | Weather Station | wireless | 1 | sensor | `A5-13-01` | &ndash; |
| **WMS** | ELTAKO | Weather Station | wireless | 1 | sensor | `A5-13-01` | &ndash; |
| **eTronic** | ELTAKO | Contact sensor | wireless | 1 | binary_sensor | `A5-14-01` | &ndash; |
| **mTronic** | ELTAKO | Window/door contact | wireless | 1 | binary_sensor | `A5-14-0A` | &ndash; |

## EnOcean Equipment Profiles (EEP)

The profile decides how the payload of a telegram is interpreted. *Recording only* means the
telegram is decoded, logged and can be analysed, but no platform turns it into an entity yet.

| EEP | What it is | Entity platform | Usable as sender for | Devices |
| --- | --- | --- | --- | --- |
| `A5-02-01` | Temperature sensor, -40 to 0 °C. | sensor | &ndash; | &ndash; |
| `A5-02-02` | Temperature sensor, -30 to 10 °C. | sensor | &ndash; | &ndash; |
| `A5-02-03` | Temperature sensor, -20 to 20 °C. | sensor | &ndash; | &ndash; |
| `A5-02-04` | Temperature sensor, -10 to 30 °C. | sensor | &ndash; | &ndash; |
| `A5-02-05` | Temperature Sensor, 0 to 40 °C (e.g. EnOcean STM 330). | sensor | &ndash; | FMMS44SB, FMS55ESB, FMS55SB, FMS65ESB, FTF65S |
| `A5-02-06` | Temperature sensor, 10 to 50 °C. | sensor | &ndash; | &ndash; |
| `A5-02-07` | Temperature sensor, 20 to 60 °C. | sensor | &ndash; | &ndash; |
| `A5-02-08` | Temperature sensor, 30 to 70 °C. | sensor | &ndash; | &ndash; |
| `A5-02-09` | Temperature sensor, 40 to 80 °C. | sensor | &ndash; | &ndash; |
| `A5-02-0A` | Temperature sensor, 50 to 90 °C. | sensor | &ndash; | &ndash; |
| `A5-02-0B` | Temperature sensor, 60 to 100 °C. | sensor | &ndash; | &ndash; |
| `A5-02-10` | Temperature sensor, -60 to 20 °C. | sensor | &ndash; | &ndash; |
| `A5-02-11` | Temperature sensor, -50 to 30 °C. | sensor | &ndash; | &ndash; |
| `A5-02-12` | Temperature sensor, -40 to 40 °C. | sensor | &ndash; | &ndash; |
| `A5-02-13` | Temperature sensor, -30 to 50 °C. | sensor | &ndash; | &ndash; |
| `A5-02-14` | Temperature sensor, -20 to 60 °C. | sensor | &ndash; | &ndash; |
| `A5-02-15` | Temperature sensor, -10 to 70 °C. | sensor | &ndash; | &ndash; |
| `A5-02-16` | Temperature sensor, 0 to 80 °C. | sensor | &ndash; | &ndash; |
| `A5-02-17` | Temperature sensor, 10 to 90 °C. | sensor | &ndash; | &ndash; |
| `A5-02-18` | Temperature sensor, 20 to 100 °C. | sensor | &ndash; | &ndash; |
| `A5-02-19` | Temperature sensor, 30 to 110 °C. | sensor | &ndash; | &ndash; |
| `A5-02-1A` | Temperature sensor, 40 to 120 °C. | sensor | &ndash; | &ndash; |
| `A5-02-1B` | Temperature sensor, 50 to 130 °C. | sensor | &ndash; | &ndash; |
| `A5-02-20` | 10-bit temperature sensor, -10 to +41.2 °C. | sensor | &ndash; | &ndash; |
| `A5-02-30` | 10-bit temperature sensor, -40 to +62.3 °C. | sensor | &ndash; | &ndash; |
| `A5-04-01` | Temperature and Humidity Sensor | sensor | &ndash; | FMMS44SB, FMS55ESB, FMS55SB, FMS65ESB |
| `A5-04-02` | Temperature and Humidity Sensor | sensor | &ndash; | FFT55B, FFT60, FFT60SB, FFT65B, FFTF65B, FLGTF, FLGTF55, FLGTF65, FLT58, FTFB, FTFSB |
| `A5-04-03` | Temperature and Humidity Sensor | sensor | &ndash; | FBH55SB, FBH65SB, FBHF65SB, FFT55B, FFT60SB, FFT65B, FFTF65B, FMMS44SB, FMS55ESB, FMS55SB, FMS65ESB, FTFB, FTFSB |
| `A5-06-01` | Brightness Twilight Sensor | sensor | &ndash; | FAH65S, FHD60SB, FIH65S |
| `A5-06-02` | ELTAKO FHD65SB light and supply-voltage telegram. | sensor | &ndash; | FHD65SB, FIH65B, FMMS44SB, FMS55ESB, FMS55SB, FMS65ESB |
| `A5-06-03` | 10-bit light sensor with 0 to 1000 lx range. | sensor | &ndash; | FMMS44SB, FMS55ESB, FMS55SB, FMS65ESB |
| `A5-07-01` | Occupancy Sensor | binary_sensor, sensor | &ndash; | FABH130, FB55B, FB55EB, FB65B, FBH55SB, FBH65SB, FBHF65SB |
| `A5-07-02` | Occupancy with supply voltage monitor (standard EEP A5-07-02). | binary_sensor, sensor | &ndash; | &ndash; |
| `A5-07-03` | Occupancy with supply voltage monitor and 10-bit illumination. | binary_sensor, sensor | &ndash; | &ndash; |
| `A5-08-01` | Light, Temperature and Occupancy sensor | binary_sensor, sensor | &ndash; | FABH65S, FB55B, FB65B, FBH55SB, FBH65, FBH65S, FBH65SB, FBH65TF, FBHF65SB, FTS14EM |
| `A5-09-04` | CO2, Temperature and Humidity Sensor | sensor | &ndash; | FCO2TF65, FCO2TS |
| `A5-09-05` | ELTAKO VOC sensor telegram used by FLT58. | sensor | &ndash; | FLT58 |
| `A5-09-0C` | Air quality sensor | sensor | &ndash; | FLGTF, FLGTF55, FLGTF65 |
| `A5-10-03` | Thermostat - current and desired temperature | sensor | &ndash; | FSTAP, FTR78S |
| `A5-10-06` | Heating and Cooling | climate, sensor | climate | F4HK14, FAE14LPR, FAE14SSR, FHK14, FHK61, FHK61-230V, FHK61SSR, FHK61SSR-230V, FHK61U, FHK61U-230V, FTAF65D, FTR55DSB, FTR55HB, FTR55SB, FTR65DSB, FTR65HB, FTR65HS, FTR65SB, FTR86B, FTRF65HB, FTRF65SB, FUTH, FUTH55D, FUTH65D |
| `A5-10-12` | Temperature Controller Command | sensor | &ndash; | FUTH, FUTH55D, FUTH65D |
| `A5-12-01` | Automated Meter Reading - Electricity | sensor | &ndash; | DSZ14DRS, DSZ14WDRS, F3Z14D, FSDG14, FSR14M_2x, FSR61VA, FSR61VA-10A, FSVA-230V, FSVA-230V-10A, FWZ12, FWZ14, FWZ14_65A |
| `A5-12-02` | Automated Meter Reading - Gas | sensor | &ndash; | F3Z14D |
| `A5-12-03` | Automated Meter Reading - Water | sensor | &ndash; | F3Z14D |
| `A5-13-01` | Weather station | sensor | &ndash; | FWG14MS, FWS61, MS, WMS |
| `A5-13-02` | Sun-position telegram with west, south and east light sensors. | *recording only* | *recording only* | FWS61 |
| `A5-13-04` | Clock and weekday telegram used by ELTAKO time transmitters. | *recording only* | *recording only* | FSU55D/230V, FSU65D/230V |
| `A5-14-01` | Contact and supply voltage sensor. | *recording only* | *recording only* | eTronic |
| `A5-14-03` | Contact and vibration sensor. | *recording only* | *recording only* | FFGB-hg |
| `A5-14-05` | Vibration sensor with supply-voltage monitoring. | *recording only* | *recording only* | FFGB-hg |
| `A5-14-07` | Door and lock contact sensor. | *recording only* | *recording only* | FFGB-hg |
| `A5-14-08` | Door, lock and vibration contact sensor. | *recording only* | *recording only* | FFGB-hg |
| `A5-14-09` | ELTAKO FFGB window contact status. | binary_sensor | &ndash; | FFG7B, FFGB-hg |
| `A5-14-0A` | ELTAKO mTronic window contact status with alarm flag. | binary_sensor | &ndash; | FFGB-hg, mTronic |
| `A5-20-04` | ELTAKO FKS-H valve and temperature telegram. | sensor | &ndash; | FKS-H |
| `A5-30-01` | Digital Input with battery status | binary_sensor | &ndash; | FSM60B |
| `A5-30-03` | Digital Inputs | binary_sensor | &ndash; | FHMB, FRWB |
| `A5-38-08` | Central Command Gateway | light | light, switch | F2L14, F4SR14-LED, F4SR14_LED, FAE14, FD2G14, FD62NP-230V, FD62NPN-230V, FDG14, FDG71, FDG71L, FDH62, FDT55B, FDT55EB, FDT65B, FDTF65B, FFR14, FHD62NP, FKLD61, FL62, FL62-230V, FL62NP, FL62NP-230V, FLC61, FLC61NP, FLC61NP-230V, FLD61, FMS14, FMS61, FMS61NP-230V, FMZ61-230V, FR62, FR62-230V, FR62NP, FR62NP-230V, FSG14_1_10V, FSG71/1-10V, FSHA, FSHA-230V, FSR14, FSR14M_2x, FSR14SSR, FSR14_1x, FSR14_2x, FSR14_4x, FSR61, FSR61-230V, FSR61/8-24V, FSR61/8-24V UC, FSR61G, FSR61G-230V, FSR61LN, FSR61LN-230V, FSR61NP, FSR61NP-230V, FSR70S, FSR70S-230V, FSR71, FSR71NP-4x, FSSA, FSSA-230V, FSSG, FSUD, FSUD-230V, FSVA, FSVA-230V, FSVA-230V-10A, FTN14, FTN61, FTN61NP-230V, FUA12-230V, FUD14, FUD14_800W, FUD61, FUD61NP, FUD61NP-230V, FUD61NPN, FUD61NPN-230V, FUD70S, FUD70S-230V, FUD71, FUD71L, FZK14, FZK61NP, FZK61NP-230V |
| `D2-00-01` | RCP/window handle controller with temperature and environment data. | *recording only* | *recording only* | FMMS44SB |
| `D2-14-40` | Indoor multisensor proposal profile without a contact bit. | *recording only* | *recording only* | FMS55SB |
| `D2-14-41` | Indoor multisensor proposal profile with a window/contact bit. | *recording only* | *recording only* | FMS55ESB, FMS65ESB |
| `D5-00-01` | Single input contact | binary_sensor | &ndash; | FFKB, FTK, FTKB-RW, FTKB-gr, FTS14EM |
| `F6-01-01` | one button switch | binary_sensor | &ndash; | F1FT65, F1T55E, F1T65, FET55E, FKD, FMH1W, FNS55B, FNS55EB, FNS65EB, FPE-1, FTTB |
| `F6-02-01` | 2-part Rocker switch, Application Style 1 (European, bottom switches | binary_sensor, switch | climate, light, switch | F2FT65, F2FT65B, F2FZT65B, F2T55E, F2T55EB, F2T65, F2T65B, F2ZT55E, F2ZT65, F4FT65, F4FT65B, F4PT, F4PT55, F4T55B, F4T55E, F4T55EB, F4T65, F4T65B, F6T55B, F6T65B, FF8, FHS2, FHS4, FMH2, FMH2S, FMH4, FMH4S, FMH8, FMZ14, FMZ61, FS55, FS55E, FS65E, FT4F, FT55, FTS14EM, FZT55 |
| `F6-02-02` | 2-part Rocker switch, Application Style 2 (US, top switches on) | binary_sensor, switch | climate, light, switch | FTS14EM |
| `F6-05-01` | Water leakage sensor (e.g. ELTAKO FWS81). | binary_sensor | &ndash; | FWS81 |
| `F6-05-02` | Smoke detector status (e.g. ELTAKO FRW). | binary_sensor | &ndash; | FZS65 |
| `F6-10-00` | Windows handle | binary_sensor, sensor | &ndash; | FASM60, FFG7B, FFTE, FSM14, FSM61, FTK, FTKE, FTS14EM |
| `G5-3F-7F` | ELTAKO Shutters | cover | &ndash; | FJ62/12-36V DC, FJ62NP-230V, FRGBW71L, FSB14, FSB61, FSB61-230V, FSB61NP, FSB61NP-230V, FSB71, FSB71NP, FSUD-230V, FWWKW71L |
| `H5-3F-7F` | ELTAKO Shutter Command | &ndash; | cover | FJ62/12-36V DC, FJ62NP-230V, FRGBW71L, FSB14, FSB61, FSB61-230V, FSB61NP, FSB61NP-230V, FSB71, FSB71NP, FSUD-230V, FWWKW71L |
| `M5-38-08` | ELTAKO Gateway Switching - This is implemented pretty rudimentary | light, switch | &ndash; | F2L14, F4SR14-LED, F4SR14_LED, FAE14, FFR14, FL62, FL62-230V, FL62NP, FL62NP-230V, FLC61NP-230V, FMS14, FMZ14, FMZ61, FR62, FR62-230V, FR62NP, FR62NP-230V, FSHA, FSHA-230V, FSR14, FSR14M_2x, FSR14_1x, FSR14_2x, FSR14_4x, FSR61, FSR61-230V, FSR61/8-24V UC, FSR61G, FSR61G-230V, FSR61LN, FSR61LN-230V, FSR61NP, FSR61NP-230V, FSR70S, FSR71, FSR71NP-4x, FSSA, FSSA-230V, FSSG, FSVA, FSVA-230V, FSVA-230V-10A, FTN14, FTN61, FTN61NP-230V, FUA12-230V, FZK61NP, FZK61NP-230V |

## Gateways

See [the readme](../README.md#supported-gateways) and
[docs/gateways](gateways/readme.md).

