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
from eltakobus.device import request_memory_of_all_devices
from eltakobus import locking

from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
from esp2_gateway_adapter.esp3_tcp_com import TCP2SerialCommunicator


def _attach_rssi_to_esp2_conversion():
    """Carry the signal strength of radio telegrams over the ESP3 -> ESP2 translation.

    ESP3 radio packets report the RSSI in their optional data (packet.dBm, negative
    dBm). The adapter drops it when it converts to ESP2 (the ESP2 frame has no place
    for it), so the converted message gets it attached as a plain attribute. The
    telegram logger picks it up from there. ESP2 gateways (FAM14, FGW14-USB) do not
    report a signal strength - nothing is attached for them.

    The adapter calls the classmethod via the class name, therefore subclassing is
    not enough - the classmethod itself is wrapped (once).
    """
    original = ESP3SerialCommunicator.convert_esp3_to_esp2_message.__func__

    def convert_with_rssi(cls, packet):
        esp2_msg = original(cls, packet)
        if esp2_msg is not None:
            dbm = getattr(packet, 'dBm', None)
            if isinstance(dbm, (int, float)) and dbm < 0:
                esp2_msg.dBm = int(dbm)
        return esp2_msg

    convert_with_rssi._adds_rssi = True
    ESP3SerialCommunicator.convert_esp3_to_esp2_message = classmethod(convert_with_rssi)


if not getattr(ESP3SerialCommunicator.convert_esp3_to_esp2_message.__func__, '_adds_rssi', False):
    _attach_rssi_to_esp2_conversion()

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_MAC
from homeassistant.helpers.dispatcher import async_dispatcher_connect, dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.config_entries import ConfigEntry

from ..const import *
from ..config import config_helpers
from ..observation.enocean_logger import POLLING_MESSAGE_TYPES, get_telegram_logger, resolve_addresses
from ..observation.bus_members import note_telegram
from ..observation.device_activity import get_activity_tracker

import threading
import time
from collections import deque
from contextlib import contextmanager


class BusBusyError(RuntimeError):
    """Another operation has the bus for itself right now."""


# How long a command waits for a busy bus before it is dropped. A bus scan takes minutes; a
# switch command which arrives that late is worse than none, so it expires (and says so).
BUS_DEFER_SECONDS = 20
# an upper bound for the queue, so a long scan cannot pile up telegrams without end
BUS_DEFERRED_LIMIT = 64

