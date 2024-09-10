# Logging

This part is about how to get access to the logs of Home Assistant Eltako Integration to e.g. check
* what telegrams have been received
* what events have been sent
* if there have been any problems occurred 
* to under how the automation behaves and see what have been done.

<img src="screenshot_logging.png" alt="Exemplary screenshot about logging." height="300" />

## Log level 
By default log level `INFO` is activated which means only important information like be displayed in the logs. This comprises e.g. error and superficial information.
If you want to get more detailed information you need to change the log level which can be done inside the Home assistant Configuration file `/config/configuration.yaml`.


## Change log level to get detailed information
To chang the configuration I can recommend to install and use the addon [File Editor](https://github.com/home-assistant/addons/tree/master/configurator). With File Editor you can read and edit any file in Home Assistant via your browser.

Extend or change the following part of the confguration file:
```
logger:
  default: info         # default log level of all components of Home Assistant
  logs:
    eltako: debug                                       # enables detailed information for Home Assistant Eltako Integration 
    eltakobus.serial: info                              # enables detailed information of the communication library for enocean devices based on ESP2 protocol
    enocean.communicators.SerialCommunicator: info      # enables detailed information of the communication library for enocean devices based on ESP3 protocol
    eltakobus.tcp2serial: info                         # enables detailed information of the communication library for gateway connected via TCP and enocean devices based on ESP3 protocol
```

## Read logs
To get the logs nicely displayed I can recommend to install and use the addon [log-viewer](https://github.com/hassio-addons/addon-log-viewer).

Logs can also be found in  `/config/home-assistant.log` and displayed by using [File Editor](https://github.com/home-assistant/addons/tree/master/configurator).
