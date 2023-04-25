``python3 ha_discovery.py /dev/ttyUSB1``

The plan is to detect all actors on the bus and prepare the list of devices as good as posible.

Additionally one could set the sender ids for Home Assistant. Idea: use a base address e.g. 0000B000 and add the device id on top. This new address could be used as default sender address. The tool could check if this address is entered and if not add it to a free register of the device.