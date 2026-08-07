"""The gateway of a simulation: an EnOceanGateway whose connection is the simulation.

A simulated gateway is a normal gateway of this integration - the same class hierarchy, the same
entities, the same address validation - with one difference: its bus is not a serial port or a
tcp connection but `SimulatorBus`. Telegrams which are sent go to the simulated devices, and
telegrams which those devices produce are injected exactly where a real gateway hands over what
it read from its port.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from time import monotonic

from eltakobus.message import ESP2Message
from eltakobus.util import AddressExpression, b2s

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from ..config import config_helpers
from ..const import ELTAKO_GLOBAL_EVENT_BUS_ID, GATEWAY_DEFAULT_NAME, LOGGER, GatewayDeviceType
from ..core.gateway import EnOceanGateway
from . import core
from .store import get_registry

LOG_PREFIX_SIM = "Simulator"


class SimulatorBus:
    """Stand-in for the connection of a gateway - no port and no socket is opened.

    It offers what `EnOceanGateway` expects from the communicators of the eltakobus library
    (start/stop/join/is_active/send plus the base id, version and repeater requests), so the
    gateway itself needs no special case for the simulation.
    """

    def __init__(self, gateway: 'SimulatedGateway'):
        self._gateway = gateway
        self._active = False
        self._status_handler = None
        # every telegram Home Assistant sent through this gateway (useful in tests)
        self.sent_messages: list[ESP2Message] = []
        # attributes the library exposes and the integration reads
        self.suppress_echo = False
        self.is_serial_connected = threading.Event()

    def set_status_changed_handler(self, handler) -> None:
        self._status_handler = handler

    def _fire_status(self, status: bool) -> None:
        if self._status_handler is not None:
            self._status_handler(status)

    def is_active(self) -> bool:
        return self._active

    def is_alive(self) -> bool:
        return self._active

    def start(self) -> None:
        self._active = True
        self.is_serial_connected.set()
        self._fire_status(True)

    def stop(self) -> None:
        self._active = False
        self.is_serial_connected.clear()
        self._fire_status(False)

    def join(self, timeout: float = None) -> None:
        return None         # there is no thread to wait for

    async def send(self, msg: ESP2Message) -> None:
        self.sent_messages.append(msg)
        await self._gateway.async_handle_command(msg)

    ### The requests a gateway sends right after connecting. A simulation has no firmware to
    ### ask - its base id comes from its configuration and stays as it is.
    async def send_base_id_request(self) -> None:
        return None

    async def send_version_request(self) -> None:
        return None

    async def send_repeater_mode_request(self) -> None:
        return None

    async def send_repeater_mode(self, mode) -> None:
        return None


class SimulatedGateway(EnOceanGateway):
    """A gateway of a normal type (FAM14, USB300, LAN, ...) whose hardware is simulated.

    Everything which depends on the type - bus gateway or wireless transceiver, ESP2 or ESP3,
    which addresses are valid, which entities exist - stays exactly as it is for the real
    device. Only the connection is replaced.
    """

    is_simulated = True

    def __init__(self, general_settings: dict, hass: HomeAssistant, dev_id: int,
                 dev_type: GatewayDeviceType, base_id: AddressExpression, dev_name: str,
                 port: int, config_entry):
        super().__init__(general_settings, hass, dev_id, dev_type,
                         config_helpers.simulator_serial_path(dev_id), -1, port, base_id,
                         dev_name or core.SIMULATOR_DEFAULT_NAME,
                         auto_reconnect=False, message_delay=None, config_entry=config_entry)

        self._global_bus_disconnect = None
        self._handled_telegrams = deque(maxlen=self.HANDLED_MEMORY_SIZE)

        # A real gateway reports its base id right after connecting, which is where the base id
        # sensor and the address validation get it from. A simulation has no firmware to ask, so
        # it reports the base id of its configuration instead.
        self.add_connection_state_changed_handler(self._report_base_id)

    async def _report_base_id(self, connected: bool) -> None:
        if connected and self.base_id is not None:
            self._fire_base_id_change_handlers(self.base_id)

    def _init_bus(self) -> None:
        """No serial port and no tcp connection - the 'bus' is the simulation itself."""
        self._received_message_count = 0
        self._fire_received_message_count_event()

        self._bus = SimulatorBus(self)
        self._bus.set_status_changed_handler(self._fire_connection_state_changed_event)

    @property
    def model(self) -> str:
        return f"{GATEWAY_DEFAULT_NAME} - {self.dev_type.upper()} (simulated)"

    async def read_memory_of_all_bus_members(self) -> None:
        """A simulated bus has no device memory to read.

        The real implementation locks the bus and talks the Eltako memory protocol to every
        position. There is nothing to talk to here, so the request is refused right away instead
        of running into its timeout - the simulated devices are known anyway: they are listed on
        the simulation page and the detection takes them over from there.
        """
        LOGGER.info(f"[{LOG_PREFIX_SIM}] [Id: {self.dev_id}] Gateway is simulated - it has no "
                    f"device memory to read. Its devices are defined on the simulation page.")

    ### ------------------------------------------------------------------ traffic

    def simulate_base_id_telegram(self) -> ESP2Message:
        """Report the base id, the way a real gateway answers a base id request.

        A FAM14 or an ESP3 stick is asked for its base id right after connecting and answers with
        an info telegram (`8B 98`); that answer is where the base id sensor, the address validation
        and the stored configuration of a gateway created in the web ui come from. The simulation
        has no firmware to ask, so this sends exactly that telegram on demand - which makes the
        whole path testable.
        """
        from eltakobus.serial import RS485SerialInterfaceV2

        telegram = RS485SerialInterfaceV2.create_base_id_info_message(
            self.base_id, GatewayDeviceType.indexOf(self.dev_type) + 1)
        self.simulate_incoming(telegram)
        return telegram

    def simulate_incoming(self, msg: ESP2Message) -> None:
        """Inject a telegram as if the gateway had received it from a real device."""
        LOGGER.debug(f"[{LOG_PREFIX_SIM}] [Id: {self.dev_id}] Simulated telegram: {msg}")
        self._callback_receive_message_from_serial_bus(msg)

    async def async_setup(self) -> None:
        """Start the gateway and listen for the senders which are taught into its actuators.

        Besides the normal setup the gateway listens on the global telegram bus: a sender which
        was taught into one of its simulated actuators may sit anywhere - a real wall switch
        behind a real gateway, a simulated switch of another simulation, or Home Assistant
        itself. Every telegram of the whole installation passes that bus, so this is the one
        place where all of them can be seen.
        """
        await super().async_setup()

        self._global_bus_disconnect = async_dispatcher_connect(
            self.hass, ELTAKO_GLOBAL_EVENT_BUS_ID, self._async_handle_global_telegram)

    def unload(self) -> None:
        if getattr(self, '_global_bus_disconnect', None) is not None:
            self._global_bus_disconnect()
            self._global_bus_disconnect = None
        super().unload()

    async def _async_handle_global_telegram(self, data: dict) -> None:
        """Every telegram of the installation - is one of our actuators taught into its sender?

        The telegrams this gateway produced itself are skipped: they were already handled where
        they came from (a command of Home Assistant in `SimulatorBus.send`, an answer of an
        actuator right below), and answering them again would be an endless loop.
        """
        msg = (data or {}).get('esp2_msg')
        if msg is None or self._was_handled(msg):
            return
        await self.async_handle_command(msg)

    ### Telegrams which were handled a moment ago, so the same telegram arriving over the global
    ### bus is not answered twice. Bounded by time as well as by count: a rocker switch which is
    ### pressed twice sends the identical bytes, and that second press has to work.
    HANDLED_MEMORY_SECONDS = 1.0
    HANDLED_MEMORY_SIZE = 64

    def _remember_handled(self, msg: ESP2Message) -> None:
        try:
            self._handled_telegrams.append((msg.serialize(), monotonic()))
        except Exception:       # noqa: BLE001 - a telegram we cannot serialize is not ours
            pass

    def _was_handled(self, msg: ESP2Message) -> bool:
        try:
            serialized = msg.serialize()
        except Exception:       # noqa: BLE001
            return False
        now = monotonic()
        while self._handled_telegrams and \
                now - self._handled_telegrams[0][1] > self.HANDLED_MEMORY_SECONDS:
            self._handled_telegrams.popleft()
        return any(handled == serialized for handled, _when in self._handled_telegrams)

    async def async_handle_command(self, msg: ESP2Message) -> None:
        """Let every simulated actuator which knows the sender of this telegram answer.

        Which actuators are meant follows from the sender address of the telegram: the sender
        Home Assistant controls the device with, or any sender which was taught into it. A real
        installation behaves exactly like that - one wall switch can be taught into several
        actuators, and each of them answers.
        """
        registry = get_registry(self.hass)
        if registry is None:
            return

        sender = core.sender_of(msg)
        devices = registry.find_all_by_sender(self.dev_id, sender) if sender else []
        if not devices:
            return

        self._remember_handled(msg)
        prettified = core.prettified(msg)
        answers = []
        for device in devices:
            entry = device.find_sender(sender if isinstance(sender, str)
                                       else b2s(bytes(sender)))
            try:
                answer = core.answer_command(device, prettified, (entry or {}).get('eep'))
            except Exception as e:  # noqa: BLE001 - one answer must not break the others
                LOGGER.warning(f"[{LOG_PREFIX_SIM}] [Id: {self.dev_id}] Cannot simulate the "
                               f"answer of {device.address}: {e}")
                continue
            if answer is not None:
                answers.append((device, *answer))

        if not answers:
            return

        await asyncio.sleep(core.ACTUATOR_RESPONSE_DELAY)   # a real actuator needs a moment too
        for device, telegram, state in answers:
            try:
                await registry.async_update_device(self.dev_id, device.address, {'state': state})
            except core.SimulationError as e:
                LOGGER.debug(f"[{LOG_PREFIX_SIM}] Cannot store the simulated state: {e}")
            self._remember_handled(telegram)
            self.simulate_incoming(telegram)


def create_gateway(general_settings: dict, hass: HomeAssistant, gateway_id: int,
                   dev_type: GatewayDeviceType, base_id: AddressExpression, name: str,
                   port: int, config_entry) -> SimulatedGateway:
    """Build the gateway object of a simulated gateway (called by core/integration.py)."""
    LOGGER.info(f"[{LOG_PREFIX_SIM}] Gateway {gateway_id} "
                f"({getattr(dev_type, 'value', dev_type)}) is simulated - no hardware is opened.")
    return SimulatedGateway(general_settings, hass, gateway_id, dev_type, base_id, name,
                            port, config_entry)


def get_gateway(hass: HomeAssistant, gateway_id: int) -> SimulatedGateway | None:
    """The live simulated gateway with this id, or None if it is not set up."""
    from ..core.websocket import get_gateways

    return next((gateway for gateway in get_gateways(hass)
                 if isinstance(gateway, SimulatedGateway)
                 and int(gateway.dev_id) == int(gateway_id)), None)
