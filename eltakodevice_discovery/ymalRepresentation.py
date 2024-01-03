from termcolor import colored
import logging
from custom_components.eltako.const import *
from homeassistant.const import CONF_ID, CONF_DEVICES, CONF_NAME, CONF_PLATFORM, CONF_TYPE, CONF_DEVICE_CLASS, CONF_TEMPERATURE_UNIT, UnitOfTemperature, Platform
from eltakobus.device import BusObject, FAM14, SensorInfo, KeyFunction
from eltakobus.message import *
from eltakobus.eep import *
from eltakobus.util import b2s, AddressExpression


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

    def __init__(self, sender_base_address:int, save_debug_log_config:bool=False):
        self.eltako = {}
        for p in [CONF_UNKNOWN, Platform.BINARY_SENSOR, Platform.LIGHT, Platform.SENSOR, Platform.SWITCH, Platform.COVER, Platform.CLIMATE]:
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
    
    def add_or_get_sensor(self, sensor_id:str, device_id:str, dev_type:str) -> dict:
        sensor = None
        if sensor_id not in self.detected_sensors.keys():
            logging.info(colored(f"Add sensor: address: {sensor_id} from device {device_id} and device type: {dev_type}", 'yellow'))
            sensor = { 
                CONF_ID: sensor_id,
                CONF_PLATFORM: CONF_UNKNOWN,
                CONF_EEP: CONF_UNKNOWN,
                CONF_REGISTERED_IN: [] 
            }
            self.detected_sensors[sensor_id] = sensor
        else:
            sensor = self.detected_sensors[sensor_id]

        if device_id is not None:
            sensor[CONF_REGISTERED_IN].append(f"{device_id} ({dev_type})")

        return sensor


    def add_detected_sensors_to_eltako_config(self):
        for s in self.detected_sensors.values():
            self.eltako[ s[CONF_PLATFORM] ].append( s )

    
    def a2s(self, address):
        """address to string"""
        return b2s( address.to_bytes(4, byteorder = 'big') )


    def add_sensors(self, sensors: [SensorInfo]) -> None:
        self.collected_sensor_list.extend( sensors )

        for s in sensors:
            if self.filter_out_base_address(s.sensor_id):
                _s = self.add_or_get_sensor(s.sensor_id_str, s.dev_adr_str, s.dev_type)
                _s[CONF_COMMENT] = KeyFunction(s.key_func).name
                _s[CONF_EEP] = self.get_eep_from_key_function_name(s.key_func)
                _s[CONF_NAME] = CONF_UNKNOWN
                
                if s.key_func in KeyFunction.get_switch_sensor_list():
                    _s[CONF_PLATFORM] = Platform.BINARY_SENSOR
                    _s[CONF_EEP] = F6_02_01.eep_string
                    _s[CONF_NAME] = "Switch"
                elif s.key_func in KeyFunction.get_contect_sensor_list():
                    _s[CONF_PLATFORM] = Platform.BINARY_SENSOR
                    _s[CONF_EEP] = D5_00_01.eep_string
                    _s[CONF_DEVICE_CLASS] = "Window"
                    _s[CONF_NAME] = "Contact"
                    _s[CONF_INVERT_SIGNAL] = False
                    

    def filter_out_base_address(self, sensor_id:bytes) -> bool:
        sensor_id_int = int.from_bytes(sensor_id, "big")
        return self.sender_base_address > sensor_id_int or self.sender_base_address+128 < sensor_id_int

    def get_eep_from_key_function_name(self, kf: KeyFunction) -> str:
        pos = KeyFunction(kf).name.find('EEP_')
        if pos > -1:
            substr = KeyFunction(kf).name[pos+4:pos+4+8]
            return substr
        return CONF_UNKNOWN


    async def add_device(self, device: BusObject):
        device_type = type(device).__name__
        info = self.find_device_info(device_type)

        # detects base if of FAM14
        if isinstance(device, FAM14):
            self.fam14_base_id = await device.get_base_id()

        # add actuators
        if info != None:
            self.add_sensors(( await device.get_all_sensors() ) )

            for i in range(0,info['address_count']):

                dev_id_str:str = self.a2s( device.address+i )
                dev_obj = {
                    CONF_ID: dev_id_str,
                    CONF_EEP: f"{info[CONF_EEP]}",
                    CONF_NAME: f"{device_type} - {device.address+i}",
                }

                if 'sender_eep' in info: #info[CONF_TYPE] in ['light', 'switch', 'cover']:
                    dev_obj['sender'] = {
                        CONF_ID: f"{self.a2s( self.sender_base_address+device.address+i )}",
                        CONF_EEP: f"{info['sender_eep']}",
                    }
                
                if info[CONF_TYPE] == Platform.COVER:
                    dev_obj[CONF_DEVICE_CLASS] = 'shutter'
                    dev_obj[CONF_TIME_CLOSES] = 25
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

                        # add thermostat into sensor 
                        sensor = self.add_or_get_sensor(b2s(thermostat.sensor_id), dev_id_str, device_type)
                        sensor[CONF_PLATFORM] = Platform.SENSOR
                        sensor[CONF_EEP] = A5_10_06.eep_string
                        sensor[CONF_NAME] = "Temperature Sensor and Controller"
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
                info = ORG_MAPPING[msg.org]
                
                if address not in self.detected_sensors.keys():

                    sensor_type = self.guess_sensor_type_by_address(msg)
                    msg_type = type(msg).__name__
                    comment = f"Sensor Type: {sensor_type}, Derived from Msg Type: {msg_type}"

                    sensor = self.add_or_get_sensor(address, None, None)
                    if CONF_EEP not in sensor:
                        sensor[CONF_EEP] = info[CONF_EEP]
                    if CONF_NAME not in sensor:
                        sensor[CONF_NAME] = f"{info[CONF_NAME]} {address}"
                    if CONF_COMMENT not in sensor:
                        sensor[CONF_COMMENT] = comment

                    if info[CONF_TYPE] == Platform.BINARY_SENSOR:
                        sensor[CONF_DEVICE_CLASS] = 'window / door / smoke / motion / ?'

        else:
            if type(msg) == EltakoDiscoveryRequest and msg.address == 127:
                logging.info(colored('Wait for incoming sensor singals. After you have recorded all your sensor singals press Ctrl+c to exist and store the configuration file.', 'red', attrs=['bold']))
            # to find message which are not displayed. Only for debugging because most of the messages are poll messages.
            # logging.debug(msg)

    def generate_config(self) -> str:
        e = self.eltako

        out = f"{DOMAIN}:\n"
        out += f"  {CONF_GERNERAL_SETTINGS}:\n"
        out += f"    {CONF_FAST_STATUS_CHANGE}: False\n"
        out += f"    {CONF_SHOW_DEV_ID_IN_DEV_NAME}: False\n"
        out += f"\n"
        out += f"  {CONF_GATEWAY}:\n"
        out += f"  - {CONF_ID}: 1\n"
        fam14 = GatewayDeviceType.GatewayEltakoFAM14.value
        fgw14usb = GatewayDeviceType.GatewayEltakoFGW14USB.value
        out += f"    {CONF_DEVICE_TYPE}: {fam14}   # you can simply change {fam14} to {fgw14usb}\n"
        out += f"    {CONF_BASE_ID}: {self.fam14_base_id}\n"
        out += f"    {CONF_DEVICES}:\n"
        # go through platforms
        for type_key in e.keys():
            if len(e[type_key]) > 0:
                if type_key == CONF_UNKNOWN:
                    out += f"      # SECTION '{CONF_UNKNOWN}' NEEDS TO BE REMOVED!!!\n"
                out += f"      {type_key}:"
                for item in e[type_key]:
                    # print devices and sensors recursively
                    out += self.config_section_to_string(item, True, 0) + "\n\n"
        # logs
        out += "logger:\n"
        out += "  default: info\n"
        out += "  logs:\n"
        out += f"    {DOMAIN}: debug\n"

        return out

    def config_section_to_string(self, config, is_list:bool, space_count:int=0) -> str:
        out = ""
        spaces = space_count*" " + "        "
        S = '-' if is_list else ' '

        if CONF_COMMENT in config:
            out += spaces + f"# {config[CONF_COMMENT]}\n"
        if CONF_REGISTERED_IN in config:
            dev_id_list = list(set(config[CONF_REGISTERED_IN]))
            dev_id_list.sort()
            out += spaces + f"# REGISTERD IN DEVICE: {dev_id_list}\n"
        out += spaces[:-2] + f"{S} {CONF_ID}: {config[CONF_ID]}\n"

        for key in config.keys():
            value = config[key]
            if isinstance(value, str) or isinstance(value, int):
                if key not in [CONF_ID, CONF_COMMENT, CONF_REGISTERED_IN, CONF_PLATFORM]:
                    if isinstance(value, str) and '?' in value:
                        value += " # <= NEED TO BE COMPLETED!!!"
                    out += spaces + f"{key}: {value}\n"
            elif isinstance(value, dict):
                out += spaces + f"{key}: \n"
                out += self.config_section_to_string(value, False, space_count+2)
        
        return out
    
    def save_as_yaml_to_flie(self, filename:str):
        logging.info(colored(f"\nStore config into {filename}", 'red', attrs=['bold']))
        
        config_str = self.generate_config()

        with open(filename, 'w', encoding="utf-8") as f:
            print(config_str, file=f)