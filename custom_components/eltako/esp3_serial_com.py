# -*- encoding: utf-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import
import logging
import serial
import time
import threading

import queue

from enocean.communicators.communicator import Communicator
from enocean.protocol.packet import Packet, RadioPacket, RORG, PACKET
from enocean.protocol.constants import PACKET, PARSE_RESULT, RETURN_CODE

from eltakobus.message import ESP2Message, RPSMessage, Regular1BSMessage,  Regular4BSMessage, prettify

class ESP3SerialCommunicator(Communicator):
    ''' Serial port communicator class for EnOcean radio '''

    def __init__(self, filename, log=None, callback=None, baud_rate=57600, reconnection_timeout:float=10, esp2_translation_enabled:bool=False):
        self.esp2_translation_enabled = esp2_translation_enabled
        self._outside_callback = callback
        super(ESP3SerialCommunicator, self).__init__(self.__callback_wrapper)
        
        self._filename = filename
        self.log = log or logging.getLogger('enocean.communicators.SerialCommunicator')

        self._baud_rate = baud_rate
        self.__recon_time = reconnection_timeout
        self.is_serial_connected = threading.Event()
        self.status_changed_handler = None
        self.__ser = None

    def is_active(self) -> bool:
        return not self._stop_flag.is_set() and self.is_serial_connected.is_set()     

    def set_status_changed_handler(self, handler) -> None:
        self.status_changed_handler = handler
        self._fire_status_change_handler(self.is_active())

    def _fire_status_change_handler(self, connected:bool) -> None:
        try:
            if self.status_changed_handler:
                self.status_changed_handler(connected)
        except Exception as e:
            pass

    @classmethod
    def convert_esp2_to_esp3_message(cls, message: ESP2Message) -> RadioPacket:
    
        d = message.data[0]

        org = 0xF6
        if isinstance(message, RPSMessage):
            org = RORG.RPS
        elif isinstance(message, Regular1BSMessage):
            org = RORG.BS1
        elif isinstance(message, Regular4BSMessage):
            org = RORG.BS4
            d = message.data
        else:
            return None
        
        # command = [0xA5, 0x02, bval, 0x01, 0x09]
        # command.extend(self._sender_id)
        # command.extend([0x00])
        # self.send_command(data=command, optional=[], packet_type=0x01)

        data = bytes([org, 0x02, 0x01, 0x01, 0x09]) + d + message.address + bytes([message.status])

        packet = Packet(packet_type=0x01, data=data, optional=[])
        return packet

    @classmethod
    def convert_esp3_to_esp2_message(cls, packet: RadioPacket) -> ESP2Message:
        
        org = 0x05
        if packet.rorg == RORG.BS1:
            org = 0x06
        elif packet.rorg == RORG.BS4:
            org = 0x07
        else:
            return None

        if org == 0x07:
            body:bytes = bytes([0x0b, org] + packet.data[1:])
        else:
            body:bytes = bytes([0x0b, org] + packet.data[1:2] + [0,0,0] + packet.data[2:])

        return prettify( ESP2Message(body) )
    

    def __callback_wrapper(self, msg):
        if self._outside_callback:
            if self.esp2_translation_enabled:
                esp2_msg = ESP3SerialCommunicator.convert_esp3_to_esp2_message(msg)
                
                if esp2_msg is None:
                    self.log.warn("[ESP3SerialCommunicator] Cannot convert to esp2 message (%s).", msg)
                else:
                    self._outside_callback(esp2_msg)

            else:
                self._outside_callback(msg)

    def reconnect(self):
        self._stop_flag.set()
        self._stop_flag.wait()
        self.start()

    async def send(self, packet) -> bool:
        if self.esp2_translation_enabled:
            esp3_msg = ESP3SerialCommunicator.convert_esp2_to_esp3_message(packet)
            if esp3_msg is None:
                self.log.warn("[ESP3SerialCommunicator] Cannot convert to esp3 message (%s).", packet)
            else:
                return super().send(esp3_msg)
        else:
            return super().send(packet)

    def run(self):
        self.logger.info('SerialCommunicator started')
        self._fire_status_change_handler(connected=False)
        while not self._stop_flag.is_set():
            try:
                # Initialize serial port
                if self.__ser is None:
                    self.__ser = serial.Serial(self._filename, self._baud_rate, timeout=0.1)
                    self.log.info("Established serial connection to %s - baudrate: %d", self._filename, self._baud_rate)
                    self.is_serial_connected.set()
                    self._fire_status_change_handler(connected=True)

                # If there's messages in transmit queue
                # send them
                while True:
                    packet = self._get_from_send_queue()
                    if not packet:
                        break
                    print("send msg")
                    self.__ser.write(bytearray(packet.build()))

                # Read chars from serial port as hex numbers
                self._buffer.extend(bytearray(self.__ser.read(16)))
                self.parse()
                time.sleep(0)

            except (serial.SerialException, IOError) as e:
                self._fire_status_change_handler(connected=False)
                self.is_serial_connected.clear()
                self.log.error(e)
                self.__ser = None
                self.log.info("Serial communication crashed. Wait %s seconds for reconnection.", self.__recon_time)
                time.sleep(self.__recon_time)

        self.__ser.close()
        self._fire_status_change_handler(connected=False)
        self.logger.info('SerialCommunicator stopped')
