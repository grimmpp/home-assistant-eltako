# Changes and Feature List

## version 1.1.0 - Heating and Cooling
* Change file introduced
* **Climate Panel introduced** incl. support for actors like FAE14, FHK14, F4HK14, F2L14, FHK61, FME14 and EEP A5-10-06 as well as control panels like FTAF55ED.
* Docs for Climate Panel/Heating and Cooling
* Refactoring
  * Introduced many explicit types.
  * Logging improved
* Prepared config for other gateway types. (Currently supported Eltako fam14 and fgw14-usb)
* Support of different gateways e.g. enOcean USB300


Backlog:
* Gateway availability checks for send commands.
* Reconnect for serial interface
* Docs for Configuration Schema
* Extend device discovery for heating and cooling actors
* Integrate Eltako FMZ14 ([Multifunction Time Relay](https://www.eltako.com/fileadmin/downloads/en/_bedienung/FMZ14_30014009-2_gb.pdf))