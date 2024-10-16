import socket
import threading
import queue
import time

from zeroconf import Zeroconf, ServiceInfo

from eltakobus.message import ESP2Message
from eltakobus.util import b2s, AddressExpression

from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry

from .const import *
from . import config_helpers
from .gateway import EnOceanGateway, GLOBAL_EVENT_BUS_ID

VIRT_GW_PORT = 12345
VIRT_GW_DEVICE_NAME = "ESP2 Netowrk Reverse Bridge"
BUFFER_SIZE = 1024
MAX_MESSAGE_DELAY = 5000
LOGGING_PREFIX_VIRT_GW = "VirtGw"

class VirtualNetworkGateway(EnOceanGateway):

    incoming_message_queue = queue.Queue()
    sending_gateways:list[EnOceanGateway] = []

    def __init__(self, general_settings:dict, hass: HomeAssistant, 
                 dev_id: int, port:int, config_entry: ConfigEntry):
        
        if port is None:
            port = VIRT_GW_PORT

        self.host = "0.0.0.0"
        super().__init__(general_settings, hass,
                         dev_id, GatewayDeviceType.VirtualNetworkAdapter, "homeassistant.local", -2, port, AddressExpression.parse('00-00-00-00'), VIRT_GW_DEVICE_NAME, True, None,
                           config_entry  )

        self._running = threading.Event()
        self._running.clear()
        self.hass = hass
        self.zeroconf:Zeroconf = None

        self._register_device()

    
    @property
    def dev_name(self):
        return VIRT_GW_DEVICE_NAME
    
    @property
    def dev_type(self):
        return GatewayDeviceType.VirtualNetworkAdapter

    @property
    def model(self):
        return GATEWAY_DEFAULT_NAME + " - " + self.dev_type.upper()


    def get_service_info(self, hostname:str, ip_address:str):
        info = ServiceInfo(
            "_bsc-sc-socket._tcp.local.",
            "Virtual-Network-Gateway-Adapter._bsc-sc-socket._tcp.local.",
            addresses = [self.convert_ip_to_bytes(ip_address)],
            port=self.port,
            server=f"{hostname}.local."
        )

        return info        


    async def _forward_message(self, data:dict):
        gateway:EnOceanGateway = data['gateway']
        msg: ESP2Message = data['esp2_msg']

        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] received message: {msg} from gateway: {gateway.dev_name}")

        if gateway not in self.sending_gateways:
            self.sending_gateways.append(gateway)

        self.incoming_message_queue.put((time.time(), msg))


    def convert_bus_address_to_external_address(self, gateway, msg):
        address = msg.body[6:10]
        if address[0] == 0 and address[1] == 0:
            LOGGER.debug(f"TODO: create external id")
        
        return msg


    def send_gateway_info(self, conn: socket.socket):
        for gw in self.sending_gateways:
            try:
                ## send base id and put gateway type as well into it
                msg = gw.create_base_id_infO_message()
                LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Send gateway info {gw} (id: {gw.dev_id}, base id: {b2s(gw.base_id[0])}, type: {gw.dev_type}) ")
                conn.sendall( msg.serialize() )

                ## request gateway version
                #TODO: ...
            except Exception as e:
                LOGGER.exception(e)


    def handle_client(self, conn: socket.socket, addr: socket.AddressInfo):
        LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Connected client by {addr}")
        try:
            with conn:
                self.send_gateway_info(conn)

                # send messages coming in and out
                while self._running.is_set():
                    # Receive data from the client
                    try:
                        package = self.incoming_message_queue.get(timeout=1)
                        t = package[0]
                        msg:ESP2Message = package[1]
                        if time.time() - t < MAX_MESSAGE_DELAY:
                            LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Forward EnOcean message {msg}")
                            conn.sendall(msg.serialize())

                            self._fire_received_message_count_event()
                            self._fire_last_message_received_event()
                        else:
                            LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] EnOcean message {msg} expired (Max delay: {MAX_MESSAGE_DELAY})")
                    except:
                        # send keep alive message
                        conn.sendall(b'IM2M')

        except ConnectionResetError:
            pass
        except BrokenPipeError:
            pass
        except Exception as e:
            LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW}] An error occurred with {addr}: {e}", exc_info=True, stack_info=True)
        finally:
            LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Handler for {addr} exiting. (Thread flag running: {self._running.is_set()})")


    async def query_for_base_id_and_version(self, connected):
        pass


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            s.settimeout(1.0)   # Set timeout so it can periodically check for shutdown

            # Get the hostname
            hostname = socket.gethostname()
            # Get the IP address
            ip_address = socket.gethostbyname(hostname)

            LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Virtual Network Gateway Adapter listening on {hostname}({ip_address}):{self.port}")
            self._fire_connection_state_changed_event(True)
            self._received_message_count = 0

            # Register the service
            try:
                service_info: ServiceInfo = self.get_service_info(hostname, ip_address)
                self.zeroconf.register_service(service_info)
                LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] registered mDNS service record created.")
            except Exception as e:
                LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW} {e}]")

            while self._running.is_set():
                try:
                    # LOGGER.debug("[%s] Try to connect", LOGGING_PREFIX)
                    conn, addr = s.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Connection from: {addr} established")
                    
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    client_thread.start()
                
                except socket.timeout:
                    # Timeout used to periodically check for shutdown
                    continue

                except Exception as e:
                    LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW}] An error occurred: {e}", exc_info=True, stack_info=True)

            self.zeroconf.unregister_service(service_info)
        
        self._fire_connection_state_changed_event(False)
        LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Closed TCP Server")


    def reconnect(self):
        self.restart_tcp_server()


    def restart_tcp_server(self):
        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Restart TCP server")
        if self._running.is_set():
            self.stop_tcp_server()
        
        self.start_tcp_server()


    def start_tcp_server(self):
        """Start TCP server in a separate thread."""
        if not self._running.is_set():
            self._running.set()
            self.tcp_thread = threading.Thread(target=self.tcp_server)
            self.tcp_thread.daemon = True
            self.tcp_thread.start()
            self._fire_connection_state_changed_event(True)


    def stop_tcp_server(self):
        self._running.clear()
        self.tcp_thread.join(10)
        self._fire_connection_state_changed_event(False)


    def convert_ip_to_bytes(self, ip_address_str):
        try:
            if ":" in ip_address_str:  # Check for IPv6
                return socket.inet_pton(socket.AF_INET6, ip_address_str)
            else:  # Assume IPv4
                return socket.inet_aton(ip_address_str)
            
        except socket.error as e:
            LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW}] Invalid IP address: {ip_address_str} - {e}")


    async def async_setup(self):
        """Initialized tcp server and register callback function on HA event bus."""

        # register for all incoming and outgoing messages from all gateways
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, GLOBAL_EVENT_BUS_ID, self._forward_message
        )

        self.zeroconf:Zeroconf = await zeroconf.async_get_instance(self.hass)

        self.start_tcp_server()

        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Was started.")


    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

        self.stop_tcp_server()

        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Was stopped.")