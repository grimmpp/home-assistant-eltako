import socket
import threading
import logging

from .const import *

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

TCP_IP = '0.0.0.0'
TCP_PORT = 12345
BUFFER_SIZE = 1024

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

        LOGGER.info("TCP server listening on %s(%s):%s", hostname, ip_address, TCP_PORT)

        while self._not_stopped:
            conn, addr = s.accept()
            LOGGER.info("Connection from: %s", addr)
            
            while self._not_stopped:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                LOGGER.info("Received data: %s", data.decode("utf-8"))
                # You can implement custom logic here to trigger Home Assistant services or update entities.
            
            conn.close()

    def start_tcp_server(self):
        """Start TCP server in a separate thread."""
        self._not_stopped = True
        self.tcp_thread = threading.Thread(target=self.tcp_server)
        self.tcp_thread.daemon = True
        self.tcp_thread.start()
        LOGGER.info("TCP Server started")

    def stop_tcp_server(self):
        self._not_stopped = False
        self.tcp_thread.join()
