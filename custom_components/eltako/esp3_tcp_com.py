import socket
import time
import logging

# from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange

from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator


# def detect_lan_gateways() -> list[str]:
#     result = []

#     zeroconf = Zeroconf()

#     def on_service_state_change(zeroconf, service_type, name, state_change):
#         if state_change is ServiceStateChange.Added:
#             zeroconf.get_service_info(service_type, name)

#     name = '_bsc-sc-socket._tcp.local.'
#     ServiceBrowser(zeroconf, name, handlers=[on_service_state_change])
    
#     time.sleep(2)
    
#     alias = zeroconf.cache.entries_with_name('_bsc-sc-socket._tcp.local.')[0].alias
#     service_name = alias.split('.')[0] + '.local.'

#     for e in zeroconf.cache.entries_with_name(service_name):
#         if 'record[a' in str(e):
#             ip_adr = str(e).split('=')[1].split(',')[1]
#             if ip_adr not in result:
#                 result.append(ip_adr)

#     zeroconf.close()
    
#     return result


class TCP2SerialCommunicator(ESP3SerialCommunicator):

    def __init__(self, 
                 host, 
                 port,
                 log=None, 
                 callback=None, 
                 reconnection_timeout:float=10,
                 esp2_translation_enabled:bool=False,  
                 auto_reconnect=True):
        
        self.__recon_time = reconnection_timeout
        self.esp2_translation_enabled = esp2_translation_enabled
        self._outside_callback = callback
        self._auto_reconnect = auto_reconnect

        super(TCP2SerialCommunicator, self).__init__(None, log, callback, None, reconnection_timeout, esp2_translation_enabled, auto_reconnect)

        self._host = host
        self._port = port
        
        self.log = log or logging.getLogger('eltakobus.tcp2serial')

        self.__ser = None


    def _test_connection(self):
        sent = self.__ser.send(b'\xff\x00\xff' * 5)
        if sent == 0:
            raise Exception("Data was not sent.")
        try:
            self.__ser.recv(1024)
        except socket.timeout as e:
            pass

    def run(self):
        timeout_count = 0
        self.logger.info('TCP2SerialCommunicator started')
        self._fire_status_change_handler(connected=False)
        while not self._stop_flag.is_set():
            try:
                # Initialize serial port
                if self.__ser is None:
                    self.__ser = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.__ser.connect((self._host, self._port))
                    self.__ser.settimeout(1)

                    # Test connection
                    self._test_connection()

                    self.log.info("Established TCP connection to %s:%s", self._host, self._port)
                    
                    self.is_serial_connected.set()
                    self._fire_status_change_handler(connected=True)
                    
                # If there's messages in transmit queue
                # send them
                while True:
                    packet = self._get_from_send_queue()
                    if not packet:
                        break
                    self.log.debug("send msg: %s", packet)
                    self.__ser.sendall( bytearray(packet.build()) )

                # Read chars from serial port as hex numbers
                try:
                    data = self.__ser.recv(1024)
                    # print(hex(int.from_bytes(data, "big")))
                    if data != b'IM2M':
                        self._buffer = data
                        self.parse()
                        timeout_count = 0

                except socket.timeout as e:
                    timeout_count += 1
                    if timeout_count > self.__recon_time:
                        timeout_count = 0
                        self._test_connection()
                time.sleep(0)

            except Exception as e:
                self._fire_status_change_handler(connected=False)
                self.is_serial_connected.clear()
                self.log.error(e)
                self.__ser = None
                if self._auto_reconnect:
                    self.log.info("TCP2Serial communication crashed. Wait %s seconds for reconnection.", self.__recon_time)
                    time.sleep(self.__recon_time)
                else:
                    self._stop_flag.set()

        if self.__ser is not None:
            self.__ser.close()
            self.__ser = None
        self.is_serial_connected.clear()
        self._fire_status_change_handler(connected=False)
        self.logger.info('TCP2SerialCommunicator stopped')
