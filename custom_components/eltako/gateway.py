"""Representation of an Eltako gateway."""
from enum import Enum
import glob

from os.path import basename, normpath

import serial
import asyncio

from eltakobus.serial import RS485SerialInterface
from eltakobus.message import ESP2Message
from eltakobus.error import ParseError

from eltakobus.util import AddressExpression, b2a
from eltakobus.message import  Regular4BSMessage

from enocean.communicators import SerialCommunicator
from enocean.protocol.packet import RadioPacket, PARSE_RESULT

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_DEVICE, CONF_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import Entity

from .const import *
from .config_helpers import *

DEFAULT_NAME = "Eltako Gateway"

class GatewayDeviceTypes(str, Enum):
    GatewayEltakoFAM14 = 'fam14'
    GatewayEltakoFGW14USB = 'fgw14usb'
    GatewayEltakoFAMUSB = 'fam-usb'     # ESP2 transceiver: https://www.eltako.com/en/product/professional-standard-en/three-phase-energy-meters-and-one-phase-energy-meters/fam-usb/
    EnOceanUSB300 = 'enocean-usb300'    # not yet supported


def convert_esp2_to_esp3_message(message: ESP2Message) -> RadioPacket:
    #TODO: implement converter
    raise Exception("Message conversion from ESP2 to ESP3 NOT YET IMPLEMENTED.")

def convert_esp3_to_esp2_message(packet: RadioPacket) -> ESP2Message:
    #TODO: implement converter
    raise Exception("Message conversion from ESP3 to ESP2 NOT YET IMPLEMENTED.")


