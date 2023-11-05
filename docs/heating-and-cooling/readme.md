# Heating and Cooling

This documentation is about how to control a heating like a heat pump which is able to heat up in winter and to cool down in summer.

<img src="./HAClimatePanel.png" alt="Home Assistant Climate Panel" height="250"/>

In the following scenario we have an actor (like FAE14, FHK14, F4HK14, F2L14, FHK61, FME14) controlling the heating valve dependent on the configured target and current temperature. The target temperature is sent frequently by a room temperature sensor and the target temperature can be set via control panel (e.g. Eltako FTAF55ED) or Home Assistant [Climate Panel](https://developers.home-assistant.io/docs/core/entity/climate).

Both control panels are updated via a frequently sent telegram from the actor based on EEP A5-10-06. For setting the target temperature the same EEP A5-10-06 is used.

Heating and cooling is supported, however it cannot be change via Climate Panel. It will be set via central rocker switch which defines the state for the whole heating. All actors need to react on it.

=> Drawing of the setup

## Actor Configuration in Device 

* **Heating is enabled** as default.
* **Operating state** instead of switching state is enabled.
* In **function group 1 a temperature sensor** is entered which sends frequently the current room temperature.
* **Optionally**: In **function group 2** a physical room **temperature controller** is entered. (e.g. Eltako FTAF55ED)
* In **function group 3** address for **Home Assistant Climate Panel** is entered.
* **Optionally**: In **function group 4** a rocker switch is entered for changing the **heating modes** (Normal, Off, Night (4°), Setback (2°) - Predefined by Eltako)
* **Optionally**: In **function group 4** a rocker switch is entered for changing from heating into **cooling mode**. Preferred solution is to use a physical with connected to FTS14EM. 

## Home Assistant Configuration

```
eltako:
  
  ...

  climate:
    - id: "00-00-00-09"           # Address of the actor
      eep: "A5-10-06"             # Telegram type of the actor
      temperature_unit: "°C"      # Displayed temperature unit in Home Assistant Climate Panel
      sender:                     # Virtual sender which represents the Home Assistant Climate Panel. Is used to set the target temperature.
        id: "00-00-B0-09"         # Sender address needs to be entered in the function group 3 of the actor e.g. via PCT14 programming software.
        eep: "A5-10-06"
      cooling_mode:               # Optional part - cooling: If this part is specified Climate Panel will automatically show cooling mode as option however it must be switch by a physical switch. It is a setting of the heating in general and not for individual control units.
        sensor:                   # Rocker switch which sends frequently (each 15min) telegrams to stay in cooling mode.
          id: "FE-DB-0A-1B"
          eep: "M5-38-08"         # Supported EEPs: F6-02-01, F6-02-02, F6-10-00, D5-00-01, A5-08-01, M5-38-08 (FTS14EM switch singals and rocker switches)
          data: 0x50              # Button which is expected to be pushed.
```

