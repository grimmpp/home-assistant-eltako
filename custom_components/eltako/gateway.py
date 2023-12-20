"""Representation of an Eltako gateway."""
from enum import Enum
import glob

from os.path import basename, normpath

import serial
import asyncio

from eltakobus.serial import RS485SerialInterface
from eltakobus.message import ESP2Message

from eltakobus.util import AddressExpression

from enocean.communicators import SerialCommunicator
from enocean.protocol.packet import RadioPacket

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICE, CONF_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.config_entries import ConfigEntry

from .const import *
from . import config_helpers

class GatewayDeviceType(str, Enum):
    GatewayEltakoFAM14 = 'fam14'
    GatewayEltakoFGW14USB = 'fgw14usb'
    GatewayEltakoFAMUSB = 'fam-usb'     # ESP2 transceiver: https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/
    EnOceanUSB300 = 'enocean-usb300'    # not yet supported

    @classmethod
    def find(cls, value):
        for t in GatewayDeviceType:
            if t.value.lower() == value.lower():
                return t
        return None

    @classmethod
    def is_transceiver(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAMUSB, GatewayDeviceType.EnOceanUSB300]

    @classmethod
    def is_bus_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB]
    
    @classmethod
    def is_esp2_gateway(cls, dev_type) -> bool:
        return dev_type in [GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFGW14USB, GatewayDeviceType.GatewayEltakoFAMUSB]

BAUD_RATE_DEVICE_TYPE_MAPPING: dict = {
    GatewayDeviceType.GatewayEltakoFAM14: 57600,
    GatewayDeviceType.GatewayEltakoFGW14USB: 57600,
    GatewayDeviceType.GatewayEltakoFAMUSB: 9600,
    GatewayDeviceType.EnOceanUSB300: 57600,
}

def convert_esp2_to_esp3_message(message: ESP2Message) -> RadioPacket:
    #TODO: implement converter
    raise Exception("Message conversion from ESP2 to ESP3 NOT YET IMPLEMENTED.")

def convert_esp3_to_esp2_message(packet: RadioPacket) -> ESP2Message:
    #TODO: implement converter
    raise Exception("Message conversion from ESP3 to ESP2 NOT YET IMPLEMENTED.")

async def async_get_base_ids_of_registered_gateway(device_registry: DeviceRegistry) -> [str]:
    base_id_list = []
    for d in device_registry.devices.values():
        if d.model and d.model.startswith(GATEWAY_DEFAULT_NAME):
            base_id_list.append( list(d.connections)[0][1] )
    return base_id_list

async def async_get_serial_path_of_registered_gateway(device_registry: DeviceRegistry) -> [str]:
    serial_path_list = []
    for d in device_registry.devices.values():
        if d.model and d.model.startswith(GATEWAY_DEFAULT_NAME):
            serial_path_list.append( list(d.identifiers)[0][1] )
    return serial_path_list

class ESP2Gateway:
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
        self._bus = RS485SerialInterface(serial_path, baud_rate=baud_rate)
        self._attr_serial_path = serial_path
        self._attr_identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None
        self.general_settings = general_settings
        self._attr_dev_id = dev_id
        self._attr_base_id = base_id
        self._attr_dev_type = dev_type

        self._attr_model = GATEWAY_DEFAULT_NAME + " - " + self.dev_type.upper()

        self._attr_dev_name = config_helpers.get_gateway_name(dev_name, dev_type.value, dev_id, base_id)

        self._register_device(hass, config_entry.entry_id)

    def _register_device(self, hass, entry_id) -> None:
        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry_id,
            identifiers={(DOMAIN, self.serial_path)},
            connections={(CONF_MAC, config_helpers.format_address(self.base_id))},
            manufacturer=MANUFACTURER,
            name= self.dev_name,
            model=self.model,
        )

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
    

    async def async_setup(self):
        """Finish the setup of the bridge and supported platforms."""
        self._main_task = asyncio.ensure_future(self._wrapped_main(), loop=self._loop)
        
        event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_SEND_MESSAGE)
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, event_id, self._send_message_callback
        )

    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

    def _send_message_callback(self, msg):
        """Send a request through the Eltako gateway."""
        if isinstance(msg, ESP2Message):
            LOGGER.debug("[Gateway] [Id: %d] Send message: %s - Serialized: %s", self.dev_id, msg, msg.serialize().hex())
            asyncio.ensure_future(self._bus.send(msg), loop=self._loop)

    async def _initialize_bus_task(self, run):
        """Call bus.run in a task that takes down main if it crashes, and is
        properly shut down as well"""
        if self._bus_task is not None:
            self._bus_task.cancel()

        conn_made = asyncio.Future()
        self._bus_task = asyncio.ensure_future(run(self._loop, conn_made=conn_made))
        def bus_done(bus_future, _task=self._main_task):
            self._bus_task = None
            try:
                result = bus_future.result()
            except Exception as e:
                LOGGER.error("Bus task terminated with %s, removing main task", bus_future.exception())
                LOGGER.exception(e)
            else:
                LOGGER.error("Bus task terminated with %s (it should have raised an exception instead), removing main task", result)
            _task.cancel()
        self._bus_task.add_done_callback(bus_done)
        await conn_made
    
    async def _wrapped_main(self, *args):
        try:
            await self._main(*args)
        except Exception as e:
            LOGGER.exception(e)
            # FIXME should I just restart with back-off?

        if self._bus_task is not None:
            self._bus_task.cancel()

    async def _main(self):
        bus = self._bus
        await self._initialize_bus_task(bus.run)

        while True:
            await self._step(bus)

    async def _step(self, bus):
        message = await bus.received.get()
        self._callback(message)

    def _callback(self, message):
        """Handle Eltako device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming message.
        """

        LOGGER.debug("[Gateway] [Id: %d] Received message: %s", self.dev_id, message)
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
    