# The base id request of a FAM14 locks the bus and disables the receive callback while it runs.
# If it does not answer, reception stays blocked - so it must not wait forever.
BASE_ID_REQUEST_TIMEOUT = 20


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
        self._repeater_mode_change_handlers = []
        self._received_message_count_handler = None

        self._attr_model = GATEWAY_DEFAULT_NAME + " - " + self.dev_type.upper()

        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            self.native_protocol = 'ESP2'
        else:
            self.native_protocol = 'ESP3'
        self._original_dev_name = dev_name
        self._attr_dev_name = config_helpers.get_gateway_name(self._original_dev_name, self.dev_type.value, self.dev_id)

        # Exclusive access to the RS485 bus. Reading the memory of the devices, writing a
        # teach-in and the base id request of a FAM14 all lock the bus in the library and
        # switch the receive callback off while they run. Nothing else may talk on the bus
        # then - a telegram in between disturbs the answers of the devices and can make a scan
        # fail halfway through. See exclusive_bus_access() below.
        self._bus_lock = threading.Lock()
        self._bus_busy_reason = None
        # commands which arrived while the bus was busy: (time, message). They are sent when it
        # is free again, as long as they are not older than BUS_DEFER_SECONDS.
        self._deferred_messages: deque = deque(maxlen=BUS_DEFERRED_LIMIT)
        self._reading_memory_of_devices_is_running = threading.Event()

        # guards the base id/version query, see query_for_base_id_and_version()
        self._base_id_query_lock = asyncio.Lock()
        self._base_id_query_done = False

        self._init_bus()

        self._register_device()

        self.add_connection_state_changed_handler(self.query_for_base_id_and_version)
        self.add_connection_state_changed_handler(self.connection_state_changed)


    async def connection_state_changed(self, connected):
        self._reading_memory_of_devices_is_running.clear()

    async def query_for_base_id_and_version(self, connected):
        """Ask the gateway for its base id and version once per connection.

        This must not run twice in parallel: reading the base id of a FAM14 locks the bus and
        switches the receive callback off for the duration of the request
        (see eltakobus.serial.request_fam14_base_id). Both are only restored in its `finally`
        block, so a second concurrent request deadlocks and leaves the callback disabled -
        which silently stops *all* telegram reception.

        The connection state event can fire more than once for one connection, therefore the
        query is guarded by a lock and a flag.
        """
        if not connected:
            self._base_id_query_done = False     # query again after a reconnect
            return

        # ESP2 gateways which cannot report a base id of their own: a FGW14-USB uses the base
        # id of the FAM14 on its bus, the reverse network bridge has none at all.
        # A FAM14 needs the special (bus locking) request, a FAM-USB answers the normal one,
        # and an ESP2 gateway reached over tcp (`lan-gw-esp2`, e.g. a serial gateway published
        # with socat) forwards that request to whatever hangs behind it - all of them are
        # queried, so the base id never has to be entered by hand.
        if GatewayDeviceType.is_esp2_gateway(self.dev_type) and self.dev_type not in (
                GatewayDeviceType.GatewayEltakoFAM14, GatewayDeviceType.GatewayEltakoFAMUSB,
                GatewayDeviceType.LAN_ESP2):
            return

        if self._base_id_query_done or self._base_id_query_lock.locked():
            LOGGER.debug("[Gateway] [Id: %d] Base id/version query already done or running - skipped.",
                         self.dev_id)
            return

        async with self._base_id_query_lock:
            if self._base_id_query_done:
                return

            # the request of a FAM14 locks the bus and switches the receive callback off, so it
            # is one of the operations which need the bus for themselves
            if not self.try_acquire_bus("base id / version request"):
                self._base_id_query_done = False    # try again after the next connect
                return
            self._base_id_query_done = True

            LOGGER.debug("[Gateway] [Id: %d] Query for base id and version info.", self.dev_id)
            try:
                await asyncio.wait_for(self._bus.send_base_id_request(), timeout=BASE_ID_REQUEST_TIMEOUT)
                await asyncio.wait_for(self._bus.send_version_request(), timeout=BASE_ID_REQUEST_TIMEOUT)
            except asyncio.TimeoutError:
                self._base_id_query_done = False
                LOGGER.warning("[Gateway] [Id: %d] Base id/version request did not answer within %d s. "
                               "Telegram reception can be blocked in this state - use the "
                               "'serial reconnection' button of the gateway to recover.",
                               self.dev_id, BASE_ID_REQUEST_TIMEOUT)
            except Exception as e:  # noqa: BLE001
                self._base_id_query_done = False
                LOGGER.warning("[Gateway] [Id: %d] Cannot query base id/version: %s", self.dev_id, e)
            finally:
                self.release_bus()



    def add_base_id_change_handler(self, handler):
        self._base_id_change_handlers.append(handler)

    def _fire_base_id_change_handlers(self, base_id: AddressExpression):
        for handler in self._base_id_change_handlers:
            self.hass.create_task(
                handler(base_id)
            )

    def add_repeater_mode_change_handler(self, handler):
        self._repeater_mode_change_handlers.append(handler)

    def _fire_repeater_mode_change_handlers(self, mode: int):
        for handler in self._repeater_mode_change_handlers:
            self.hass.create_task(
                handler(mode)
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


    def _record_telegram(self, msg: ESP2Message, direction: TelegramDirection) -> None:
        """Hand over the telegram to the telegram logger, the bus member registry and the
        device activity tracker.

        The bus member registry and the activity tracker run independently of the telegram
        logging setting: the bus member registry holds the channel layout of multi channel
        devices, and the long term information of the tracker (has this device ever reported?
        how often?) is needed exactly when something does not work.
        """
        telegram_logger = get_telegram_logger(self.hass)
        if telegram_logger is not None:
            telegram_logger.record_message(self, msg, direction.value)

        try:
            telegram = prettify(msg) if type(msg) is ESP2Message else msg
        except Exception as e:  # noqa: BLE001 - a telegram which cannot be parsed must not break the bus
            LOGGER.debug("[Gateway] [Id: %s] Cannot prettify telegram: %s", self.dev_id, e)
            return

        note_telegram(self.hass, self, telegram)

        activity_tracker = get_activity_tracker(self.hass)
        if activity_tracker is not None:
            try:
                if isinstance(telegram, POLLING_MESSAGE_TYPES):
                    return
                address, _local_address = resolve_addresses(self, telegram)
                if address:
                    data = getattr(telegram, 'data', None)
                    activity_tracker.record(
                        address, direction.value, type(telegram).__name__, gateway=self,
                        data=b2s(bytes(data)) if isinstance(data, (bytes, bytearray)) else None)
            except Exception as e:  # noqa: BLE001 - tracking must never break the bus
                LOGGER.debug("[Gateway] [Id: %s] Cannot track device activity: %s", self.dev_id, e)

    
    # pyserial validates the baud rate even for a socket url, where it is meaningless (the
    # real rate is set on the device by whoever publishes it). -1 of the LAN types is rejected
    # with "Not a valid baudrate", which crashed the reader thread in an endless retry loop.
    DEFAULT_BAUD_RATE_FOR_URL = 57600

    def _esp2_connection(self) -> tuple[str, int]:
        """(url, baud rate) RS485SerialInterfaceV2 is opened with.

        An ESP2 gateway reached over the network (`lan-gw-esp2`) has no device file: its
        configuration provides a host and a port. pyserial opens a tcp connection for the url
        `socket://<host>:<port>`, so the same serial interface serves both cases.

        This makes a serial gateway usable from a container which cannot access usb: publish
        the port on the host (`dev/share-serial.sh` runs socat) and configure the gateway as
        `lan-gw-esp2` with that host and port.
        """
        path = str(self.serial_path or "")
        baud_rate = self.baud_rate

        if GatewayDeviceType.is_lan_gateway(self.dev_type):
            if '://' not in path:       # not already a pyserial url like socket://host:5100
                path = f"socket://{path}:{self.port}"
            if not baud_rate or baud_rate <= 0:
                baud_rate = self.DEFAULT_BAUD_RATE_FOR_URL

        return path, baud_rate

    def _init_bus(self):
        self._received_message_count = 0
        self._fire_received_message_count_event()

        if GatewayDeviceType.is_esp2_gateway(self.dev_type):
            url, baud_rate = self._esp2_connection()
            LOGGER.debug("[Gateway] [Id: %s] ESP2 connection: %s (baud rate %s)",
                         self.dev_id, url, baud_rate)
            self._bus = RS485SerialInterfaceV2(url,
                                               baud_rate=baud_rate,
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
        # Without a known base id there is nothing to compare against (it is queried from the
        # gateway right after the connection is established). Validating against the
        # placeholder 00-00-00-00 would mark every correct sender id as wrong.
        if self.base_id is None or self.base_id[0][0] != 0xFF:
            LOGGER.debug(f"{device_name}: Base id of gateway '{self.dev_name}' is not available yet - "
                         f"sender id {b2s(sender_id[0])} not validated.")
            return True

        result = config_helpers.compare_enocean_ids(self.base_id[0], sender_id[0])
        if not result:
            LOGGER.warning(f"{device_name}: Sender id {b2s(sender_id[0])} is not in the base id range of "
                           f"gateway '{self.dev_name}' ({getattr(self.dev_type, 'value', self.dev_type)}); expected "
                           f"{b2s(self.base_id[0])[0:8]}-XX. Telegrams with a foreign sender id are "
                           f"not transmitted by the gateway.")
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
            LOGGER.warning(f"{device_name}: Device id {b2s(dev_id[0])} is not a wireless address; gateway "
                           f"'{self.dev_name}' ({getattr(self.dev_type, 'value', self.dev_type)}) is a wireless transceiver and expects "
                           f"FF-XX-XX-XX. Local bus addresses (00-00-XX-XX) only work with a bus gateway "
                           f"(FAM14, FGW14-USB).")
        return result


    def dev_id_validation_by_bus_gateway(self, dev_id: AddressExpression, device_name: str = "") -> bool:
        result = config_helpers.compare_enocean_ids(b'\x00\x00\x00\x00', dev_id[0], len=2)
        if not result:
            LOGGER.warning(f"{device_name}: Device id {b2s(dev_id[0])} is not a local bus address; gateway "
                           f"'{self.dev_name}' ({getattr(self.dev_type, 'value', self.dev_type)}) is a bus gateway and expects "
                           f"00-00-XX-XX.")
        return result
    


    ### -----------------------------------------------------------------------------------
    ### exclusive access to the bus
    ### -----------------------------------------------------------------------------------

    @property
    def is_bus_busy(self) -> bool:
        """True while an operation has the bus for itself (scan, teach-in, base id request)."""
        return self._bus_busy_reason is not None

    @property
    def bus_busy_reason(self) -> str | None:
        """What is occupying the bus right now, for the log and the web ui."""
        return self._bus_busy_reason

    def try_acquire_bus(self, reason: str) -> bool:
        """Take the bus for one operation. False if somebody else already has it.

        Deliberately non-blocking: two scans in parallel are not a queueing problem but a
        mistake, and the caller can say so ('already_running') instead of hanging.
        """
        if not self._bus_lock.acquire(blocking=False):
            LOGGER.warning("[Gateway] [Id: %s] '%s' was refused - the bus is busy with '%s'.",
                           self.dev_id, reason, self._bus_busy_reason)
            return False
        self._bus_busy_reason = reason
        # the flag is what the web ui and the detection have always looked at
        self._reading_memory_of_devices_is_running.set()
        LOGGER.info("[Gateway] [Id: %s] '%s' has the bus - other telegrams wait.",
                    self.dev_id, reason)
        return True

    def release_bus(self) -> None:
        """Give the bus back and send what was waiting for it."""
        if self._bus_busy_reason is None:
            return
        reason = self._bus_busy_reason
        self._bus_busy_reason = None
        self._reading_memory_of_devices_is_running.clear()
        try:
            self._bus_lock.release()
        except RuntimeError:        # never acquired - nothing to release
            pass
        LOGGER.info("[Gateway] [Id: %s] '%s' released the bus.", self.dev_id, reason)
        self._send_deferred_messages()

    @contextmanager
    def exclusive_bus_access(self, reason: str):
        """`with gateway.exclusive_bus_access('bus scan'):` - raises BusBusyError if occupied."""
        if not self.try_acquire_bus(reason):
            raise BusBusyError(f"The bus of gateway {self.dev_id} is busy with "
                               f"'{self._bus_busy_reason}'.")
        try:
            yield self
        finally:
            self.release_bus()

    def _defer_message(self, msg: ESP2Message) -> None:
        """Remember a command which arrived while the bus was busy."""
        self._deferred_messages.append((time.monotonic(), msg))
        LOGGER.info("[Gateway] [Id: %s] The bus is busy with '%s' - message %s waits (%d in the "
                    "queue).", self.dev_id, self._bus_busy_reason, msg,
                    len(self._deferred_messages))

    def _send_deferred_messages(self) -> None:
        """Send what waited for the bus. Runs after an exclusive operation finished.

        A command which waited longer than BUS_DEFER_SECONDS is dropped instead of sent: a
        switch command which arrives minutes late is worse than none, and a bus scan takes
        minutes. What was dropped is logged - it never disappears silently.
        """
        waiting, self._deferred_messages = list(self._deferred_messages), deque(
            maxlen=BUS_DEFERRED_LIMIT)
        if not waiting:
            return

        now = time.monotonic()
        fresh = [msg for queued_at, msg in waiting if now - queued_at <= BUS_DEFER_SECONDS]
        expired = len(waiting) - len(fresh)
        if expired:
            LOGGER.warning("[Gateway] [Id: %s] %d message(s) waited longer than %d s for the bus "
                           "and were dropped.", self.dev_id, expired, BUS_DEFER_SECONDS)
        if not fresh:
            return

        LOGGER.info("[Gateway] [Id: %s] Sending %d message(s) which waited for the bus.",
                    self.dev_id, len(fresh))
        # this can run in the thread of the scan - the sending itself belongs to the event loop
        for msg in fresh:
            try:
                self.hass.add_job(self._callback_send_message_to_serial_bus, msg)
            except Exception as e:  # noqa: BLE001 - one message must not stop the others
                LOGGER.warning("[Gateway] [Id: %s] Cannot send the waiting message %s: %s",
                               self.dev_id, msg, e)

    async def read_memory_of_all_bus_members(self):
        if self.is_bus_busy:
            LOGGER.info("[Gateway] [Id: %s] Reading the device memories was skipped - the bus is "
                        "busy with '%s'.", self.dev_id, self.bus_busy_reason)
            return
        await asyncio.to_thread(asyncio.run, self._read_memory_of_all_bus_members())


    async def _read_memory_of_all_bus_members(self):
        if not self.try_acquire_bus("reading the device memories"):
            return
        try:
            await request_memory_of_all_devices(self._bus)
        except Exception as e:
            LOGGER.exception(f"[Gateway] [Id: {self.dev_id}] {e}")
        finally:
            self.release_bus()




    def reconnect(self):
        try:
            LOGGER.info("[Gateway] [Id: %d] Connection Restart", self.dev_id)
            self._bus.stop()
            self._bus.join(10)    # wait until thread is really stopped
            LOGGER.debug("[Gateway] [Id: %d] Connection stopped", self.dev_id)
            self._init_bus()
            self._bus.start()

            self.request_repeater_mode()
        except Exception as e:
            LOGGER.exception(f"[Gateway] [Id: {self.dev_id}] {e}")


    async def async_setup(self):
        """Initialized serial bus and register callback function on HA event bus."""
        self._bus.start()

        LOGGER.debug("[Gateway] [Id: %d] Was started.", self.dev_id)

        # receive messages from HA event bus
        event_id = config_helpers.get_bus_event_type(gateway_id=self.dev_id, function_id=SIGNAL_SEND_MESSAGE)
        LOGGER.debug("[Gateway] [Id: %s] Register gateway bus for message event_id %s", self.dev_id, event_id)
        self.dispatcher_disconnect_handle = async_dispatcher_connect(
            self.hass, event_id, self._callback_send_message_to_serial_bus
        )

        # Register home assistant service for sending arbitrary telegrams.
        #
        # The service will be registered for each gateway, as the user
        # might have different gateways that cause the eltako relays
        # only to react on them.
        service_name = config_helpers.get_bus_event_type(gateway_id=self.dev_id, function_id=SIGNAL_SEND_MESSAGE_SERVICE)
        LOGGER.debug("[Gateway] [Id: %s] Register send message service %s", self.dev_id, service_name)
        self.hass.services.async_register(DOMAIN, service_name, self.async_service_send_message)


    # Names accepted for the sender address of the send message service. 'id' is the
    # documented one, the others are what users intuitively enter (and what other
    # integrations call it) - accepting them saves a lot of guessing.
    SENDER_ID_SERVICE_FIELDS = ("id", "sender_id", "sender", "address")

    @classmethod
    def get_sender_id_of_service_call(cls, data: dict) -> AddressExpression:
        """Read the sender address out of the data of a send message service call.

        Accepts every field name of SENDER_ID_SERVICE_FIELDS and both notations of an
        address: 'FF-A7-96-82' (string) and 0xFFA79682 (number, e.g. when the yaml editor
        turns the unquoted value into an int). Raises ValueError if there is none.
        """
        for field in cls.SENDER_ID_SERVICE_FIELDS:
            value = data.get(field, None)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                continue

            if isinstance(value, bool):     # bool is an int - and never an address
                raise ValueError(f"Field '{field}' of the sender id is not an address: {value}")

            if isinstance(value, int):
                value = b2s(value.to_bytes(4, 'big'))

            return AddressExpression.parse(str(value).strip())

        raise ValueError(f"No sender id given. Use one of the fields: "
                         f"{', '.join(cls.SENDER_ID_SERVICE_FIELDS)}")

    # Command Section
    async def async_service_send_message(self, event, raise_exception=False) -> None:
        """Send an arbitrary message with the provided eep."""
        LOGGER.debug(f"[Service Send Message: {event.service}] Received event data: {event.data}")

        try:
            sender_id:AddressExpression = self.get_sender_id_of_service_call(event.data)
        except Exception as e:
            LOGGER.error(f"[Service Send Message: {event.service}] No valid sender id defined. ({e}) "
                         f"Given data: {dict(event.data)}")
            if raise_exception:
                raise e
            return

        # Only a warning: the telegram is sent anyway (a foreign sender id can be intended,
        # e.g. for a FTS14EM input). But it is the usual reason for 'nothing happens':
        # a wireless transceiver only transmits sender ids of its own base id range.
        self.validate_sender_id(sender_id, f"[Service Send Message: {event.service}]")

        sender_eep_str = event.data.get("eep", None)
        try:
            sender_eep:EEP = EEP.find(sender_eep_str)
        except Exception as e:
            LOGGER.error(f"[Service Send Message: {event.service}] No valid eep defined. "
                         f"(Given eep: {sender_eep_str})")
            if raise_exception:
                raise e
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

        try:
            eep:EEP = sender_eep(**eep_args)
        except Exception as e:
            LOGGER.error(f"[Service Send Message: {event.service}] Cannot build telegram of eep "
                         f"{sender_eep_str} with the given values {eep_args}: {e}")
            if raise_exception:
                raise e
            return

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
        event_id = config_helpers.get_bus_event_type(gateway_id=self.dev_id, function_id=SIGNAL_SEND_MESSAGE)
        dispatcher_send(self.hass, event_id, msg)
        dispatcher_send(self.hass, ELTAKO_GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': msg})


    def unload(self):
        """Disconnect callbacks established at init time."""
        if self.dispatcher_disconnect_handle:
            self._reading_memory_of_devices_is_running.clear()
            self._bus.stop()
            self._bus.join()
            LOGGER.debug("[Gateway] [Id: %d] Was stopped.", self.dev_id)
            self.dispatcher_disconnect_handle()
            self.dispatcher_disconnect_handle = None

    def request_repeater_mode(self):
        # this goes past _callback_send_message_to_serial_bus straight onto the bus, so it needs
        # its own check - it is a question to the gateway and cannot be queued sensibly
        if self.is_bus_busy:
            LOGGER.info("[Gateway] [Id: %s] The repeater mode request was skipped - the bus is "
                        "busy with '%s'.", self.dev_id, self.bus_busy_reason)
            return
        self.hass.create_task(
            self._bus.send_repeater_mode_request()
        )

    def set_repeater_mode(self, mode):
        if self.is_bus_busy:
            raise BusBusyError(f"The repeater mode cannot be set: the bus of gateway "
                               f"{self.dev_id} is busy with '{self.bus_busy_reason}'.")
        self.hass.create_task(
            self._bus.send_repeater_mode(mode)
        )

    def _callback_send_message_to_serial_bus(self, msg):
        """Send one telegram. Called from the dispatcher and by the deferred queue.

        While an exclusive operation has the bus (a scan, a teach-in, the base id request of a
        FAM14), nothing else may be put on it: the devices answer the running operation, and a
        telegram in between disturbs those answers. Such a command is therefore queued and sent
        when the bus is free again - see _send_deferred_messages.
        """
        if self.is_bus_busy and isinstance(msg, ESP2Message):
            self._defer_message(msg)
            return

        if self._bus.is_active():
            if isinstance(msg, ESP2Message):
                LOGGER.debug("[Gateway] [Id: %d] Send message: %s - Serialized: %s", self.dev_id, msg, msg.serialize().hex())

                # record outgoing telegram for logging and analysis
                self._record_telegram(msg, TelegramDirection.OUTGOING)

                # put message on serial bus
                # TODO: maybe it makes sense to filter for matching base id. currently all gateways try to send message but only those where base id matches do actually send. FAM14 and FGW14-USB will receive any message.
                self.hass.create_task(
                    self._bus.send(msg)
                )
                dispatcher_send(self.hass, ELTAKO_GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': msg})
        else:
            LOGGER.warning("[Gateway] [Id: %d] Serial port %s is not available!!! message (%s) was not sent.", self.dev_id, self.serial_path, msg)


    def _callback_receive_message_from_serial_bus(self, message:ESP2Message):
        """Handle Eltako device's callback.

        This is the callback function called by python-enocan whenever there
        is an incoming message.

        This function runs in the serial reader thread of the library. An exception escaping
        from here kills that thread (see eltakobus.serial.run) - the connection then looks
        active while no telegram is received anymore. Therefore everything is wrapped.
        """
        try:
            self._handle_received_message(message)
        except Exception as e:  # noqa: BLE001 - the reader thread must survive anything
            LOGGER.error("[Gateway] [Id: %s] Error while handling received message %s: %s",
                         self.dev_id, message, e, exc_info=True)


    def _handle_received_message(self, message:ESP2Message):
        """Process one received telegram. Never call directly, see the callback above."""

        # record every incoming telegram (including bus polling) for logging and analysis.
        # The telegram logger itself decides what is relevant and is called first so that
        # nothing gets lost by the filters below.
        self._record_telegram(message, TelegramDirection.INCOMING)

        if type(message) not in [EltakoPoll]:
            LOGGER.debug("[Gateway] [Id: %d] Received message: %s", self.dev_id, message)
            local_message = None
            self.report_message_stats()

            # received base id
            if message.body[:2] == b'\x8b\x98':
                LOGGER.debug("[Gateway] [Id: %d] Received base id: %s", self.dev_id, b2s(message.body[2:6]))
                self._attr_base_id = AddressExpression( (message.body[2:6], None) )
                self._fire_base_id_change_handlers(self.base_id)

            # received repeater mode
            if message.body[:2] == b'\x8b\x99':
                LOGGER.debug("[Gateway] [Id: %d] Received Repeater mode: Filter %s, Repeater Level %s", self.dev_id, b2s(message.body[2:3]), b2s(message.body[3:4]))
                self._fire_repeater_mode_change_handlers( int.from_bytes(message.body[3:4]) )

            # only send messages to HA when base id is known
            if int.from_bytes(self.base_id[0]) != 0:

                # Send message on local bus. Only devices configure to this gateway will receive those message.
                event_id = config_helpers.get_bus_event_type(gateway_id=self.dev_id, function_id=SIGNAL_RECEIVE_MESSAGE)
                dispatcher_send(self.hass, event_id, {'gateway':self, 'esp2_msg': message})

                if type(message) not in [EltakoDiscoveryRequest]:
                    # Send message on global bus with external/outside address
                    global_msg = prettify(message)
                    # do not change discovery and memory message addresses, base id will be sent upfront so that the receive known to whom the message belong
                    if type(message) in [EltakoWrappedRPS, EltakoWrapped4BS, RPSMessage, Regular1BSMessage, Regular4BSMessage, EltakoMessage]:
                        # The address is the last 4 bytes before the status byte of the 11 byte body.
                        address = AddressExpression((message.body[-5:-1], None))
                        if address.is_local_address():
                            local_message = message
                            address = address.add(self.base_id)
                            body = bytearray(message.body)
                            body[-5:-1] = bytearray(address[0])
                            global_msg = prettify(ESP2Message( bytes(body) ))

                    LOGGER.debug("[Gateway] [Id: %d] Forwared message (%s) in global bus", self.dev_id, global_msg)
                    dispatcher_send(self.hass, ELTAKO_GLOBAL_EVENT_BUS_ID, {'gateway':self, 'esp2_msg': global_msg})
                    
                    # events are only fired for frontend
                    self.hass.bus.fire(ELTAKO_GLOBAL_EVENT_BUS_ID, {'gateway': {'name': self.dev_name, 'id': self.dev_id}, 'msg': config_helpers.telegram2json(global_msg, local_message)})
            
    
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
