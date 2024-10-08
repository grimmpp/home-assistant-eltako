import socket
import threading
import queue
import time

from eltakobus.message import ESP2Message
from eltakobus.util import b2s, AddressExpression

from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr

from .const import *
from . import config_helpers

BUFFER_SIZE = 1024
MAX_MESSAGE_DELAY = 5
LOGGING_PREFIX = "VMGW"

CENTRAL_VIRTUAL_NETWORK_GATEWAY = None

def create_central_virtual_network_gateway(hass):
    global CENTRAL_VIRTUAL_NETWORK_GATEWAY
    if CENTRAL_VIRTUAL_NETWORK_GATEWAY is None:
        CENTRAL_VIRTUAL_NETWORK_GATEWAY = VirtualNetworkGateway(hass)
    
    CENTRAL_VIRTUAL_NETWORK_GATEWAY.restart_tcp_server()
    
    return CENTRAL_VIRTUAL_NETWORK_GATEWAY

def stop_central_virtual_network_gateway():
    global CENTRAL_VIRTUAL_NETWORK_GATEWAY
    if CENTRAL_VIRTUAL_NETWORK_GATEWAY is None:
        CENTRAL_VIRTUAL_NETWORK_GATEWAY.stop_tcp_server()

class VirtualNetworkGateway:

    incoming_message_queue = queue.Queue()
    sending_gateways = []

    def __init__(self, hass):
        self.host = "0.0.0.0"
        self.port = 12345
        self._running = False
        self.hass = hass
        
    def forward_message(self, gateway, msg: ESP2Message):
        if gateway not in self.sending_gateways:
            self.sending_gateways.append(gateway)
        
        self.incoming_message_queue.put((time.time(),msg))

    def convert_bus_address_to_external_address(self, gateway, msg):
        address = msg.body[6:10]
        if address[0] == 0 and address[1] == 0:
            LOGGER.debug(f"TODO: create external id")
        
        return msg

    def send_gateway_info(self, conn: socket.socket):
        for gw in self.sending_gateways:
            try:
                data = b'\x8b\x98' + gw.base_id[0] + b'\x00\x00\x00\x00\x00'
                LOGGER.debug(f"Send gateway info {gw} (id: {gw.dev_id}, base id: {b2s(gw.base_id[0])}, type: {gw.dev_type})")
                conn.sendall( ESP2Message(bytes(data)).serialize() )
            except Exception as e:
                LOGGER.exception(e)

    def handle_client(self, conn: socket.socket, addr: socket.AddressInfo):
        LOGGER.info(f"[{LOGGING_PREFIX}] Connected client by {addr}")
        try:
            with conn:
                self.send_gateway_info(conn)

                # send messages coming in and out
                while self._running:
                    # Receive data from the client
                    try:
                        package = self.incoming_message_queue.get(timeout=1)
                        t = package[0]
                        msg:ESP2Message = package[1]
                        if time.time() - t < MAX_MESSAGE_DELAY:
                            LOGGER.debug(f"[{LOGGING_PREFIX}] Forward EnOcean message {msg}")
                            conn.sendall(msg.serialize())
                        else:
                            LOGGER.debug(f"[{LOGGING_PREFIX}] EnOcean message {msg} expired (Max delay: {MAX_MESSAGE_DELAY})")
                    except:
                        # send keep alive message
                        conn.sendall(b'IM2M')

        except ConnectionResetError:
            pass
        except Exception as e:
            LOGGER.error(f"[{LOGGING_PREFIX}] An error occurred with {addr}: {e}", exc_info=True, stack_info=True)
        finally:
            LOGGER.info(f"[{LOGGING_PREFIX}] Handler for {addr} exiting. (Thread flag running: {self._running})")


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()

            # Get the hostname
            hostname = socket.gethostname()
            # Get the IP address
            ip_address = socket.gethostbyname(hostname)

            LOGGER.info(f"[{LOGGING_PREFIX}] TCP server listening on {hostname}({ip_address}):{self.port}")

            while self._running:
                try:
                    # LOGGER.debug("[%s] Try to connect", LOGGING_PREFIX)
                    conn, addr = s.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    LOGGER.debug(f"[{LOGGING_PREFIX}] Connection from: {addr} established")
                    
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    client_thread.start()
                            
                except Exception as e:
                    LOGGER.error(f"[{LOGGING_PREFIX}] An error occurred: {e}", exc_info=True, stack_info=True)
            
        LOGGER.info(f"[{LOGGING_PREFIX}] Closed TCP Server")


    def restart_tcp_server(self):
        if self._running:
            self._running = False
            self.stop_tcp_server()
        
        self.start_tcp_server()

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
