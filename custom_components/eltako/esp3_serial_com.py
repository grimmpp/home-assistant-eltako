# -*- encoding: utf-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import
import asyncio
import datetime
import logging
import serial
import time
import threading

import queue

from enocean.communicators.communicator import Communicator
from enocean.protocol.packet import Packet, RadioPacket, RORG, PACKET, UTETeachInPacket
from enocean.protocol.constants import PACKET, PARSE_RESULT, RETURN_CODE


from eltakobus.message import ESP2Message, RPSMessage, Regular1BSMessage,  Regular4BSMessage, prettify
from eltakobus.eep import CentralCommandSwitching, A5_38_08
from eltakobus.util import b2s

class ESP3SerialCommunicator(Communicator):
    ''' Serial port communicator class for EnOcean radio '''

    def __init__(self, 
                 filename, 
                 log=None, 
                 callback=None, 
                 baud_rate=57600, 
                 reconnection_timeout:float=10, 
                 esp2_translation_enabled:bool=False, 
                 auto_reconnect:bool=True):
        
        self.esp2_translation_enabled = esp2_translation_enabled
        self._outside_callback = callback
        self._auto_reconnect = auto_reconnect
        super(ESP3SerialCommunicator, self).__init__(self.__callback_wrapper)
        
        self._filename = filename
        self.log = log or logging.getLogger('enocean.communicators.SerialCommunicator')

        self._baud_rate = baud_rate
        self.__recon_time = reconnection_timeout
        self.is_serial_connected = threading.Event()
        self.status_changed_handler = None
        self.__ser = None

    def set_callback(self, callback):
        self._outside_callback = callback

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

    async def base_exchange(self, request:ESP2Message):
        self.esp2_translation_enabled = True
        self.send(request)

    @classmethod
    def convert_esp2_to_esp3_message(cls, message: ESP2Message) -> RadioPacket:
        optional = []
        if isinstance(message, RPSMessage):
            rorg = RORG.RPS
            data = [message.data[0]]
        elif isinstance(message, Regular1BSMessage):
            rorg = RORG.BS1
            data = [message.data[0]]
        elif isinstance(message, Regular4BSMessage):
            rorg = RORG.BS4
            sub_tel = PACKET.RADIO_SUB_TEL if message.outgoing else 0 # 3 = send, 0 = receive
            optional = [sub_tel,   # 3 = sender, 0 = receiver
                        0xFF, 0xFF, 0xFF, 0xFF, # destination broadcast
                        0xFF                    # wireless quality
                        ]
            data = message.data
        else:
            return None

        command=[rorg]
        command.extend(data)
        command.extend([x for x in message.address])
        command.extend([message.status])

        package_type = PACKET.RADIO_ERP1
        p = Packet(package_type, command, optional)
        p.rorg = rorg
        p.packet_type = package_type

        return p

    @classmethod
    def convert_esp3_to_esp2_message(cls, packet: RadioPacket) -> ESP2Message:
        
        if packet.rorg == RORG.RPS:
            org = 0x05
        elif packet.rorg == RORG.BS1:
            org = 0x06
        elif packet.rorg == RORG.BS4:
            org = 0x07
        else:
            return None

        sub_tel = packet.optional[0] if packet.optional is not None and len(packet.optional) > 0 else 0 # 3 = send, 0 = receive
        in_or_out = 0x6b if sub_tel == PACKET.RADIO_SUB_TEL else 0x0b

        if org == 0x07:
            
            body:bytes = bytes([in_or_out, org] + packet.data[1:])
        else:
            # data = ['0xf6', '0x50', '0xff', '0xa2', '0x24', '0x1', '0x30']
            body:bytes = bytes([in_or_out, org] + packet.data[1:2] + [0,0,0] + packet.data[2:])

        return prettify( ESP2Message(body) )
    

    def __callback_wrapper(self, msg: Packet):
        if msg.packet_type == PACKET.RESPONSE and msg.data[0] != RETURN_CODE.OK:
            self.log.error(f"Received ESP3 response with with return code {RETURN_CODE(msg.data[0]).name} ({msg.data[0]}) - {str(msg)} ")
            return

        if self._outside_callback:
            if self.esp2_translation_enabled:
                # only when message is radio telegram
                if msg.packet_type == PACKET.RADIO:
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
            self.log.debug(f"Converted esp2 ({str(packet)} - {b2s(packet.serialize())}) message to esp3 ({str(esp3_msg)})")
            if esp3_msg is None:
                self.log.warn("[ESP3SerialCommunicator] Cannot convert to esp3 message (%s).", packet)
            else:
                self.log.debug(f"Send ESP3 message {str(esp3_msg)}")
                return super().send(esp3_msg)
        else:
            self.log.debug(f"Send ESP3 message {str(packet)}")
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
                    self.log.debug("send msg: %s", packet)
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
                if self._auto_reconnect:
                    self.log.info("Serial communication crashed. Wait %s seconds for reconnection.", self.__recon_time)
                    time.sleep(self.__recon_time)
                else:
                    self._stop_flag.set()

        if self.__ser is not None:
            self.__ser.close()
            self.__ser = None
        self.is_serial_connected.clear()
        self._fire_status_change_handler(connected=False)
        self.logger.info('SerialCommunicator stopped')


    def parse(self):
        ''' Parses messages and puts them to receive queue '''
        # Loop while we get new messages
        while True:
            status, self._buffer, packet = Packet.parse_msg(self._buffer)
            # If message is incomplete -> break the loop
            if status == PARSE_RESULT.INCOMPLETE:
                return status

            # If message is OK, add it to receive queue or send to the callback method
            if status == PARSE_RESULT.OK and packet:
                packet.received = datetime.datetime.now()

                if isinstance(packet, UTETeachInPacket) and self.teach_in:
                    response_packet = packet.create_response_packet(self.base_id)
                    self.logger.info('Sending response to UTE teach-in.')
                    self.send(response_packet)

                if self._outside_callback is None:
                    self.receive.put(packet)
                else:
                    self.__callback_wrapper(packet)
                self.logger.debug(packet)

    @property
    def base_id(self):
        ''' Fetches Base ID from the transmitter, if required. Otherwise returns the currently set Base ID. '''
        # If base id is already set, return it.
        if self._base_id is not None:
            return self._base_id

        # Send COMMON_COMMAND 0x08, CO_RD_IDBASE request to the module
        super().send(Packet(PACKET.COMMON_COMMAND, data=[0x08]))
        # Loop over 10 times, to make sure we catch the response.
        # Thanks to timeout, shouldn't take more than a second.
        # Unfortunately, all other messages received during this time are ignored.
        for i in range(0, 10):
            try:
                packet = self.receive.get(block=True, timeout=0.1)
                # We're only interested in responses to the request in question.
                if packet.packet_type == PACKET.RESPONSE and packet.response == RETURN_CODE.OK and len(packet.response_data) == 4:  # noqa: E501
                    # Base ID is set in the response data.
                    self._base_id = packet.response_data
                    # Put packet back to the Queue, so the user can also react to it if required...
                    self.receive.put(packet)
                    break
                # Put other packets back to the Queue.
                self.receive.put(packet)
            except queue.Empty:
                continue
        # Return the current Base ID (might be None).
        return self._base_id
    
