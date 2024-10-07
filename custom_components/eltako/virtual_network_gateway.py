import socket
import threading
import time
import queue

from .const import *
from . import config_helpers
from .gateway import EnOceanGateway

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_connect

BUFFER_SIZE = 1024

LOGGING_PREFIX = "VMGW"

class VirtualNetworkGateway:

    incoming_message_queue = queue.Queue()

    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 12345
        self._running = False


    def register_gateway(self, hass, gateway:EnOceanGateway):
        event_id = config_helpers.get_bus_event_type(gateway.base_id, SIGNAL_SEND_MESSAGE)
        # dispatcher_connect(hass, event_id, self.receive_enocean_msg_from_gw)
        hass.loop.call_soon_threadsafe(dispatcher_connect, hass, event_id)


    async def receive_enocean_msg_from_gw(self, msg):
        self.incoming_message_queue.put(msg)


    def handle_client(self, conn: socket.socket, addr: socket.AddressInfo):
        LOGGER.info(f"[{LOGGING_PREFIX}] Connected client by {addr}")
        try:
            with conn:
                while self._running:
                    try:
                        # Receive data from the client
                        msg = self.incoming_message_queue.get(block=True)
                        LOGGER.info(f"[{LOGGING_PREFIX}] Received enocean message {msg}")
                        ##LOGGER.## TODO
                        if msg:
                            conn.sendall(msg)

                        time.sleep(.01)

                        # data = conn.recv(1024)
                        # if not data:
                        #     LOGGER.debug(f"[{LOGGING_PREFIX}] Connection closed by {addr}")
                        #     break  # No data means the client has closed the connection
                        # LOGGER.debug(f"[{LOGGING_PREFIX}] Received from {addr}: {data.decode()}")
                        # # Echo the received data back to the client
                        # conn.sendall(data)  # Send data back to the client
                    except Exception as e:
                        LOGGER.error(f"[{LOGGING_PREFIX}] An error occurred with {addr}: {e}", exc_info=True, stack_info=True)
                        time.sleep(1)

        except Exception as e:
            LOGGER.error(f"[{LOGGING_PREFIX}] An error occurred with {addr}: {e}", exc_info=True, stack_info=True)
        finally:
            LOGGER.info(f"[{LOGGING_PREFIX}] Handler for {addr} exiting. (Thread flag running: {self._running})")


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen(1)

            # Get the hostname
            hostname = socket.gethostname()
            # Get the IP address
            ip_address = socket.gethostbyname(hostname)

            LOGGER.info(f"[{LOGGING_PREFIX}] TCP server listening on {hostname}({ip_address}):{self.port}")

            while self._running:
                try:
                    # LOGGER.debug("[%s] Try to connect", LOGGING_PREFIX)
                    conn, addr = s.accept()
                    LOGGER.debug(f"[{LOGGING_PREFIX}] Connection from: {addr} established")
                    
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    client_thread.start()
                            
                except Exception as e:
                    LOGGER.error(f"[{LOGGING_PREFIX}] An error occurred: {e}", exc_info=True, stack_info=True)
            
        LOGGER.info(f"[{LOGGING_PREFIX}] Closed TCP Server")


    def start_tcp_server(self):
        """Start TCP server in a separate thread."""
        if not self._running:
            self._running = True
            self.tcp_thread = threading.Thread(target=self.tcp_server)
            self.tcp_thread.daemon = True
            self.tcp_thread.start()
            LOGGER.info("f[{LOGGING_PREFIX}] TCP Server started")


    def stop_tcp_server(self):
        self._running = False
        self.tcp_thread.join()
