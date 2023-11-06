# Heating and Cooling

This documentation is about how to control a heating like a heat pump which is able to heat up in winter and to cool down in summer.

<img src="./HAClimatePanel.png" alt="Home Assistant Climate Panel" height="250"/>

In the following scenario we have an actor (like FAE14, FHK14, F4HK14, F2L14, FHK61, FME14) controlling the heating valve dependent on the configured target and current temperature. The target temperature is sent frequently by a room temperature sensor and the target temperature can be set via control panel (e.g. Eltako FTAF55ED) or Home Assistant [Climate Panel](https://developers.home-assistant.io/docs/core/entity/climate).

Both control panels are updated via a frequently sent telegram from the actor based on EEP A5-10-06. For setting the target temperature the same EEP A5-10-06 is used.

Heating and cooling is supported, however it cannot be change via Climate Panel. It will be set via central rocker switch which defines the state for the whole heating. All actors need to react on it.

<img src="./heating-and-cooling-setup2.png" alt="Heating and cooling setup" height=600 />

| Number      | Component   | Description |
| :---        | :---        | :---        |
| 1           | Heating and Cooling Actor | e.g. Eltako FHK14, FAE14SSR ... . This actor is controlling the actuator (number 6)|
| 2           | Climate Panel | Virtual temperature controller in Home Assistant. <br/>It requires an own address which needs to be entered in the function group 3 of the actor e.g. via PCT14 programming software. <br/>It's EEP is "A5-10-06". |
| 3           | Cooling Mode | Physical switch which is connected to FTS14EM and sends frequently (15min) a signal to stay in cooling mode or is off for heating. <br/>Supported EEPs: F6-02-01, F6-02-02, F6-10-00, D5-00-01, A5-08-01, M5-38-08 (FTS14EM contact signals and rocker switches are supported) |
| 4           | Room Temperature Sensor | Sensor sending periodically (every 50 seconds) the current temperature of the room. |
| 5           | Temperature Controller | Physical wall-mounted temperature sensor and controller in one box. |
| 6           | Actuator | Bringing the valve into the right position. |

## Actor Configuration in Device 

* **Heating is enabled** as default.
* **Operating state** instead of switching state is enabled.
* In **function group 1 a temperature sensor** is entered which sends frequently the current room temperature.
* **Optionally**: In **function group 2** a physical room **temperature controller** is entered. (e.g. Eltako FTAF55ED)
* In **function group 3** address for **Home Assistant Climate Panel** is entered.
* **Optionally**: In **function group 4** a rocker switch is entered for changing the **heating modes** (Normal, Off, Night (4°), Setback (2°) - Predefined by Eltako)
* **Optionally**: In **function group 4** a rocker switch is entered for changing from heating into **cooling mode**. Preferred solution is to use a physical with connected to FTS14EM. 

## Home Assistant Configuration

You can find the meaning of the numbers in the table above.
```
eltako:
  
  ...

  climate:
    - id: "00-00-00-09"           # Address of actor (1)
      eep: "A5-10-06"             # Telegram type of the actor (1)
      temperature_unit: "°C"      # Displayed temperature unit in Climate Panel (2)
      sender:                     # Virtual temperature controller (2)
        id: "00-00-B0-09"         # Sender address (2) needs to be entered .
        eep: "A5-10-06"           # 2: Sender EEP
      cooling_mode:               # Optional part - cooling mode
        sensor:                   # Rocker switch (3)
          id: "FE-DB-0A-1B"       # Address of switch (3) 
          eep: "M5-38-08"         # EEP of switch (3).
          data: 0x50              # In case of switch button needs to be specified.
```

