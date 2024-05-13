"""Representation of an Eltako gateway."""
from enum import Enum
import glob

from os.path import basename, normpath
import pytz
from datetime import datetime

import serial
import asyncio

from eltakobus.serial import RS485SerialInterface, RS485SerialInterfaceV2, BusInterface
from eltakobus.message import ESP2Message, RPSMessage, Regular1BSMessage, Regular4BSMessage, EltakoPoll, prettify

from eltakobus.util import AddressExpression
from eltakobus.eep import EEP

from enocean.communicators import SerialCommunicator
from enocean.protocol.packet import RadioPacket, RORG, Packet

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceRegistry, DeviceInfo
from homeassistant.config_entries import ConfigEntry

from .const import *
from . import config_helpers
from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator


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
                 dev_id: int, dev_type: GatewayDeviceType, serial_path: str, baud_rate: int, base_id: AddressExpression, dev_name: str, 
                 config_entry: ConfigEntry):
        """Initialize the Eltako gateway."""

        self._loop = asyncio.get_event_loop()
        self._bus_task = None
        self.baud_rate = baud_rate
        self._attr_dev_type = dev_type
        self._attr_serial_path = serial_path
        self._attr_identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None
        self.general_settings = general_settings
        self._attr_dev_id = dev_id
        self._attr_base_id = base_id
        self.config_entry_id = config_entry.entry_id

        self._last_message_received_handler = None
        self._connection_state_handler = None
        self._received_message_count_handler = None

        self._attr_model = GATEWAY_DEFAULT_NAME + " - " + self.dev_type.upper()

        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self.native_protocol = 'ESP2'
        else:
            self.native_protocol = 'ESP3'
        self._attr_dev_name = config_helpers.get_gateway_name(dev_name, dev_type.value, dev_id, base_id)

        self._init_bus()

        self._register_device()


    def set_connection_state_changed_handler(self, handler):
        self._connection_state_handler = handler
        self._fire_connection_state_changed_event(self._bus and self._bus.is_active())


    def _fire_connection_state_changed_event(self, connected:bool):
        if self._connection_state_handler:
            self.hass.async_create_task(
                self._connection_state_handler( connected )
            )


    def set_last_message_received_handler(self, handler):
        self._last_message_received_handler = handler


    def _fire_last_message_received_event(self):
        if self._last_message_received_handler:
            self.hass.async_create_task(
                self._last_message_received_handler( datetime.utcnow().replace(tzinfo=pytz.utc) )
            )


    def set_received_message_count_handler(self, handler):
        self._received_message_count_handler = handler


    def _fire_received_message_count_event(self):
        self._received_message_count += 1
        if self._received_message_count_handler:
            self.hass.async_create_task(
                self._received_message_count_handler( self._received_message_count )
            )

    def process_messages(self, data):
        LOGGER.info("GATEWAY: HANDLE MESSAGES")


    def _init_bus(self):
        self._received_message_count = 0
        # self._fire_received_message_count_event()
        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self._bus = RS485SerialInterfaceV2(self.serial_path, baud_rate=self.baud_rate, callback=self._callback_receive_message_from_serial_bus)
        else:
            self._bus = ESP3SerialCommunicator(filename=self.serial_path, callback=self._callback_receive_message_from_serial_bus, esp2_translation_enabled=True)

        # self._bus.set_status_changed_handler(self._fire_connection_state_changed_event)


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
            LOGGER.warn(f"{device_name} ({sender_id}): Maybe have wrong sender id configured!")
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
            LOGGER.warn(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
        return result
    

    def dev_id_validation_by_bus_gateway(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = config_helpers.compare_enocean_ids(b'\x00\x00\x00\x00', dev_id[0], len=2)
        if not result:
            LOGGER.warn(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
        return result
    

    ### send and receive funtions for RS485 bus (serial bus)
    ### all events are looped through the HA event bus so that other automations can work with those events. History about events can aslo be created.

    def reconnect(self):
        self._bus.stop()
        self._init_bus()
        self._bus.start()


    async def async_setup(self):
        """Initialized serial bus and register callback function on HA event bus."""
        self._bus.start()
        LOGGER.debug("[Gateway] [Id: %d] Was started.", self.dev_id)

        # receive messages from HA event bus
        event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_SEND_MESSAGE)
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, event_id, self._callback_send_message_to_serial_bus
        )

        event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_RECEIVE_MESSAGE)
        async_dispatcher_connect(self.hass, event_id, self.process_messages)

        # Register home assistant service for sending arbitrary telegrams.
        #
        # The service will be registered for each gateway, as the user
        # might have different gateways that cause the eltako relays
        # only to react on them.
        service_name = f"gateway_{self._attr_dev_id}_send_message"
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
        event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_SEND_MESSAGE)
        dispatcher_send(self.hass, event_id, msg)


    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
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
                asyncio.ensure_future(self._bus.send(msg), loop=self._loop)
        else:
            LOGGER.warn("[Gateway] [Id: %d] Serial port %s is not available!!! message (%s) was not sent.", self.dev_id, self.serial_path, msg)


    def _callback_receive_message_from_serial_bus(self, message):
        """Handle Eltako device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming message.
        """

        if type(message) not in [EltakoPoll]:
            LOGGER.debug("[Gateway] [Id: %d] Received message: %s", self.dev_id, message)
            # self._fire_last_message_received_event()
            # self._fire_received_message_count_event()
            if isinstance(message, ESP2Message):
                event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_RECEIVE_MESSAGE)
                dispatcher_send(self.hass, event_id, message)
            
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
