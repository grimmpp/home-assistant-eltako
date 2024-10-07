import socket
import threading
import logging

from .const import *

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

TCP_IP = '0.0.0.0'
TCP_PORT = 12345
BUFFER_SIZE = 1024

LOGGING_PREFIX = "VMGW"

class VirtualTCPServer:

    def __init__(self):
        self._not_stopped = False


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((TCP_IP, TCP_PORT))
        s.listen()

        # Get the hostname
        hostname = socket.gethostname()
        # Get the IP address
        ip_address = socket.gethostbyname(hostname)

        LOGGER.debug("[%s] TCP server listening on %s(%s):%s", LOGGING_PREFIX, hostname, ip_address, TCP_PORT)

        while self._not_stopped:
            try:
                conn, addr = s.accept()
                LOGGER.debug("[%s] Connection from: %s", LOGGING_PREFIX, addr)
                with conn:
                    while self._not_stopped:
                        LOGGER.debug('[%s] Connected by', LOGGING_PREFIX, addr)
                        data = conn.recv(BUFFER_SIZE)
                        if not data:
                            break
                        LOGGER.debug("[%s] Received data: %s", LOGGING_PREFIX, data.decode("utf-8"))
                        # You can implement custom logic here to trigger Home Assistant services or update entities.
            except Exception as e:
                LOGGER.debug("[%s] An error occurred: {e}")
            finally:
                conn.close()
                LOGGER.debug("[%s] Connection closed!")

    def start_tcp_server(self):
        """Start TCP server in a separate thread."""
        self._not_stopped = True
        self.tcp_thread = threading.Thread(target=self.tcp_server)
        self.tcp_thread.daemon = True
        self.tcp_thread.start()
        LOGGER.info("[%s] TCP Server started", LOGGING_PREFIX)

    def stop_tcp_server(self):
        self._not_stopped = False
        self.tcp_thread.join()
