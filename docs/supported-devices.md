# Supported devices and EEPs

*This page is generated from the code by [`generate_docs.py`](../generate_docs.py) &ndash; do not edit it by hand.*

The integration knows **68 device types** and **26 EnOcean Equipment Profiles**, of which **24** can become a Home Assistant entity on one of **6 platforms**. It is not limited to Eltako hardware - any device which speaks one of these profiles works.

The **Help** page of the web ui shows the same lists for the version you actually run.

## Platforms

A device is configured for the platform which matches what it does. The platform decides which
EEPs are accepted - anything else is rejected by the configuration check.

| Platform | What it covers | EEP of the device | Sender EEP (what Home Assistant sends) |
| --- | --- | --- | --- |
| **binary sensor** | Contacts, rocker switches, occupancy and water sensors - everything with a state of on/off. | `A5-07-01`, `A5-08-01`, `A5-30-01`, `A5-30-03`, `D5-00-01`, `F6-01-01`, `F6-02-01`, `F6-02-02`, `F6-10-00` | &ndash; |
| **[climate](heating-and-cooling/readme.md)** | Heating and cooling: room thermostats and the actuators they control. | `A5-10-06` | `A5-10-06`, `F6-02-01`, `F6-02-02` |
| **[cover](relays-and-switches/readme.md)** | Blinds and shutters incl. travel times and tilt. | `G5-3F-7F` | `H5-3F-7F` |
| **[light](lights-tutorial/readme.md)** | Switchable and dimmable lights. | `A5-38-08`, `M5-38-08` | `A5-38-08`, `F6-02-01`, `F6-02-02` |
| **sensor** | Measured values: temperature, humidity, brightness, air quality, meter readings, weather. | `A5-04-01`, `A5-04-02`, `A5-04-03`, `A5-06-01`, `A5-07-01`, `A5-08-01`, `A5-09-0C`, `A5-10-03`, `A5-10-06`, `A5-10-12`, `A5-12-01`, `A5-12-02`, `A5-12-03`, `A5-13-01`, `F6-10-00` | &ndash; |
| **[switch](relays-and-switches/readme.md)** | Relays and everything else which is switched on and off. | `F6-02-01`, `F6-02-02`, `M5-38-08` | `A5-38-08`, `F6-02-01`, `F6-02-02` |

## Devices

Hardware types the integration knows by name. Selecting one in the device form of the web ui
prefills its EEP, sender EEP and platform, and *addresses* is how many bus addresses a device
occupies (a four channel actuator takes four). Devices which are not listed here still work as
long as they speak one of the profiles below.

