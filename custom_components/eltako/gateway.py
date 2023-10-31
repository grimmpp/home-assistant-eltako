"""Representation of an Eltako gateway."""
import glob
import asyncio
import logging
from os.path import basename, normpath

from eltakobus.serial import RS485SerialInterface
from eltakobus.message import ESP2Message
import serial

from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr

from .const import SIGNAL_RECEIVE_MESSAGE, SIGNAL_SEND_MESSAGE, LOGGER, MANUFACTURER, DOMAIN

DEFAULT_NAME = "Eltako gateway"


class EltakoGateway:
    """Representation of an Eltako gateway.

    The gateway is responsible for receiving the Eltako frames,
    creating devices if needed, and dispatching messages to platforms.
    """

    RECONNECT_TIMEOUT = 10 # sec

    def __init__(self, hass, serial_path, config_entry):
        """Initialize the Eltako gateway."""

        self._loop = asyncio.get_event_loop()
        self._bus_task = None
        self._bus = RS485SerialInterface(serial_path)
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
        def bus_done(bus_future, _task=self._main_task, serial_path=self.serial_path):
            self._bus_task = None
            try:
                LOGGER.info(f"Connect Eltako serial bus to {serial_path}")
                result = bus_future.result()
            except Exception as e:
                LOGGER.error("Bus task terminated with %s, removing main task", bus_future.exception())
                LOGGER.exception(e)
            else:
                LOGGER.error("Bus task terminated with %s (it should have raised an exception instead), removing main task", result)
            
            # LOGGER.info(f"Wait {self.RECONNECT_TIMEOUT} until reconnect ...")
            # await asyncio.sleep(self.RECONNECT_TIMEOUT)
            # _task.cancel()
            if self._bus_task is not None:
                self._bus_task.cancel()

        self._bus_task.add_done_callback(bus_done)
        await conn_made
    
    async def _wrapped_main(self, *args):
        try:
            await self._main(*args)
        except Exception as e:
            LOGGER.Info("Test 123 ###########################################")
            LOGGER.exception(e)
            # FIXME should I just restart with back-off?

        if self._bus_task is not None:
            self._bus_task.cancel()

    async def _main(self):
        bus = self._bus
        while True:
            try:
                if self._bus_task is None:
                    await self._initialize_bus_task(bus.run)
            
                while True:
                    await self._step(bus)

            except asyncio.TimeoutError:
                LOGGER.info(f"Wait {self.RECONNECT_TIMEOUT} until reconnect ...")
                await asyncio.sleep(self.RECONNECT_TIMEOUT)
                self._bus_task = None
            except Exception as e:
                LOGGER.exception(e)
                

    async def _step(self, bus):
        # message = await bus.received.get()
        message = await asyncio.wait_for(bus.received.get, self.RECONNECT_TIMEOUT) # 10 sec
        self._callback(message)
        # try:
        #     message = await asyncio.wait_for(bus.received.get, self.RECONNECT_TIMEOUT) # 10 sec
        #     self._callback(message)
        # except asyncio.TimeoutError:
        #     LOGGER.info(f"Didn't receive a message since {self.RECONNECT_TIMEOUT} seconds. Try to reconnect.")
        #     self._initialize_bus_task()

    def _callback(self, message):
        """Handle Eltako device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming message.
        """

        if isinstance(message, ESP2Message):
            LOGGER.debug("Received message: %s", message)
            dispatcher_send(self.hass, SIGNAL_RECEIVE_MESSAGE, message)
            
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
