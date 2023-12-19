import json
from termcolor import colored
import logging
from custom_components.eltako.const import *
from custom_components.eltako.gateway import GatewayDeviceType
from homeassistant.const import CONF_ID, CONF_DEVICES, CONF_NAME, CONF_PLATFORM, CONF_TYPE, CONF_DEVICE_CLASS, CONF_TEMPERATURE_UNIT, UnitOfTemperature
from eltakobus.device import BusObject, FAM14, SensorInfo, KeyFunction
from eltakobus.message import *
from eltakobus.eep import *
from eltakobus.util import b2s

from homeassistant.const import Platform

EEP_MAPPING = [
    {'hw-type': 'FTS14EM', CONF_EEP: 'F6-02-01', CONF_TYPE: Platform.BINARY_SENSOR, 'description': 'Rocker switch', 'address_count': 1},
    {'hw-type': 'FTS14EM', CONF_EEP: 'F6-02-02', CONF_TYPE: Platform.BINARY_SENSOR, 'description': 'Rocker switch', 'address_count': 1},
    {'hw-type': 'FTS14EM', CONF_EEP: 'F6-10-00', CONF_TYPE: Platform.BINARY_SENSOR, 'description': 'Window handle', 'address_count': 1},
    {'hw-type': 'FTS14EM', CONF_EEP: 'D5-00-01', CONF_TYPE: Platform.BINARY_SENSOR, 'description': 'Contact sensor', 'address_count': 1},
    {'hw-type': 'FTS14EM', CONF_EEP: 'A5-08-01', CONF_TYPE: Platform.BINARY_SENSOR, 'description': 'Occupancy sensor', 'address_count': 1},

    {'hw-type': 'FWG14', CONF_EEP: 'A5-13-01', CONF_TYPE: Platform.SENSOR, 'description': 'Weather station', 'address_count': 1},
    {'hw-type': 'FTS14EM', CONF_EEP: 'A5-12-01', CONF_TYPE: Platform.SENSOR, 'description': 'Window handle', 'address_count': 1},
    {'hw-type': 'FSDG14', CONF_EEP: 'A5-12-02', CONF_TYPE: Platform.SENSOR, 'description': 'Automated meter reading - electricity', 'address_count': 1},
    {'hw-type': 'F3Z14D', CONF_EEP: 'A5-13-01', CONF_TYPE: Platform.SENSOR, 'description': 'Automated meter reading - gas', 'address_count': 1},
    {'hw-type': 'F3Z14D', CONF_EEP: 'A5-12-03', CONF_TYPE: Platform.SENSOR, 'description': 'Automated meter reading - water', 'address_count': 1},

    {'hw-type': 'FUD14', CONF_EEP: 'A5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.LIGHT, 'description': 'Central command - gateway', 'address_count': 1},
    {'hw-type': 'FSR14_1x', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.LIGHT, 'description': 'Eltako relay', 'address_count': 1},
    {'hw-type': 'FSR14_x2', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.LIGHT, 'description': 'Eltako relay', 'address_count': 2},
    {'hw-type': 'FSR14_4x', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.LIGHT, 'description': 'Eltako relay', 'address_count': 4},

    {'hw-type': 'FSR14_1x', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.SWITCH, 'description': 'Eltako relay', 'address_count': 1},
    {'hw-type': 'FSR14_x2', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.SWITCH, 'description': 'Eltako relay', 'address_count': 2},
    {'hw-type': 'FSR14_4x', CONF_EEP: 'M5-38-08', 'sender_eep': 'A5-38-08', CONF_TYPE: Platform.SWITCH, 'description': 'Eltako relay', 'address_count': 4},

    {'hw-type': 'FSB14', CONF_EEP: 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', CONF_TYPE: Platform.COVER, 'description': 'Eltako cover', 'address_count': 2},

    {'hw-type': 'FAE14SSR', CONF_EEP: 'A5-10-06', 'sender_eep': 'A5-10-06', CONF_TYPE: Platform.CLIMATE, 'description': 'Eltako heating/cooling', 'address_count': 2},
]

ORG_MAPPING = {
    5: {'Telegram': 'RPS', 'RORG': 'F6', CONF_NAME: 'Switch', CONF_TYPE: Platform.BINARY_SENSOR, CONF_EEP: 'F6-02-01' },
    6: {'Telegram': '1BS', 'RORG': 'D5', CONF_NAME: '1 Byte Communication', CONF_TYPE: Platform.SENSOR, CONF_EEP: 'D5-??-??' },
    7: {'Telegram': '4BS', 'RORG': 'A5', CONF_NAME: '4 Byte Communication', CONF_TYPE: Platform.SENSOR, CONF_EEP: 'A5-??-??' },
}

SENSOR_MESSAGE_TYPES = [EltakoWrappedRPS, EltakoWrapped4BS, RPSMessage, Regular4BSMessage, Regular1BSMessage, EltakoMessage]

class HaConfig():

    def __init__(self, sender_base_address, save_debug_log_config:bool=False):
        self.eltako = {}
        for p in [Platform.BINARY_SENSOR, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH, Platform.COVER, Platform.CLIMATE]:
            self.eltako[p] = []
        self.detected_sensors = {}
        self.sender_base_address = sender_base_address
        self.export_logger = save_debug_log_config
        self.fam14_base_id = '00-00-00-00'

        self.collected_sensor_list:[SensorInfo] = []

    def get_detected_sensor_by_id(self, id:str) -> dict:
        if id not in self.detected_sensors.keys():
            self.detected_sensors[id] = {
                CONF_ID: id
            }

        return self.detected_sensors[id]
    
    def find_sensors(self, dev_id:int, in_func_group: int) -> [SensorInfo]:
        result = []
        for s in self.collected_sensor_list: 
            if int.from_bytes(s.dev_adr, "big") == dev_id and s.in_func_group == in_func_group:
                result.append(s)
        return result
    
    def find_sensor(self, dev_id:int, in_func_group: int) -> SensorInfo:
        l = self.find_sensors(dev_id, in_func_group)
        if len(l) > 0:
            return l[0]
        return None

    def find_device_info(self, name):
        for i in EEP_MAPPING:
            if i['hw-type'] == name:
                return i
        return None
    
    
    def a2s(self, address):
        """address to string"""
        return b2s( address.to_bytes(4, byteorder = 'big') )


    async def add_device(self, device: BusObject):
        device_name = type(device).__name__
        info = self.find_device_info(device_name)

        # detects base if of FAM14
        if isinstance(device, FAM14):
            self.fam14_base_id = await device.get_base_id()

        # add actuators
        if info != None:
            self.collected_sensor_list.extend( await device.get_all_sensors() )

            for i in range(0,info['address_count']):

                dev_obj = {
                    # CONF_ID: self.get_formatted_address(device.address+i),
                    CONF_ID: self.a2s( device.address+i ),
                    CONF_EEP: f"{info[CONF_EEP]}",
                    CONF_NAME: f"{device_name} - {device.address+i}",
                }

                if 'sender_eep' in info: #info[CONF_TYPE] in ['light', 'switch', 'cover']:
                    dev_obj['sender'] = {
                        CONF_ID: f"{self.a2s( self.sender_base_address+device.address+i )}",
                        CONF_EEP: f"{info['sender_eep']}",
                    }
                
                if info[CONF_TYPE] == Platform.COVER:
                    dev_obj[CONF_DEVICE_CLASS] = 'shutter'
                    dev_obj[CONF_TIME_CLOSES] = 24
                    dev_obj[CONF_TIME_OPENS] = 25

                if info[CONF_TYPE] == Platform.CLIMATE:
                    dev_obj[CONF_TEMPERATURE_UNIT] = f"'{UnitOfTemperature.KELVIN}'"
                    dev_obj[CONF_MIN_TARGET_TEMPERATURE] = 16
                    dev_obj[CONF_MAX_TARGET_TEMPERATURE] = 25
                    thermostat = self.find_sensor(device.address, in_func_group=1)
                    if thermostat:
                        dev_obj[CONF_ROOM_THERMOSTAT] = {}
                        dev_obj[CONF_ROOM_THERMOSTAT][CONF_ID] = b2s(thermostat.sensor_id)
                        dev_obj[CONF_ROOM_THERMOSTAT][CONF_EEP] = A5_10_06.eep_string   #TODO: derive EEP from switch/sensor function
                    # #TODO: cooling_mode

                self.eltako[info[CONF_TYPE]].append(dev_obj)
                
                logging.info(colored(f"Add device {info[CONF_TYPE]}: id: {dev_obj[CONF_ID]}, eep: {dev_obj[CONF_EEP]}, name: {dev_obj[CONF_NAME]}",'yellow'))


    def guess_sensor_type_by_address(self, msg:ESP2Message)->str:
        if type(msg) == Regular1BSMessage:
            try:
                data = b"\xa5\x5a" + msg.body[:-1]+ (sum(msg.body[:-1]) % 256).to_bytes(2, 'big')
                _msg = Regular1BSMessage.parse(data)
                min_address = b'\x00\x00\x10\x01'
                max_address = b'\x00\x00\x14\x89'
                if min_address <= _msg.address and _msg.address <= max_address:
                    return "FTS14EM switch"
            except:
                pass
        
        if type(msg) == RPSMessage:
            if b'\xFE\xDB\x00\x00' < msg.address:
                return "Wall Switch /Rocker Switch"

        if type(msg) == Regular4BSMessage:
            return "Multi-Sensor ? "

        return "???"

    # async def add_sensor_from_actuator(self, sensor_info: SensorInfo):
    #     for si in sensor_info:



    async def add_sensor_from_wireless_telegram(self, msg: ESP2Message):
        if type(msg) in SENSOR_MESSAGE_TYPES:
            logging.debug(msg)
            if hasattr(msg, 'outgoing'):
                address = b2s(msg.address)
                if address not in self.detected_sensors.keys():

                    info = ORG_MAPPING[msg.org]
                    sensor_type = self.guess_sensor_type_by_address(msg)
                    msg_type = type(msg).__name__
                    comment = f"Sensor Type: {sensor_type}, Derived from Msg Type: {msg_type}"

                    sensor = self.get_detected_sensor_by_id(address)
                    sensor[CONF_EEP] = info[CONF_EEP]
                    sensor[CONF_NAME] = f"{info[CONF_NAME]} {address}"
                    sensor[CONF_PLATFORM] = info[CONF_TYPE]
                    sensor[CONF_COMMENT] = comment

                    if info[CONF_TYPE] == Platform.BINARY_SENSOR:
                        sensor[CONF_DEVICE_CLASS] = 'window / door / smoke / motion / ?'

                    if info[CONF_TYPE] not in self.eltako:
                        self.eltako[info[CONF_TYPE]] = []

                    self.eltako[info[CONF_TYPE]].append(sensor)
                    self.detected_sensors[b2s(msg.address)] = sensor
                    
                    logging.info(colored(f"Add Sensor ({msg_type} - {info[CONF_NAME]}): address: {address}, Sensor Type: {sensor_type}", 'yellow'))
        else:
            if type(msg) == EltakoDiscoveryRequest and msg.address == 127:
                logging.info(colored('Wait for incoming sensor singals. After you have recorded all your sensor singals press Ctrl+c to exist and store the configuration file.', 'red', attrs=['bold']))
            # to find message which are not displayed. Only for debugging because most of the messages are poll messages.
            # logging.debug(msg)


    def save_as_yaml_to_flie(self, filename:str):
        logging.info(colored(f"\nStore config into {filename}", 'red', attrs=['bold']))
        
        e = self.eltako

        with open(filename, 'w', encoding="utf-8") as f:
            print(f"{DOMAIN}:", file=f)
            print(f"  {CONF_GERNERAL_SETTINGS}:", file=f)
            print(f"    {CONF_FAST_STATUS_CHANGE}: False", file=f)
            print(f"    {CONF_SHOW_DEV_ID_IN_DEV_NAME}: False", file=f)
            print(f"  {CONF_GATEWAY}:", file=f)
            print(f"  - {CONF_ID}: 1", file=f)
            fam14 = GatewayDeviceType.GatewayEltakoFAM14.value
            fgw14usb = GatewayDeviceType.GatewayEltakoFGW14USB.value
            print(f"    {CONF_DEVICE_TYPE}: {fam14}   # you can simply change {fam14} to {fgw14usb}", file=f)
            print(f"    {CONF_BASE_ID}: "+self.fam14_base_id, file=f)
            print(f"    {CONF_DEVICES}:", file=f)
            for type_key in e.keys():
                print(f"      {type_key}:", file=f)
                for item in e[type_key]:
                    f.write( self.config_section_to_string(item, True, 0) )
            # logs
            print("logger:", file=f)
            print("  default: info", file=f)
            print("  logs:", file=f)
            print(f"    {DOMAIN}: debug", file=f)


    def config_section_to_string(self, config, is_list:bool, space_count:int=0) -> str:
        out = ""
        spaces = space_count*" " + "        "
        S = '-' if is_list else ' '

        if CONF_COMMENT in config:
            out += spaces + f"# {config[CONF_COMMENT]}\n"
        out += spaces[:-2] + f"{S} {CONF_ID}: {config[CONF_ID]}\n"

        for key in config.keys():
            value = config[key]
            if isinstance(value, str) or isinstance(value, int):
                if key not in [CONF_ID, CONF_COMMENT]:
                    if isinstance(value, str) and '?' in value:
                        value += " # <= NEED TO BE COMPLETED!!!"
                    out += spaces + f"{key}: {value}\n"
            elif isinstance(value, dict):
                out += spaces + f"{key}: \n"
                out += self.config_section_to_string(value, False, space_count+2)
        
        return out