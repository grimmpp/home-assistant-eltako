import ruamel.yaml
import json
from termcolor import colored
import logging
from eltakobus.device import BusObject
from eltakobus.message import *

EEP_MAPPING = [
    {'hw-type': 'FTS14EM', 'eep': 'F6-02-01', 'type': 'binary_sensor', 'description': 'Rocker switch', 'address_count': 1},
    {'hw-type': 'FTS14EM', 'eep': 'F6-02-02', 'type': 'binary_sensor', 'description': 'Rocker switch', 'address_count': 1},
    {'hw-type': 'FTS14EM', 'eep': 'F6-10-00', 'type': 'binary_sensor', 'description': 'Window handle', 'address_count': 1},
    {'hw-type': 'FTS14EM', 'eep': 'D5-00-01', 'type': 'binary_sensor', 'description': 'Contact sensor', 'address_count': 1},
    {'hw-type': 'FTS14EM', 'eep': 'A5-08-01', 'type': 'binary_sensor', 'description': 'Occupancy sensor', 'address_count': 1},

    {'hw-type': 'FWG14', 'eep': 'A5-13-01', 'type': 'sensor', 'description': 'Weather station', 'address_count': 1},
    {'hw-type': 'FTS14EM', 'eep': 'A5-12-01', 'type': 'sensor', 'description': 'Window handle', 'address_count': 1},
    {'hw-type': 'FSDG14', 'eep': 'A5-12-02', 'type': 'sensor', 'description': 'Automated meter reading - electricity', 'address_count': 1},
    {'hw-type': 'F3Z14D', 'eep': 'A5-13-01', 'type': 'sensor', 'description': 'Automated meter reading - gas', 'address_count': 1},
    {'hw-type': 'F3Z14D', 'eep': 'A5-12-03', 'type': 'sensor', 'description': 'Automated meter reading - water', 'address_count': 1},

    {'hw-type': 'FUD14', 'eep': 'A5-38-08', 'sender_eep': 'A5-38-08', 'type': 'light', 'description': 'Central command - gateway', 'address_count': 1},
    {'hw-type': 'FSR14_1x', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'light', 'description': 'Eltako relay', 'address_count': 1},
    {'hw-type': 'FSR14_x2', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'light', 'description': 'Eltako relay', 'address_count': 2},
    {'hw-type': 'FSR14_4x', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'light', 'description': 'Eltako relay', 'address_count': 4},

    {'hw-type': 'FSR14_1x', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'switch', 'description': 'Eltako relay', 'address_count': 1},
    {'hw-type': 'FSR14_x2', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'switch', 'description': 'Eltako relay', 'address_count': 2},
    {'hw-type': 'FSR14_4x', 'eep': 'M5-38-08', 'sender_eep': 'A5-38-08', 'type': 'switch', 'description': 'Eltako relay', 'address_count': 4},

    {'hw-type': 'FSB14', 'eep': 'G5-3F-7F', 'sender_eep': 'H5-3F-7F', 'sender_eep': '' ,'type': 'cover', 'description': 'Eltako cover', 'address_count': 1},
]

ORG_MAPPING = {
    5: {'Telegram': 'RPS', 'RORG': 'F6', 'name': 'Switch', 'type': 'binary_sensor', 'eep': 'F6-02-01'},
    6: {'Telegram': '1BS', 'RORG': 'D5', 'name': '1 Byte Communication', 'type': 'sensor', 'eep': 'D5-??-??'},
    7: {'Telegram': '4BS', 'RORG': 'A5', 'name': '4 Byte Communication', 'type': 'sensor', 'eep': 'A5-??-??'},
}

SENSOR_MESSAGE_TYPES = [EltakoWrappedRPS, EltakoWrapped4BS, RPSMessage, Regular4BSMessage, EltakoMessage]

class HaConfig():

    def __init__(self, default_sender_address, save_debug_log_config:bool=False):
        super()

        self.eltako = {}
        self.sener_id_list = []
        self.sender_address = default_sender_address
        self.export_logger = save_debug_log_config


    def find_device_info(self, name):
        for i in EEP_MAPPING:
            if i['hw-type'] == name:
                return i
        return None
    
    def get_formatted_address(self, address):
        a = f"{address:08x}".upper()
        return f"{a[0:2]}-{a[2:4]}-{a[4:6]}-{a[6:8]}"

    async def add_device(self, device: BusObject):
        device_name = type(device).__name__
        info = self.find_device_info(device_name)

        if info != None:
            for i in range(0,info['address_count']):

                dev_obj = {
                    'id': self.get_formatted_address(device.address+i),
                    'eep': f"{info['eep']}",
                    'name': f"{device_name} - {device.address+i}",
                }

                if info['type'] in ['light', 'switch', 'cover']:
                    dev_obj['sender'] = {
                        'id': f"{self.get_formatted_address(self.sender_address+device.address+i)}",
                        'eep': f"{info['sender_eep']}",
                    }

                if info['type'] not in self.eltako:
                    self.eltako[info['type']] = []    
                self.eltako[info['type']].append(dev_obj)
                
                logging.info(colored(f"Add device {info['type']}: id: {dev_obj['id']}, eep: {dev_obj['eep']}, name: {dev_obj['name']}",'yellow'))


    async def add_sensor(self, msg: ESP2Message):
        if type(msg) in SENSOR_MESSAGE_TYPES:
            logging.debug(msg)
            if hasattr(msg, 'outgoing'):
                if msg.address not in self.sener_id_list:

                    info = ORG_MAPPING[msg.org]
                    address = b2a(msg.address).replace(' ','-').upper()

                    sensor = {
                        'id': address,
                        'eep': info['eep'],
                        'name': info['name']
                    }

                    if info['type'] not in self.eltako:
                        self.eltako[info['type']] = []

                    self.eltako[info['type']].append(sensor)
                    self.sener_id_list.append(msg.address)
                    
                    logging.info(colored(f"Add Sensor ({info['name']}): address: {address}", 'yellow'))
        else:
            if type(msg) == EltakoDiscoveryRequest and msg.address == 127:
                logging.info(colored('Wait for incoming sensor singals. After you have recorded all your sensor singals press Ctrl+c to exist and store the configuration file.', 'red', attrs=['bold']))
            # to find message which are not displayed. Only for debugging because most of the messages are poll messages.
            # logging.debug(msg)


    def save_as_yaml_to_flie(self, filename:str):
        logging.info(colored(f"\nStore config into {filename}", 'red', attrs=['bold']))

        data = {}
        data['eltako'] = self.eltako
        
        if self.export_logger:
            data['logger'] = {
                'default': 'info',
                'logs': {
                    'eltako': 'debug'
                }
            }

        yaml = ruamel.yaml.YAML()
        yaml.preserve_quotes = True
        # yaml.explicit_start = True
        with open(filename, 'w') as f:
            data = yaml.dump(data, f)