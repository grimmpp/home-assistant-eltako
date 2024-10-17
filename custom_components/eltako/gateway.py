import glob
"""Representation of an Eltako gateway."""

from os.path import basename, normpath
import pytz
from datetime import datetime, UTC

import serial
import asyncio

from eltakobus.serial import RS485SerialInterfaceV2
from eltakobus.message import *
from eltakobus.util import AddressExpression, b2s
from eltakobus.eep import EEP
from eltakobus.device import sorted_known_objects
from eltakobus import locking

from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
from esp2_gateway_adapter.esp3_tcp_com import TCP2SerialCommunicator

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.config_entries import ConfigEntry

from .const import *
from . import config_helpers

import threading


async def async_get_base_ids_of_registered_gateway(device_registry: DeviceRegistry) -> list[str]:
    base_id_list = []
    for d in device_registry.devices.values():
        if d.model and d.model.startswith(GATEWAY_DEFAULT_NAME):
            base_id_list.append( list(d.connections)[0][1] )
    return base_id_list


async def async_get_serial_path_of_registered_gateway(device_registry: DeviceRegistry) -> list[str]:
    serial_path_list = []
    for d in device_registry.devices.values():
        if d.model and d.model.startswith(GATEWAY_DEFAULT_NAME):
            serial_path_list.append( list(d.identifiers)[0][1] )
    return serial_path_list