if __name__ == '__main__':

    def cb(package:Packet):
        print("Callback Base id: " + b2s(package.data[1:]))
        print(package)

    # com = ESP3SerialCommunicator("COM12", callback=cb)
    # com.start()
    # com.is_serial_connected.wait(timeout=10)
    # asyncio.run( com.send(Packet(PACKET.COMMON_COMMAND, data=[0x08])) )
    

    # ser = serial.Serial("COM12", 57600, timeout=0.1)

    # # org = 0xF6  # org = 0x05, rorg = 0xF6
    # # package_type = 0x01  # Radio_ERP_1
    # # telegram_count = 0x02  # Sub-Telegram Count
    # # header_checksum = 0x7A
    # # h_seq = property(lambda self: 3 if self.outgoing else 0)
    # # data = [0x70]
    # # address = [0xFF,0xD6,0x30,0x01]
    # # status = 0x00

    # # # 55 00 07 07 01 7A F6 70 FF B9 FC 8D 30 02 FF FF FF FF 44 00 F8
    # # body = bytes((0x07, 0x07, package_type, header_checksum, org, *data, *address, status, telegram_count, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF))

    # # data = b"\x55\x00" + body
    # # msg = data + crc8.crc8(data[1:]).digest()

    # msg = MY_RPSMessage(b'\xFF\xD6\x30\x01',0x00, b'\x70', True)

    # ser.write(msg.serialize())
    # ser.read_all()

    # print("\n\n")
    # time.sleep(2)

    # ser.close()

    # exit(0)

    com = ESP3SerialCommunicator("COM12", callback=cb, esp2_translation_enabled=False)
    com.start()
    com.is_serial_connected.wait(timeout=10)
    com.set_callback(None)

    if com.base_id:
        print("base_id: "+ b2s(com.base_id) +"\n\n")

    com.set_callback(cb)
    com.base_id
    
    # asyncio.run( com.send(RPSMessage(address=b'\xFF\xD6\x30\x01', status=b'\x30', data=b'\x50', outgoing=True)) )
    command=[RORG.BS4, 0x01, 0x00, 0x00, 0x09]
    command.extend([0xFF,0xD6,0x30, 0x01])
    command.extend([0x00])

    optional=[0x03, 0xFF,0xFF,0xFF,0xFF,0xFF]

    asyncio.run( com.send(Packet(PACKET.RADIO_ERP1, command, optional)) )

    command=[RORG.RPS, 0x01, 0x00, 0x00, 0x09]
    command.extend([0xFF,0xD6,0x30, 0x01])
    command.extend([0x00])
    asyncio.run( com.send(Packet(PACKET.RADIO_ERP1, command, optional)) )

    sender = [0xFF,0xD6,0x30,0x01]
    status = [0x30]

    command=[RORG.RPS, 0x30]
    command.extend(sender)
    command.extend(status)

    destination = [0xFF,0xFF,0xFF,0xFF]# [0xFF,0xA2,0x24,0x01]
    
    
    # command.extend([0xFF,0xD6,0x30,0x01])
    # command.extend([0x00])

    # p = RadioPacket.create(RORG.RPS, rorg_func=0x02, rorg_type=0x02, command=command, destination=destination, sender=sender)
    # p = Packet(packet_type = 0x01, data=command)
    # p.status = 0x30
    # p.data[1] = 0x30
    # p.data[6] = 0x30
    
    p = ESP3SerialCommunicator.convert_esp2_to_esp3_message(RPSMessage(b'\xFF\xD6\x30\x01', 0x30, b'\x30', True))


    # p = ESP3SerialCommunicator.convert_esp2_to_esp3_message(Regular4BSMessage(b'\xFF\xD6\x30\x01', 0x00, b'\x01\x00\x00\x09', True))
    # asyncio.run( com.send(p) )

    print("\n\n")
    # time.sleep(3)

    address = b'\xFF\xD6\x30\x01'
    # esp2_msg = Regular4BSMessage(address, 0x00, bytes((0x01, 0x00, 0x00, 0x09)), True)
    
    esp2_msg = A5_38_08(command=0x01, switching=CentralCommandSwitching(0, 1, 0, 0, 1)).encode_message(address)
    esp2_msg2 = Regular4BSMessage(address, 0x00, b'\x01\x00\x00\x09', True)

    print("ESP2: "+b2s(esp2_msg.serialize()))
    p = ESP3SerialCommunicator.convert_esp2_to_esp3_message(esp2_msg)
    print(', '.join([hex(i) for i in p.build()]))

    # p = ESP3SerialCommunicator.convert_esp2_to_esp3_message(RPSMessage(b'\xFF\xD6\x30\x01', 0x30, b'\x10', True))
    # p = ESP3SerialCommunicator.convert_esp2_to_esp3_message(Regular4BSMessage(b'\xFF\x82\x3E\x70', 0x00, bytes((0x01, 0x00, 0x00, 0x08)), True))
    print("ESP3: " + b2s(bytes(p.build())) )
    print("ESP2: " + b2s(ESP3SerialCommunicator.convert_esp3_to_esp2_message(p).serialize() ))
    
    asyncio.run( com.send(p) )


    print("\n\n")
    time.sleep(2)

    

    com.stop()
    exit(0)

    data = [0xf6, 0x50, 0xff, 0xa2, 0x24, 0x1, 0x30]
    body:bytes = bytes([0x0b, 0x05] + data[1:2] + [0,0,0] + data[2:])
    msg =  prettify( ESP2Message(body) )
    print( msg )

    # command = [0xA5, 0x02, 0x01, 0x01, 0x09] # data
    # command.extend([0xFF, 0xD6, 0x30, 0x01]) # address
    # command.extend([0x00])  #status
    # packet = RadioPacket(0x01, command, [])
    # print(packet)

    packet = RadioPacket.create(rorg=RORG.RPS, 
                                rorg_func=0x02, 
                                rorg_type=0x02,
                                sender=[0xFF,0xD6,0x30,0x01],
                                command=[0x01, 0x00, 0x00, 0x09]
                                )
    print(packet)

    packet = ESP3SerialCommunicator.convert_esp2_to_esp3_message(msg)
    print(packet)