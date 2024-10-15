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
from .gateway import EnOceanGateway

VIRT_GW_ID = 0
VIRT_GW_PORT = 12345
VIRT_GW_DEVICE_NAME = "ESP2 Netowrk Reverse Bridge"
BUFFER_SIZE = 1024
MAX_MESSAGE_DELAY = 5
LOGGING_PREFIX_VIRT_GW = "VirtGw"
DEVICE_ID = "VirtGw"


class VirtualNetworkGateway():

    incoming_message_queue = queue.Queue()
    sending_gateways = []

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        
        self.host = "0.0.0.0"

        self.hass = hass
        self.config_entry = config_entry
        self._running = False
        self.hass = hass
        self.zeroconf:Zeroconf = None

        self._register_device()

    def _register_device(self) -> None:
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, "gateway_"+str(VIRT_GW_ID))},
            # connections={(CONF_MAC, config_helpers.format_address(self.base_id))},
            manufacturer=MANUFACTURER,
            name= self.dev_name,
            model=self.model,
        )

    @property
    def dev_id(self):
        return VIRT_GW_ID
    
    @property
    def dev_name(self):
        return VIRT_GW_DEVICE_NAME
    
    @property
    def dev_type(self):
        return GatewayDeviceType.LAN_ESP2.value

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
                gw_type_id:int = GatewayDeviceType.indexOf(gw.dev_type)
                data:bytes = b'\x8b\x98' + gw.base_id[0] + gw_type_id.to_bytes(1, 'big') + b'\x00\x00\x00\x00'
                LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Send gateway info {gw} (id: {gw.dev_id}, base id: {b2s(gw.base_id[0])}, type: {gw.dev_type} / {gw_type_id}) ")
                conn.sendall( ESP2Message(bytes(data)).serialize() )
            except Exception as e:
                LOGGER.exception(e)


    def handle_client(self, conn: socket.socket, addr: socket.AddressInfo):
        LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Connected client by {addr}")
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
                            LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Forward EnOcean message {msg}")
                            conn.sendall(msg.serialize())
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
            LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Handler for {addr} exiting. (Thread flag running: {self._running})")


    def tcp_server(self):
        """Basic TCP Server that listens for connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()

            # Get the hostname
            hostname = socket.gethostname()
            # Get the IP address
            ip_address = socket.gethostbyname(hostname)

            LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Virtual Network Gateway Adapter listening on {hostname}({ip_address}):{self.port}")

            # Register the service
            try:
                service_info: ServiceInfo = self.get_service_info(hostname, ip_address)
                self.zeroconf.register_service(service_info)
                LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] registered mDNS service record created.")
            except Exception as e:
                LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW} {e}]")

            while self._running:
                try:
                    # LOGGER.debug("[%s] Try to connect", LOGGING_PREFIX)
                    conn, addr = s.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] Connection from: {addr} established")
                    
                    client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    client_thread.start()
                            
                except Exception as e:
                    LOGGER.error(f"[{LOGGING_PREFIX_VIRT_GW}] An error occurred: {e}", exc_info=True, stack_info=True)


            self.zeroconf.unregister_service(service_info)
            
        LOGGER.info(f"[{LOGGING_PREFIX_VIRT_GW}] Closed TCP Server")


    def restart_tcp_server(self):
        if self._running:
            self.stop_tcp_server()
        
        self.start_tcp_server()

    def start_tcp_server(self):
        """Start TCP server in a separate thread."""
        if not self._running:
            self._running = True
            self.tcp_thread = threading.Thread(target=self.tcp_server)
            self.tcp_thread.daemon = True
            # self.tcp_thread.start()


    def stop_tcp_server(self):
        self._running = False
        # self.tcp_thread.join()

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

        self.zeroconf:Zeroconf = await zeroconf.async_get_instance(self.hass)

        self.start_tcp_server()
        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] [Id: {VIRT_GW_ID}] Was started.")

        # receive messages from HA event bus
        # event_id = config_helpers.get_bus_event_type(self.dev_id, SIGNAL_SEND_MESSAGE)
        # self.dispatcher_disconnect_handle = async_dispatcher_connect(
        #     self.hass, event_id, self._callback_send_message_to_serial_bus
        # )

    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

        self.stop_tcp_server()

        LOGGER.debug(f"[{LOGGING_PREFIX_VIRT_GW}] [Id: {VIRT_GW_ID}] Was stopped.")