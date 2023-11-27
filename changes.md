# Changes and Feature List

## version 1.1.0 - Heating and Cooling
* Change file introduced
* **Climate Panel introduced** incl. support for actors like FAE14, FHK14, F4HK14, F2L14, FHK61, FME14 and EEP A5-10-06 as well as control panels like FTAF55ED.
* Docs for Climate Panel/Heating and Cooling
* Refactoring
  * Introduced many explicit types.
  * Logging improved
* Prepared config for other gateway types. (Currently supported Eltako fam14 and fgw14-usb)
* Support of different gateways e.g. enOcean USB300 with different protocol version (ESP3)
* Added teach-in buttons for climate and temperature controller
* Added Air Quality Sensor with EEP A5-09-0C for e.g. FLGTF
* Fast status change added. You can set per configuration is you want to wait for actuator response or if you directly want to see the status change in HA.

## Version 1.0.0 Baseline

## Backlog
* Config generation shall be come more easy.
* Docs for Configuration Schema
* Extend device discovery for heating and cooling actors
* Integrate Eltako FUTH65D ([Wireless thermo clock/hygrostat](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FUTH65D_12-24VUC_30065741-1_gb.pdf))
* Integrate Eltako FMZ14 ([Multifunction Time Relay](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FMZ14_30014009-2_gb.pdf))
* Gateway availability checks for send commands.
* Reconnect for serial interface.
