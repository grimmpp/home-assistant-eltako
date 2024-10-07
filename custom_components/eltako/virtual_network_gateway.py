import socket
import threading
import logging

from .const import *

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

BUFFER_SIZE = 1024

LOGGING_PREFIX = "VMGW"

class VirtualTCPServer:

    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 12345
        self._not_stopped = False


    def handle_client(self, conn, addr):
        LOGGER.info(f"[{LOGGING_PREFIX}] Connected client by {addr}")
        try:
            with conn:
                while self._not_stopped:
                    # Receive data from the client
                    data = conn.recv(1024)
                    if not data:
                        print(f"[{LOGGING_PREFIX}] Connection closed by {addr}")
                        break  # No data means the client has closed the connection
                    print(f"[{LOGGING_PREFIX}] Received from {addr}: {data.decode()}")
                    # Echo the received data back to the client
                    conn.sendall(data)  # Send data back to the client
        except Exception as e:
            LOGGER.info(f"[{LOGGING_PREFIX}] An error occurred with {addr}: {e}")
        finally:
            LOGGER.info(f"[{LOGGING_PREFIX}] Handler for {addr} exiting.")


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()

            # Get the hostname
            hostname = socket.gethostname()
            # Get the IP address
            ip_address = socket.gethostbyname(hostname)

            LOGGER.info("[%s] TCP server listening on %s(%s):%s", LOGGING_PREFIX, hostname, ip_address, self.port)

            while self._not_stopped:
                try:
                    LOGGER.debug("[%s] Try to connect", LOGGING_PREFIX)
                    conn, addr = s.accept()
                    LOGGER.debug("[%s] Connection from: %s established", LOGGING_PREFIX, addr)
                    
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    client_thread.start()
                            
                except Exception as e:
                    LOGGER.debug("[%s] An error occurred: {e}")
            


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
