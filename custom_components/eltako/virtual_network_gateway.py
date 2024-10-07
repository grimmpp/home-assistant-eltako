import socket
import threading
import time
import queue

from eltakobus.message import ESP2Message

from .const import *

BUFFER_SIZE = 1024

LOGGING_PREFIX = "VMGW"


class VirtualNetworkGateway:

    incoming_message_queue = queue.Queue()

    def __init__(self):
        self.host = "0.0.0.0"
        self.port = 12345
        self._running = False

    def forward_message(self, msg: ESP2Message):
        self.incoming_message_queue.put(msg)

    def handle_client(self, conn: socket.socket, addr: socket.AddressInfo):
        LOGGER.info(f"[{LOGGING_PREFIX}] Connected client by {addr}")
        try:
            with conn:
                while self._running:
                    # Receive data from the client
                    msg:ESP2Message = self.incoming_message_queue.get(block=True)
                    LOGGER.info(f"[{LOGGING_PREFIX}] Received enocean message {msg}")
                    if msg:
                        conn.sendall(msg.serialize())

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