| Device | Brand | What it is | Connection | Addresses | Platform | EEP | Sender EEP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **F3Z14D** | Eltako | Electricity/Gas/Water Meter | RS485 bus | 3 | sensor | `A5-12-01`, `A5-12-02`, `A5-12-03` | &ndash; |
| **F4HK14** | Eltako | Heating/Cooling (4 channels) | RS485 bus | 4 | climate | `A5-10-06` | `A5-10-06` |
| **F4SR14_LED** | Eltako | Relay for LED (4 channels) | RS485 bus | 4 | light | `M5-38-08` | `A5-38-08` |
| **F4T55E** | Eltako | Wireless 4-way pushbutton (E-Design55) | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FABH65S** | Eltako | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FAE14SSR** | Eltako | Heating/Cooling | RS485 bus | 2 | climate | `A5-10-06` | `A5-10-06` |
| **FB55EB** | Eltako | Occupancy sensor | wireless | 1 | binary_sensor | `A5-07-01` | &ndash; |
| **FBH65** | Eltako | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FBH65S** | Eltako | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FBH65TF** | Eltako | Light, temperature and occupancy sensor | wireless | 1 | sensor | `A5-08-01` | &ndash; |
| **FD2G14** | Eltako | Dali Gateway | RS485 bus | 16 | light | `A5-38-08` | `A5-38-08` |
| **FD62NP-230V** | Eltako | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FD62NPN-230V** | Eltako | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FDG14** | Eltako | Dali Gateway | RS485 bus | 16 | light | `A5-38-08` | `A5-38-08` |
| **FFT60** | Eltako | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02` | &ndash; |
| **FFTE** | Eltako | Window/door contact | wireless | 1 | binary_sensor | `F6-10-00` | &ndash; |
| **FGW14** | Eltako | Bus Gateway | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FHD60SB** | Eltako | Twilight and daylight sensor | wireless | 1 | sensor | `A5-06-01` | &ndash; |
| **FHK14** | Eltako | Heating/Cooling | RS485 bus | 2 | climate | `A5-10-06` | `A5-10-06` |
| **FJ62/12-36V DC** | Eltako | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FJ62NP-230V** | Eltako | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FL62-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FL62NP-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FLC61NP-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FLGTF** | Eltako | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02`, `A5-09-0C` | &ndash; |
| **FLT58** | Eltako | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02` | &ndash; |
| **FMH1W** | Eltako | Wireless single button | wireless | 1 | binary_sensor | `F6-01-01` | &ndash; |
| **FMSR14** | Eltako | Multisensor relay | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FMZ14** | Eltako | Relay (multifunction) | RS485 bus | 1 | light | `M5-38-08` | `F6-02-01` |
| **FMZ61** | Eltako | Relay (multifunction) | wireless | 1 | light | `M5-38-08` | `F6-02-01` |
| **FR62-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FR62NP-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSB14** | Eltako | Cover | RS485 bus | 2 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61-230V** | Eltako | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSB61NP-230V** | Eltako | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSDG14** | Eltako | Electricity Meter | RS485 bus | 1 | sensor | `A5-12-01` | &ndash; |
| **FSG14_1_10V** | Eltako | Dimming for electr. ballasts (1-10V) | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FSM60B** | Eltako | Digital input with battery status | wireless | 1 | binary_sensor | `A5-30-01` | &ndash; |
| **FSR14** | Eltako | Relay | RS485 bus | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR14M_2x** | Eltako | Relay (2 channels, with metering) | RS485 bus | 2 | light, sensor | `A5-12-01`, `M5-38-08` | `A5-38-08` |
| **FSR14_1x** | Eltako | Relay (1 channel) | RS485 bus | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR14_2x** | Eltako | Relay (2 channels) | RS485 bus | 2 | light | `M5-38-08` | `A5-38-08` |
| **FSR14_4x** | Eltako | Relay (4 channels) | RS485 bus | 4 | light | `M5-38-08` | `A5-38-08` |
| **FSR61-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61/8-24V UC** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61G-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSR61LN-230V** | Eltako | Relay | wireless | 2 | light | `M5-38-08` | `A5-38-08` |
| **FSR61NP-230V** | Eltako | Relay | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSSA-230V** | Eltako | Socket switch actuator | wireless | 1 | light | `M5-38-08` | `A5-38-08` |
| **FSU14** | Eltako | Clock/timer module | RS485 bus |  | *detected only* | &ndash; | &ndash; |
| **FSUD-230V** | Eltako | Cover | wireless | 1 | cover | `G5-3F-7F` | `H5-3F-7F` |
| **FSVA-230V-10A** | Eltako | Socket switch actuator | wireless | 1 | light, sensor | `A5-12-01`, `M5-38-08` | `A5-38-08` |
| **FT55** | Eltako | Wireless 4-way pushbutton | wireless | 1 | binary_sensor | `F6-02-01` | &ndash; |
| **FTFSB** | Eltako | Temperature and Humidity Sensor | wireless | 1 | sensor | `A5-04-02` | &ndash; |
| **FTK** | Eltako | Window/door contact | wireless | 1 | binary_sensor | `F6-10-00` | &ndash; |
| **FTKE** | Eltako | Window/door contact | wireless | 1 | binary_sensor | `F6-10-00` | &ndash; |
| **FTR78S** | Eltako | Thermostat | wireless | 1 | sensor | `A5-10-03` | &ndash; |
| **FTS14EM** | Eltako | Wired inputs (switches, contacts) | RS485 bus | 1 | binary_sensor | `A5-08-01`, `D5-00-01`, `F6-02-01`, `F6-02-02`, `F6-10-00` | &ndash; |
| **FUD14** | Eltako | Light dimmer | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD14_800W** | Eltako | Light dimmer | RS485 bus | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NP-230V** | Eltako | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUD61NPN-230V** | Eltako | Light dimmer | wireless | 1 | light | `A5-38-08` | `A5-38-08` |
| **FUTH** | Eltako | Temperature sensor and controller | wireless | 1 | sensor | `A5-10-06`, `A5-10-12` | &ndash; |
| **FWG14MS** | Eltako | Weather Station Gateway | RS485 bus | 1 | sensor | `A5-13-01` | &ndash; |
| **FWS61** | Eltako | Weather Station | wireless | 1 | sensor | `A5-13-01` | &ndash; |
| **FWZ14_65A** | Eltako | Electricity Meter | RS485 bus | 1 | sensor | `A5-12-01` | &ndash; |
| **MS** | Eltako | Weather Station | wireless | 1 | sensor | `A5-13-01` | &ndash; |
| **WMS** | Eltako | Weather Station | wireless | 1 | sensor | `A5-13-01` | &ndash; |

## EnOcean Equipment Profiles (EEP)

The profile decides how the payload of a telegram is interpreted. *Recording only* means the
telegram is decoded, logged and can be analysed, but no platform turns it into an entity yet.

| EEP | What it is | Entity platform | Usable as sender for | Devices |
| --- | --- | --- | --- | --- |
| `A5-04-01` | Temperature and Humidity Sensor | sensor | &ndash; | &ndash; |
| `A5-04-02` | Temperature and Humidity Sensor | sensor | &ndash; | FFT60, FLGTF, FLT58, FTFSB |
| `A5-04-03` | Temperature and Humidity Sensor | sensor | &ndash; | &ndash; |
| `A5-06-01` | Brightness Twilight Sensor | sensor | &ndash; | FHD60SB |
| `A5-07-01` | Occupancy Sensor | binary_sensor, sensor | &ndash; | FB55EB |
| `A5-08-01` | Light, Temperature and Occupancy sensor | binary_sensor, sensor | &ndash; | FABH65S, FBH65, FBH65S, FBH65TF, FTS14EM |
| `A5-09-04` | CO2, Temperature and Humidity Sensor | *recording only* | *recording only* | &ndash; |
| `A5-09-0C` | Air quality sensor | sensor | &ndash; | FLGTF |
| `A5-10-03` | Thermostat - current and desired temperature | sensor | &ndash; | FTR78S |
| `A5-10-06` | Heating and Cooling | climate, sensor | climate | F4HK14, FAE14SSR, FHK14, FUTH |
| `A5-10-12` | Temperature Controller Command | sensor | &ndash; | FUTH |
| `A5-12-01` | Automated Meter Reading - Electricity | sensor | &ndash; | F3Z14D, FSDG14, FSR14M_2x, FSVA-230V-10A, FWZ14_65A |
| `A5-12-02` | Automated Meter Reading - Gas | sensor | &ndash; | F3Z14D |
| `A5-12-03` | Automated Meter Reading - Water | sensor | &ndash; | F3Z14D |
| `A5-13-01` | Weather station | sensor | &ndash; | FWG14MS, FWS61, MS, WMS |
| `A5-30-01` | Digital Input with battery status | binary_sensor | &ndash; | FSM60B |
| `A5-30-03` | Digital Inputs | binary_sensor | &ndash; | &ndash; |
| `A5-38-08` | Central Command Gateway | light | light, switch | F4SR14_LED, FD2G14, FD62NP-230V, FD62NPN-230V, FDG14, FL62-230V, FL62NP-230V, FLC61NP-230V, FR62-230V, FR62NP-230V, FSG14_1_10V, FSR14, FSR14M_2x, FSR14_1x, FSR14_2x, FSR14_4x, FSR61-230V, FSR61/8-24V UC, FSR61G-230V, FSR61LN-230V, FSR61NP-230V, FSSA-230V, FSVA-230V-10A, FUD14, FUD14_800W, FUD61NP-230V, FUD61NPN-230V |
| `D5-00-01` | Single input contact | binary_sensor | &ndash; | FTS14EM |
| `F6-01-01` | one button switch | binary_sensor | &ndash; | FMH1W |
| `F6-02-01` | 2-part Rocker switch, Application Style 1 (European, bottom switches | binary_sensor, switch | climate, light, switch | F4T55E, FMZ14, FMZ61, FT55, FTS14EM |
| `F6-02-02` | 2-part Rocker switch, Application Style 2 (US, top switches on) | binary_sensor, switch | climate, light, switch | FTS14EM |
| `F6-10-00` | Windows handle | binary_sensor, sensor | &ndash; | FFTE, FTK, FTKE, FTS14EM |
| `G5-3F-7F` | Eltako Shutters | cover | &ndash; | FJ62/12-36V DC, FJ62NP-230V, FSB14, FSB61-230V, FSB61NP-230V, FSUD-230V |
| `H5-3F-7F` | Eltako Shutter Command | &ndash; | cover | FJ62/12-36V DC, FJ62NP-230V, FSB14, FSB61-230V, FSB61NP-230V, FSUD-230V |
| `M5-38-08` | Eltako Gateway Switching - This is implemented pretty rudimentary | light, switch | &ndash; | F4SR14_LED, FL62-230V, FL62NP-230V, FLC61NP-230V, FMZ14, FMZ61, FR62-230V, FR62NP-230V, FSR14, FSR14M_2x, FSR14_1x, FSR14_2x, FSR14_4x, FSR61-230V, FSR61/8-24V UC, FSR61G-230V, FSR61LN-230V, FSR61NP-230V, FSSA-230V, FSVA-230V-10A |

## Gateways

See [the readme](../README.md#supported-gateways) and
[docs/gateways](gateways/readme.md).