class EnOceanGateway:
    """Representation of an Eltako gateway.

    The gateway is responsible for receiving the Eltako frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    def __init__(self, general_settings:dict, hass: HomeAssistant, 
                 dev_id: int, dev_type: GatewayDeviceType, serial_path: str, baud_rate: int, port: int, base_id: AddressExpression, dev_name: str, auto_reconnect: bool=True, message_delay:float=None, 
                 config_entry: ConfigEntry = None):

        """Initialize the Eltako gateway."""

        self._loop = asyncio.get_event_loop()
        self._bus_task = None
        self.baud_rate = baud_rate
        self._auto_reconnect = auto_reconnect
        self._message_delay = message_delay
        self.port = port
        self._attr_dev_type = dev_type
        self._attr_serial_path = serial_path
        self._attr_identifier = basename(normpath(serial_path))
        self.hass: HomeAssistant = hass
        self.dispatcher_disconnect_handle = None
        self.general_settings = general_settings
        self._attr_dev_id = dev_id
        self._attr_base_id = base_id
        self.config_entry_id = config_entry.entry_id

        self._last_message_received_handler = None
        self._connection_state_handlers = []
        self._base_id_change_handlers = []
        self._received_message_count_handler = None

        self._attr_model = GATEWAY_DEFAULT_NAME + " - " + self.dev_type.upper()

        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self.native_protocol = 'ESP2'
        else:
            self.native_protocol = 'ESP3'
        self._original_dev_name = dev_name
        self._attr_dev_name = config_helpers.get_gateway_name(self._original_dev_name, self.dev_type.value, self.dev_id)

        self._reading_memory_of_devices_is_running = threading.Event()

        self._init_bus()

        self._register_device()

        self.add_connection_state_changed_handler(self.query_for_base_id_and_version)


    async def query_for_base_id_and_version(self, connected):
        if connected:
            if not GatewayDeviceType.is_esp2_gateway(self.dev_type):
                LOGGER.debug("[Gateway] [Id: %d] Query for base id and version info.", self.dev_id)
                await self._bus.send_base_id_request()
                await self._bus.send_version_request()

            elif self.dev_type == GatewayDeviceType.GatewayEltakoFAM14:
                await asyncio.to_thread(asyncio.run, self.get_fam14_base_id())



    def add_base_id_change_handler(self, handler):
        self._base_id_change_handlers.append(handler)

    def _fire_base_id_change_handlers(self, base_id: AddressExpression):
        for handler in self._base_id_change_handlers:
            self.hass.create_task(
                handler(base_id)
            )

    def add_connection_state_changed_handler(self, handler):
        self._connection_state_handlers.append(handler)
        self._fire_connection_state_changed_event(self._bus.is_active())


    def _fire_connection_state_changed_event(self, status):
        for handler in self._connection_state_handlers:
            self.hass.create_task(
                handler(status)
            )


    def set_last_message_received_handler(self, handler):
        self._last_message_received_handler = handler


    def _fire_last_message_received_event(self):
        if self._last_message_received_handler:
            self.hass.create_task(
                self._last_message_received_handler( datetime.now(UTC).replace(tzinfo=pytz.UTC) )
            )


    def set_received_message_count_handler(self, handler):
        self._received_message_count_handler = handler


    def _fire_received_message_count_event(self):
        self._received_message_count += 1
        if self._received_message_count_handler:
            self.hass.create_task(
                self._received_message_count_handler( self._received_message_count ),
            )

    def report_message_stats(self, data=None):
        """Received message from bus in HA loop. (Actions needs to run outside bus thread!)"""
        self._fire_received_message_count_event()
        self._fire_last_message_received_event()

    
    def _init_bus(self):
        self._received_message_count = 0
        self._fire_received_message_count_event()

        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self._bus = RS485SerialInterfaceV2(self.serial_path, 
                                               baud_rate=self.baud_rate, 
                                               callback=self._callback_receive_message_from_serial_bus, 
                                               delay_message=self._message_delay,
                                               auto_reconnect=self._auto_reconnect)
            
        elif GatewayDeviceType.is_lan_gateway(self.dev_type) and not GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self._bus = TCP2SerialCommunicator(host=self.serial_path, 
                                               port=self.port, 
                                               callback=self._callback_receive_message_from_serial_bus, 
                                               esp2_translation_enabled=True,
                                               auto_reconnect=self._auto_reconnect)
        else:
            self._bus = ESP3SerialCommunicator(filename=self.serial_path, 
                                               callback=self._callback_receive_message_from_serial_bus, 
                                               esp2_translation_enabled=True, 
                                               auto_reconnect=self._auto_reconnect)
        
        self._bus.set_status_changed_handler(self._fire_connection_state_changed_event)


    def _register_device(self) -> None:
        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry_id,
            identifiers={(DOMAIN, self.serial_path)},
            # connections={(CONF_MAC, config_helpers.format_address(self.base_id))},
            manufacturer=MANUFACTURER,
            name= self.dev_name,
            model=self.model,
        )
        

    ### address validation functions

    def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        if GatewayDeviceType.is_transceiver(self.dev_type):
            return self.sender_id_validation_by_transmitter(sender_id, device_name)
        elif GatewayDeviceType.is_bus_gateway(self.dev_type):
            return self.sender_id_validation_by_bus_gateway(sender_id, device_name)
        return False
    

    def sender_id_validation_by_transmitter(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        result = config_helpers.compare_enocean_ids(self.base_id[0], sender_id[0])
        if not result:
            LOGGER.warning(f"{device_name} ({sender_id}): Maybe have wrong sender id configured!")
        return result
    

    def sender_id_validation_by_bus_gateway(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        return True # because no sender telegram is leaving the bus into wireless, only status update of the actuators and those ids are bease on the baseId.
    

    def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        if GatewayDeviceType.is_transceiver(self.dev_type):
            return self.dev_id_validation_by_transmitter(dev_id, device_name)
        elif GatewayDeviceType.is_bus_gateway(self.dev_type):
            return self.dev_id_validation_by_bus_gateway(dev_id, device_name)
        return False


    def dev_id_validation_by_transmitter(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = 0xFF == dev_id[0][0]
        if not result:
            LOGGER.warning(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
        return result
    

    def dev_id_validation_by_bus_gateway(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = config_helpers.compare_enocean_ids(b'\x00\x00\x00\x00', dev_id[0], len=2)
        if not result:
            LOGGER.warning(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
        return result
    

    ### send and receive funtions for RS485 bus (serial bus)
    ### all events are looped through the HA event bus so that other automations can work with those events. History about events can aslo be created.

    async def get_fam14_base_id(self):
        LOGGER.debug("[Gateway] [Id: %d] Try to read base id of FAM14", self.dev_id)
        is_locked = False
        try:
            self._bus.set_callback( None )

            is_locked = (await locking.lock_bus(self._bus)) == locking.LOCKED
            
            # first get fam14 and make it know to data manager
            response:EltakoMemoryResponse = await self._bus.exchange(EltakoMemoryRequest(255, 1), EltakoMemoryResponse)
            base_id_str = b2s(response.value[0:4])

            # fam14:FAM14 = await create_busobject(bus=self._bus, id=255)
            # base_id_str = await fam14.get_base_id()
            self._attr_base_id = AddressExpression.parse( base_id_str )
            LOGGER.info("[Gateway] [Id: %d] Found base id for FAM14 %s", self.dev_id, base_id_str)
            self._fire_base_id_change_handlers(self.base_id)

        except Exception as e:
            LOGGER.error("[Gateway] [Id: %d] Failed to load base_id from FAM14.", self.dev_id)
            raise e
        finally:
            if is_locked:
                resp = await locking.unlock_bus(self._bus)
            self._bus.set_callback( self._callback_receive_message_from_serial_bus )


    async def read_memory_of_all_bus_members(self):
        if not self._reading_memory_of_devices_is_running.is_set():
            await asyncio.to_thread(asyncio.run, self._read_memory_of_all_bus_members())


    async def _read_memory_of_all_bus_members(self):
        
        if self.dev_type == GatewayDeviceType.EltakoFAM14:
            LOGGER.debug("[Gateway] [Id: %d] Try to read memory of all bus devices", self.dev_id)
            
            self._reading_memory_of_devices_is_running.set()
            is_locked = False
            try:
                self._bus.set_callback( None )

                is_locked = (await locking.lock_bus(self._bus)) == locking.LOCKED
                
                self._callback_receive_message_from_serial_bus( self.create_base_id_infO_message() )

                # iterate through devices
                for id in range(1, 256):
                    # exit if gateway is about to be deleted
                    if not self._reading_memory_of_devices_is_running.is_set():
                        return
                    
                    try:
                        dev_response:EltakoDiscoveryReply = await self._bus.exchange(EltakoDiscoveryRequest(address=id), EltakoDiscoveryReply, retries=3)
                        if dev_response == None:
                            break

                        assert id == dev_response.reported_address, "Queried for ID %s, received %s" % (id, prettify(dev_response))

                        self._callback_receive_message_from_serial_bus(EltakoDiscoveryReply.parse(dev_response.body))

                        device_name = ""
                        for o in sorted_known_objects:
                            if dev_response.model[0:2] in o.discovery_names:
                                device_name = o.__name__

                        LOGGER.debug("[Gateway] [Id: %d] Read memory from %s", )
                        # iterate through memory lines
                        for line in range(1, dev_response.memory_size):
                            # exit if gateway is about to be deleted
                            if not self._reading_memory_of_devices_is_running.is_set():
                                return
                                
                            try:                             
                                LOGGER.debug("[Gateway] [Id: %d] Read memory line %d", self.dev_id, line)
                                mem_response:EltakoMemoryResponse = await self._bus.exchange(EltakoMemoryRequest(dev_response.reported_address, line), EltakoMemoryResponse, retries=3)
                                self._callback_receive_message_from_serial_bus(mem_response)
                            except TimeoutError:
                                continue
                            except Exception as e:
                                LOGGER.error("[Gateway] [Id: %d] Cannot read memory line %d from device (id=%d)", self.dev_id, line, id)

                    except TimeoutError:
                        continue
                    except Exception as e:
                        LOGGER.exception("[Gateway] [Id: %d] Cannot detect device with address {i}", self.dev_id, id)

            except Exception as e:
                LOGGER.exception("[Gateway] [Id: %d] Failed to load base_id from FAM14.", self.dev_id)
                raise e
            finally:
                if is_locked:
                    resp = await locking.unlock_bus(self._bus)
                self._reading_memory_of_devices_is_running.clear()
                self._bus.set_callback( self._callback_receive_message_from_serial_bus ) 
        else:
            LOGGER.error(f"Cannot read memory of FAM14 beceuase this is a different gateway ({self.dev_type})")




    def reconnect(self):
        self._bus.stop()
        self._init_bus()
        self._bus.start()


    async def async_setup(self):
        """Initialized serial bus and register callback function on HA event bus."""
        self._bus.start()

        LOGGER.debug("[Gateway] [Id: %d] Was started.", self.dev_id)

        # receive messages from HA event bus
        event_id = config_helpers.get_bus_event_type(self.dev_id, SIGNAL_SEND_MESSAGE)
        LOGGER.debug("[Gateway] [Id: %d] Register gateway bus for message event_id %s", event_id)
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, event_id, self._callback_send_message_to_serial_bus
        )

        # Register home assistant service for sending arbitrary telegrams.
        #
        # The service will be registered for each gateway, as the user
        # might have different gateways that cause the eltako relays
        # only to react on them.
        service_name = config_helpers.get_bus_event_type(self.dev_id, SIGNAL_SEND_MESSAGE_SERVICE)
        LOGGER.debug("[Gateway] [Id: %d] Register send message service event_id %s", event_id)
        self.hass.services.async_register(DOMAIN, service_name, self.async_service_send_message)


    # Command Section
    async def async_service_send_message(self, event, raise_exception=False) -> None:
        """Send an arbitrary message with the provided eep."""
        LOGGER.debug(f"[Service Send Message: {event.service}] Received event data: {event.data}")
        
        try:
            sender_id_str = event.data.get("id", None)
            sender_id:AddressExpression = AddressExpression.parse(sender_id_str)
        except:
            LOGGER.error(f"[Service Send Message: {event.service}] No valid sender id defined. (Given sender id: {sender_id_str})")
            return

        try:
            sender_eep_str = event.data.get("eep", None)
            sender_eep:EEP = EEP.find(sender_eep_str)
        except:
            LOGGER.error(f"[Service Send Message: {event.service}] No valid sender id defined. (Given sender id: {sender_id_str})")
            return
        
        # prepare all arguements for eep constructor
        import inspect
        sig = inspect.signature(sender_eep.__init__)
        eep_init_args = [param.name for param in sig.parameters.values() if param.kind == param.POSITIONAL_OR_KEYWORD]
        knargs = {filter_key:event.data[filter_key] for filter_key in eep_init_args if filter_key in event.data and filter_key != 'self'}
        LOGGER.debug(f"[Service Send Message: {event.service}] Provided EEP ({sender_eep.__name__}) args: {knargs})")
        uknargs = {filter_key:0 for filter_key in eep_init_args if filter_key not in event.data and filter_key != 'self'}
        LOGGER.debug(f"[Service Send Message: {event.service}] Missing EEP ({sender_eep.__name__}) args: {uknargs})")
        eep_args = knargs
        eep_args.update(uknargs)
            
        eep:EEP = sender_eep(**eep_args)

        try:
            # create message
            msg = eep.encode_message(sender_id[0])
            LOGGER.debug(f"[Service Send Message: {event.service}] Generated message: {msg} Serialized: {msg.serialize().hex()}")
            # send message
            self.send_message(msg)
        except Exception as e:
            LOGGER.error(f"[Service Send Message: {event.service}] Cannot send message.", exc_info=True, stack_info=True)
            if raise_exception:
                raise e



    def send_message(self, msg: ESP2Message):
        """Put message on RS485 bus. First the message is put onto HA event bus so that other automations can react on messages."""
        event_id = config_helpers.get_bus_event_type(self.dev_id, SIGNAL_SEND_MESSAGE)
        dispatcher_send(self.hass, event_id, msg)
        dispatcher_send(self.hass, GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': msg})


    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self._reading_memory_of_devices_is_running.clear()
            self._bus.stop()
            self._bus.join()
            LOGGER.debug("[Gateway] [Id: %d] Was stopped.", self.dev_id)
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None


    def _callback_send_message_to_serial_bus(self, msg):
        """Callback method call from HA when receiving events from serial bus."""
        if self._bus.is_active():
            if isinstance(msg, ESP2Message):
                LOGGER.debug("[Gateway] [Id: %d] Send message: %s - Serialized: %s", self.dev_id, msg, msg.serialize().hex())

                # put message on serial bus
                self.hass.create_task(
                    self._bus.send(msg)
                )
                dispatcher_send(self.hass, GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': msg})
        else:
            LOGGER.warning("[Gateway] [Id: %d] Serial port %s is not available!!! message (%s) was not sent.", self.dev_id, self.serial_path, msg)


    def _callback_receive_message_from_serial_bus(self, message:ESP2Message):
        """Handle Eltako device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming message.
        """

        if type(message) not in [EltakoPoll]:
            LOGGER.debug("[Gateway] [Id: %d] Received message: %s", self.dev_id, message)
            self.report_message_stats()

            if message.body[:2] == b'\x8b\x98':
                LOGGER.debug("[Gateway] [Id: %d] Received base id: %s", self.dev_id, b2s(message.body[2:6]))
                self._attr_base_id = AddressExpression( (message.body[2:6], None) )
                self._fire_base_id_change_handlers(self.base_id)


            # only send messages to HA when base id is known
            if int.from_bytes(self.base_id[0]) != 0:

                # Send message on local bus. Only devices configure to this gateway will receive those message.
                event_id = config_helpers.get_bus_event_type(self.dev_id, SIGNAL_RECEIVE_MESSAGE)
                dispatcher_send(self.hass, event_id, message)

                if type(message) not in [EltakoDiscoveryRequest]:
                    # Send message on global bus with external/outside address
                    global_msg = prettify(message)
                    # do not change discovery and memory message addresses, base id will be sent upfront so that the receive known to whom the message belong
                    if type(message) in [EltakoWrappedRPS, EltakoWrapped4BS, RPSMessage, Regular1BSMessage, Regular4BSMessage, EltakoMessage]:
                        address = message.body[6:10]
                        if address[0:2] == b'\x00\x00':
                            g_address = (int.from_bytes(address, 'big') + int.from_bytes(self.base_id[0], 'big')).to_bytes(4, byteorder='big')
                            global_msg = prettify(ESP2Message( message.body[:8] + g_address + message.body[12:] ))


                    LOGGER.debug("[Gateway] [Id: %d] Forwared message (%s) in global bus", self.dev_id, global_msg)
                    dispatcher_send(self.hass, GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': global_msg})
            
            
    def create_base_id_infO_message(gw):
        gw_type_id:int = GatewayDeviceType.indexOf(gw.dev_type) + 1
        data:bytes = b'\x8b\x98' + gw.base_id[0] + gw_type_id.to_bytes(1, 'big') + b'\x00\x00\x00\x00'
        return ESP2Message(bytes(data))


    @property
    def unique_id(self) -> str:
        """Return the unique id of the gateway."""
        return self.serial_path
    

    @property
    def serial_path(self) -> str:
        """Return the serial path of the gateway."""
        return self._attr_serial_path
    

    @property
    def dev_name(self) -> str:
        """Return the device name of the gateway."""
        return self._attr_dev_name
    

    @property
    def dev_id(self) -> int:
        """Return the device id of the gateway."""
        return self._attr_dev_id
    
    @property
    def dev_type(self) -> GatewayDeviceType:
        """Return the device type of the gateway."""
        return self._attr_dev_type
    

    @property
    def base_id(self) -> AddressExpression:
        """Return the base id of the gateway."""
        return self._attr_base_id
    

    @property
    def model(self) -> str:
        """Return the model of the gateway."""
        return self._attr_model
    

    @property
    def identifier(self) -> str:
        """Return the identifier of the gateway."""
        return self._attr_identifier
    
    @property
    def message_delay(self) -> str:
        """Return the message delay of single telegrams to be sent."""
        return str(self._message_delay)
    
    @property
    def is_auto_reconnect_enabled(self) -> str:
        """Return if auto connected is enabled."""
        return str(self._auto_reconnect)


def detect() -> list[str]:
    """Return a list of candidate paths for USB Eltako gateways.

    This method is currently a bit simplistic, it may need to be
    improved to support more configurations and OS.
    """
    globs_to_test = ["/dev/serial/by-id/*", "/dev/serial/by-path/*"]
    found_paths = []
    for current_glob in globs_to_test:
        found_paths.extend(glob.glob(current_glob))

    return found_paths


def validate_path(path: str, baud_rate: int):
    """Return True if the provided path points to a valid serial port, False otherwise."""
    try:
        serial.serial_for_url(path, baud_rate, timeout=0.1)
        return True
    except serial.SerialException as exception:
        LOGGER.warning("Gateway path %s is invalid: %s", path, str(exception))
        return False