class EltakoGateway:
    """Representation of an Eltako gateway.

    The gateway is responsible for receiving the Eltako frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    def __init__(self, general_settings:dict, hass: HomeAssistant, serial_path: str, baud_rate: int, base_id: AddressExpression, dev_name: str, config_entry):
        """Initialize the Eltako gateway."""

        self._loop = asyncio.get_event_loop()
        self._bus_task = None
        self._bus = RS485SerialInterface(serial_path, baud_rate=baud_rate)
        self.serial_path = serial_path
        self.identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None
        self.general_settings = general_settings
        self.base_id = base_id
        self.base_id_str = f"{b2a(self.base_id[0], '-').upper()}"

        if isinstance(self, EltakoGatewayFam14):
            self.model = "Eltako Gateway - FAM14"
        elif isinstance(self, EltakoGatewayFgw14Usb):
            self.model = "Eltako Gateway - FGW14-USB"
        elif isinstance(self, EltakoGatewayFamUsb):
            self.model = "Eltako Gateway - FAM-USB"
        else:
            self.model = "Eltako Gateway"

        if not dev_name and len(dev_name) == 0:
            self.dev_name = self.model
        
        self.dev_name = get_device_name(dev_name, base_id, self.general_settings)

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, self.unique_id)},
            connections={(CONF_MAC, self.base_id_str)},
            manufacturer=MANUFACTURER,
            name= self.dev_name,
            model=self.model,
        )

    def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        return False
    
    def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        return False

    async def async_setup(self):
        """Finish the setup of the bridge and supported platforms."""
        self._main_task = asyncio.ensure_future(self._wrapped_main(), loop=self._loop)
        
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, SIGNAL_SEND_MESSAGE, self._send_message_callback
        )

    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

    def _send_message_callback(self, msg):
        """Send a request through the Eltako gateway."""
        if isinstance(msg, ESP2Message):
            LOGGER.debug("Send message: %s - Serialized: %s", msg, msg.serialize().hex())
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

        LOGGER.debug("Received message: %s", message)
        if isinstance(message, ESP2Message):
            dispatcher_send(self.hass, SIGNAL_RECEIVE_MESSAGE, message)
            
    @property
    def unique_id(self):
        """Return the unique id of the gateway."""
        return self.serial_path
    

class EltakoGatewayFam14 (EltakoGateway):
    """Gateway class for Eltako FAM14."""

    def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        return True # because no sender telegram is leaving the bus into wireless, only status update of the actuators and those ids are bease on the baseId.
    
    def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = compare_enocean_ids(b'\x00\x00\x00\x00', dev_id[0])
        if not result:
            LOGGER.error(f"Wrong id ({dev_id}) configured for device {device_name}")
        return result

class EltakoGatewayFgw14Usb (EltakoGatewayFam14):
    """Gateway class for Eltako FGW14-USB."""

class EltakoGatewayFamUsb (EltakoGateway, Entity):
    """Gateway class for Eltako FAM-USB."""

    def __init__(self, general_settings:dict, hass: HomeAssistant, serial_path: str, baud_rate: int, base_id: AddressExpression, dev_name: str, config_entry):
        super(EltakoGatewayFamUsb, self).__init__(general_settings, hass, serial_path, baud_rate, base_id, dev_name, config_entry)

    #     self.async_on_remove(
    #         async_dispatcher_connect(
    #             self.hass, SIGNAL_RECEIVE_MESSAGE, self._message_received_callback
    #         )
    #     )

    #     # read base id from device
    #     msg = ESP2Message(b'\xA5\x5A\xAB\x58\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    #     dispatcher_send(self.hass, SIGNAL_SEND_MESSAGE, msg)

    # def _message_received_callback(self, msg: ESP2Message) -> None:
    #     # receive base id and compare with base id in configuration
    #     if msg.address == b'\x00\x00\x00\x00' and msg.body[0] == 0x8B and msg.body[1] == 0x98:
    #         device_base_id = msg.body[2:5]
    #         if not compare_enocean_ids(self.base_id, device_base_id, len=4):
    #             raise Exception(f"Configured baseId {self.base_id} does not match device baseId {device_base_id}")
    #         else:
    #             LOGGER.debug(f"Received baseId form device {device_base_id} and compared with configuration.")
        

    def validate_sender_id(self, sender_id: AddressExpression, device_name: str = "") -> bool:
        result = compare_enocean_ids(self.base_id[0], sender_id[0])
        if not result:
            LOGGER.error(f"Wrong sender id ({sender_id}) configured for device {device_name}")
        return result

    
    def validate_dev_id(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = 0xFF == dev_id[0][0] and 0x80 <= dev_id[0][1]
        if not result:
            LOGGER.error(f"Wrong id ({dev_id}) configured for device {device_name}")
        return result
    
    

class EnoceanUSB300Gateway:
    """Representation of Enocean USB300 transmitter.

    The dongle is responsible for receiving the ENOcean frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    def __init__(self, hass, serial_path, config_entry):
        """Initialize the EnOcean dongle."""

        self._communicator = SerialCommunicator(
            port=serial_path, callback=self.callback
        )
        self.serial_path = serial_path
        self.identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None
        
        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
        )

    async def async_setup(self):
        """Finish the setup of the bridge and supported platforms."""
        self._communicator.start()
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, SIGNAL_SEND_MESSAGE, self._send_message_callback
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
                dispatcher_send(self.hass, SIGNAL_RECEIVE_MESSAGE, eltako_message)
            
    @property
    def unique_id(self):
        """Return the unique id of the gateway."""
        return self.serial_path


def detect():
    """Return a list of candidate paths for USB Eltako gateways.

    This method is currently a bit simplistic, it may need to be
    improved to support more configurations and OS.
    """
    globs_to_test = ["/dev/serial/by-id/*", "/dev/serial/by-path/*"]
    found_paths = []
    for current_glob in globs_to_test:
        found_paths.extend(glob.glob(current_glob))

    return found_paths


def validate_path(path: str):
    """Return True if the provided path points to a valid serial port, False otherwise."""
    try:
        serial.Serial(path, 57600, timeout=0.1)
        return True
    except serial.SerialException as exception:
        LOGGER.warning("Gateway path %s is invalid: %s", path, str(exception))
        return False
