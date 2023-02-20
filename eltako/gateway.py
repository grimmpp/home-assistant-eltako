"""Representation of an Eltako gateway."""
import glob
import asyncio
import logging
from os.path import basename, normpath

from eltakobus.serial import RS485SerialInterface
from eltakobus.message import ESP2Message
import serial

from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send

from .const import SIGNAL_RECEIVE_MESSAGE, SIGNAL_SEND_MESSAGE

_LOGGER = logging.getLogger(__name__)


class EltakoGateway:
    """Representation of an Eltako gateway.

    The gateway is responsible for receiving the Eltako frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    def __init__(self, hass, serial_path):
        """Initialize the Eltako gateway."""

        self._loop = asyncio.get_event_loop()
        self._bus_task = None
        self._bus = RS485SerialInterface(serial_path)
        self.serial_path = serial_path
        self.identifier = basename(normpath(serial_path))
        self.hass = hass
        self.dispatcher_disconnect_handle = None

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

    def _send_message_callback(self, request):
        """Send a request through the Eltako gateway."""
        self._bus.send(request)

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
                _LOGGER.error("Bus task terminated with %s, removing main task", bus_future.exception())
                _LOGGER.exception(e)
            else:
                _LOGGER.error("Bus task terminated with %s (it should have raised an exception instead), removing main task", result)
            _task.cancel()
        self._bus_task.add_done_callback(bus_done)
        await conn_made
    
    async def _wrapped_main(self, *args):
        try:
            await self._main(*args)
        except Exception as e:
            _LOGGER.exception(e)
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

        if isinstance(message, ESP2Message):
            _LOGGER.debug("Received message: %s", message)
            dispatcher_send(self.hass, SIGNAL_RECEIVE_MESSAGE, message)


def detect():
    """Return a list of candidate paths for USB Eltako gateways.

    This method is currently a bit simplistic, it may need to be
    improved to support more configurations and OS.
    """
    # TODO: Find a better way
    globs_to_test = ["/dev/tty*Eltako*", "/dev/serial/by-id/*Eltako*"]
    found_paths = []
    for current_glob in globs_to_test:
        found_paths.extend(glob.glob(current_glob))

    return found_paths


def validate_path(path: str):
    """Return True if the provided path points to a valid serial port, False otherwise."""
    try:
        # Creating the serial communicator will raise an exception
        # if it cannot connect
        # TODO: Implement check
        #SerialCommunicator(port=path)
        return True
    except serial.SerialException as exception:
        _LOGGER.warning("Gateway path %s is invalid: %s", path, str(exception))
        return False
