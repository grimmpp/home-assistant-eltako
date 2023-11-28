# Window Sensor Setup by using FTS14EM

## Hardware Setup
* FTS14EM is connected on eltako bus. (Among other devices there is FAM14 and a FGW14-USB on the bus)
* 24V DC power supply for the sensors
* Window sensor (for tests you can use a regular switch)

### Wiring
* 24V DC power supply +  <--connected-to--> window sensor
* window sensor <--connected-to--> FTS14EM Port 1
* FTS14EM port - <--connected-to--> 24 DC power supply

## Device setup
FTS14EM Specs: [Manual](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FTS14EM_30014060-3_gb.pdf) [Datasheet](https://www.eltako.com/fileadmin/downloads/en/_datasheets/Datasheet_FTS14EM.pdf)

### Activate the inputs for window/door contacts 
Turn the upper rotary switch within
3 seconds 5 times to the left stop, the LED
goes on during 4 seconds.

### Switch Positions
1. Turn upper rotary switch in **position 0**.
2. Turn bottom rotary switch in **position UT 1**.

## Home Assistant Configuration
```
eltako:
  binary_sensor:
    - id: "00-00-10-01"
      eep: "D5-00-01"
      name: window
      device_class: window
      invert-signal: False   # optional, default=False
```