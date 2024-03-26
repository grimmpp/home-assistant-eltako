# Eltako Device and Sensor Discovery

# DEPRECATED: Check out [EnOnocean Device Manager](https://github.com/grimmpp/enocean-device-manager)

Main purpose of this tool is to programmatically prepare the Home Assistance configuration as good as possible.

## Limitation
Unfortunately, the configuration cannot be generated automatically because there is no clear relation between sensor messages and their EEP numbers ([EnOcean Equipment Profiles](https://www.trio2sys.fr/images/media/EnOcean_Equipment_Profiles_EEP2.1.pdf)). 
Sensors can still be detected you merely need to extend the EEPs manually.

## Device Detection
Nevertheless, it can detect devices and their addresses on the bus. All devices will be listed incl. their addresses and 'virtual' sender so that Home Assistant can send commands to the devices. All devices need to have the sender address entered and every device needs its own sender. To keep the device and sender address relation simple there is a pattern to not get confused. 

## Sender Address Pattern for Devices
There is a offset address for the senders (default value ``00 00 B0 00``). For every device the sender address is ``offset + device address``. 

Example: If you have a FUD14 with address ``5`` and if you use offset address ``00 00 B0 00`` then the sender address is ``00 00 B0 05``.

This pattern can also automatically applied to the devices. By using the argument `--write_sender_address_to_device` the script ensures that Home Assistant senders are registered.

## Sender Detection
After all devices detected the tool will scan for senders. You can push all the switches and wait for message coming in e.g. from weather stations. After you think you've waited long enough you can press ``Ctrl+c`` to end the listening process. 


## Manual Extension
The tool will then write all collected data into a file which you then need to extend manually. Most of the detected senders won't have a proper EEP. Therefore check out the [Enocean Standard](https://www.trio2sys.fr/images/media/EnOcean_Equipment_Profiles_EEP2.1.pdf) and what type of sensors (EEPs) send which messages. Important is to have the relation of EEP to the address which is included in the sensor message and which was detected by the tool and put into the output file.

## Tool Installation and Usage
(Works on Linux as well as on Windows. Mac is not tested.)
1. Python 3 is installed.
2. Clone repo and change into it. `git clone https://github.com/grimmpp/home-assistant-eltako` and `cd home-assistant-eltako`
3. Install virtual environment: `python.exe -m venv .venv`
4. Install dependencies/libraries: `.\.venv\Scripts\pip.exe install -r .\requirements.txt`
5. Select python interpreter and virtualenv in VS Code: `CTRL + SHIFT + P`, type: `Python: Select Interpreter` and choose `Python 3.*` with path `.venv`.<br/>
6. Use Debug mode in VS Code to run the tool. (Specifing all arguments and code dependencies is a quite long arguement list.) <br/>
   Choose in selction `RUN AND DEBUG`: `Python: device discovery (Windows)` or `Python: device discovery (Linux)`
7. USB cable needs to be plugged into FAM14. 
8. Find out the right serial port and enter it in the `launch.json`. You can also change e.g. filename, ... . (You can open `launch.json` by clicking on the gear next to the combobox.)
9. If you want to automatically write also the virtual sender ids into the Eltako devices then add `"-wsa"` to the argument list.
10. Start the tool by pushing the green debug arrow.
11. At some point the tool will ask you to wait for sensor messages. Wait for all automatically triggered messages from e.g. weather stations and push all switches you want to have listed in the configuration. You can end the detection by simply pressing ``CRTL+c``.
12. It will list all detected devices and sensors. As result you will receive a yaml which you can copy past into Home Assistant. Ensure that you find and enter manually all the needed EEPs for the listed sensors.


<img src="./debug_decice_discovery2.png"/>

An example file can be found here: [ha.yaml](ha.yaml)

# GUI
I started to develop an graphical user interface. You can start it by choosing `Python: Device Discovery GUI` in VS Code in the debug section.
Required installation steps can be found in the steps above. 