# -*- encoding: utf-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import
import logging
import serial
import time
import threading

from enocean.communicators.communicator import Communicator


class ESP3SerialCommunicator(Communicator):
    ''' Serial port communicator class for EnOcean radio '''

    def __init__(self, filename, log=None, callback=None, baud_rate=57600, reconnection_timeout:float=10):
        super(ESP3SerialCommunicator, self).__init__(callback)
        
        self.filename = filename
        self.log = log or logging.getLogger('enocean.communicators.SerialCommunicator')

        self.baud_rate = baud_rate
        self.__recon_time = reconnection_timeout
        self.is_serial_connected = threading.Event()

    def is_active(self) -> bool:
        return not self._stop_flag.is_set() and self.is_serial_connected.is_set()     

    def reconnect(self):
        self._stop_flag.set()
        self._stop_flag.wait()
        self.start()

    def run(self):
        self.logger.info('SerialCommunicator started')
        while not self._stop_flag.is_set():
            try:
                # Initialize serial port
                if self.__ser is None:
                    self.__ser = serial.Serial(self.filename, self.baud_rate, timeout=0.1)
                    self.log.info("Established serial connection to %s - baudrate: %d", self._filename, self._baud_rate)
                    self.is_serial_connected.set()

                # If there's messages in transmit queue
                # send them
                while True:
                    packet = self._get_from_send_queue()
                    if not packet:
                        break
                    try:
                        self.__ser.write(bytearray(packet.build()))
                    except serial.SerialException:
                        self.stop()

                # Read chars from serial port as hex numbers
                try:
                    self._buffer.extend(bytearray(self.__ser.read(16)))
                except serial.SerialException:
                    self.logger.error('Serial port exception! (device disconnected or multiple access on port?)')
                    self.stop()
                self.parse()
                time.sleep(0)

            except (serial.SerialException, IOError) as e:
                self.is_serial_connected.clear()
                self.log.error(e)
                self.__ser = None
                self.log.info("Serial communication crashed. Wait %s seconds for reconnection.", self.__recon_time)
                time.sleep(self.__recon_time)

        self.__ser.close()
        self.logger.info('SerialCommunicator stopped')