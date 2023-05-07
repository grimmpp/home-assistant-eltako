# Eltako Device and Sensor Discovery

Main purpose of this tool is to programmatically prepare the Home Assistance configuration as good as possible.

## Limitation
Unfortunately, the configuration cannot be generated automatically because there is no clear relation between sensor messages and their EEP numbers ([EnOcean Equipment Profiles](https://www.trio2sys.fr/images/media/EnOcean_Equipment_Profiles_EEP2.1.pdf)). 
Sensors can still be detected you merely need to extend the EEPs manually.

## Device Detection
Nevertheless, it can detect devices and their addresses on the bus. All devices will be listed incl. their addresses and 'virtual' sender so that Home Assistant can send commands to the devices. All devices need to have the sender address entered and every device needs its own sender. To keep the device and sender address relation simple there is a patter to not get confused. 

## Sender Address Pattern for Devices
There is a offset address for the senders (default value ``00 00 B0 00``). For every device the sender address is ``offset + device address``. 

Example: If you have a FUD14 with address ``5`` and if you use offset address ``00 00 B0 00`` then the sender address is ``00 00 B0 05``.

## Sender Detection
After all devices detected the tool will scan for senders. You can push all the switches and wait for message coming in e.g. from weather stations. After you think you've waited long enough you can press ``Ctrl+c`` to end the listening process. 


## Manual Extension
The tool will then write all collected data into a file which you then need to extend manually. Most of the detected senders won't have a proper EEP. Therefore check out the [Enocean Standard](https://www.trio2sys.fr/images/media/EnOcean_Equipment_Profiles_EEP2.1.pdf) and what type of sensors (EEPs) send which messages. Important is to have the relation of EEP to the address which is included in the sensor message and which was detected by the tool and put into the output file.

# Example Execution
USB cable needs to be plugged into FAM14. The find out the right serial port in this example ``/dev/ttyUSB0``. Define an output file and offset address for the senders.

Execute:
``python3 ha_discovery.py --verbose --eltakobus /dev/ttyUSB0 --output ha.yaml --offset-sender-address 0x0000B000``

At some point the tool will ask you to wait for sensor messages. Wait for all automatically triggered messages from e.g. weather stations and push all switches you want to register in Home Assistant. You can end the detection by simply pressing ``Ctrl+c``.

It will list you all the detected devices and sensors. As result you will receive a yaml which you can copy past into Home Assistant. Ensure that you find and enter manually all the needed EEPs for the listed sensors.