# class EltakoGatewayFam14 (EltakoGateway):
#     """Gateway class for Eltako FAM14."""

#     def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
#         return True # because no sender telegram is leaving the bus into wireless, only status update of the actuators and those ids are bease on the baseId.
    
#     def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
#         result = config_helpers.compare_enocean_ids(b'\x00\x00\x00\x00', dev_id[0], len=2)
#         if not result:
#             LOGGER.warn(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
#         return result

# class EltakoGatewayFgw14Usb (EltakoGatewayFam14):
#     """Gateway class for Eltako FGW14-USB."""

# class EltakoGatewayFamUsb (EltakoGateway, Entity):
#     """Gateway class for Eltako FAM-USB."""

#     def __init__(self, general_settings:dict, hass: HomeAssistant, dev_type: GatewayDeviceType, serial_path: str, baud_rate: int, base_id: AddressExpression, dev_name: str, config_entry):
#         super(EltakoGatewayFamUsb, self).__init__(general_settings, hass, dev_type, serial_path, baud_rate, base_id, dev_name, config_entry)

#     #     self.async_on_remove(
#     #         async_dispatcher_connect(
#     #             self.hass, SIGNAL_RECEIVE_MESSAGE, self._message_received_callback
#     #         )
#     #     )

#     #     # read base id from device
#     #     msg = ESP2Message(b'\xA5\x5A\xAB\x58\x00\x00\x00\x00\x00\x00\x00\x00\x00')
#     #     dispatcher_send(self.hass, SIGNAL_SEND_MESSAGE, msg)

#     # def _message_received_callback(self, msg: ESP2Message) -> None:
#     #     # receive base id and compare with base id in configuration
#     #     if msg.address == b'\x00\x00\x00\x00' and msg.body[0] == 0x8B and msg.body[1] == 0x98:
#     #         device_base_id = msg.body[2:5]
#     #         if not compare_enocean_ids(self.base_id, device_base_id, len=4):
#     #             raise Exception(f"Configured baseId {self.base_id} does not match device baseId {device_base_id}")
#     #         else:
#     #             LOGGER.debug(f"Received baseId form device {device_base_id} and compared with configuration.")
        

#     def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
#         result = config_helpers.compare_enocean_ids(self.base_id[0], sender_id[0])
#         if not result:
#             LOGGER.warn(f"{device_name} ({sender_id}): Maybe have wrong sender id configured!")
#         return result

    
#     def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
#         result = 0xFF == dev_id[0][0]
#         if not result:
#             LOGGER.warn(f"{device_name} ({dev_id}): Maybe have wrong device id configured!")
#         return result
    
    

class ESP3Gateway:
    """Representation of Enocean USB300 transmitter.

    The dongle is responsible for receiving the ENOcean frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    def __init__(self, general_settings:dict, hass: HomeAssistant, dev_type: GatewayDeviceType, serial_path: str, baud_rate: int, base_id: AddressExpression, dev_name: str, config_entry):
        """Initialize the EnOcean dongle."""

        self._communicator = SerialCommunicator(
            port=serial_path, callback=self.callback
        )
        self.serial_path = serial_path
        self.identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None
        self.general_settings = general_settings
        self.base_id = base_id
        self.dev_type = dev_type
        
        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=MANUFACTURER,
            name=GATEWAY_DEFAULT_NAME,
        )

    async def async_setup(self):
        """Finish the setup of the bridge and supported platforms."""
        self._communicator.start()
        event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_SEND_MESSAGE)
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, event_id, self._send_message_callback
        )

    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

    def _send_message_callback(self, eltako_command):
        """Send a command through the EnOcean dongle."""
        enocean_command = convert_esp2_to_esp3_message(eltako_command)
        if enocean_command is not None:
            self._communicator.send(enocean_command)

    def callback(self, packet):
        """Handle EnOcean device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming packet.
        """

        if isinstance(packet, RadioPacket):
            LOGGER.debug("Received radio packet: %s", packet)
            eltako_message = convert_esp3_to_esp2_message(packet)
            if eltako_message is not None:
                event_id = config_helpers.get_bus_event_type(self.base_id, SIGNAL_RECEIVE_MESSAGE)
                dispatcher_send(self.hass, event_id, eltako_message)
            
    @property
    def unique_id(self):
        """Return the unique id of the gateway."""
        return self.serial_path


def detect() -> [str]:
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
