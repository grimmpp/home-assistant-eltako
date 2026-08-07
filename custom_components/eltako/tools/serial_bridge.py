"""Bridge a serial gateway to a machine or container which cannot reach the usb port itself.

Docker on macOS and Windows runs in a linux vm without usb access, so a stick plugged into the
developer machine never arrives in the container - `devices:` cannot forward what the vm does
not have. This module moves the port instead of the device, in two halves which are the exact
counterparts of each other:

* **publish** - runs where the stick is (the host). Opens the serial port and offers its bytes
  on a tcp port, one client at a time.
* **attach** - runs where the gateway is expected (the container). Connects to a publisher and
  exposes the byte stream as a **pty**, symlinked to a path like `/dev/ttyUSB0`.

The second half is what makes the **automatic gateway detection** testable: the detection globs
`/dev/ttyUSB*` and probes what it finds ([`gateway_scan`](gateway_scan.py),
[`plug_and_play`](plug_and_play.py)). Configuring the published port as a `lan-gw-esp2` network
gateway also works, but then nothing is detected - the gateway is declared by hand, which is the
opposite of what a detection test is supposed to show.

Everything here is plain pyserial plus sockets and threads: no socat, no asyncio, no Home
Assistant. On top of the two classes sits a transport-agnostic control layer (`start_bridge`,
`stop_bridge`, `bridge_status`) which takes and returns plain json-able dicts, so the CLI, the
websocket command at the bottom of this file and a REST endpoint all drive the same objects.

Two details decide whether this works at all, and both differ from a naive socat invocation:

* the pty **stays alive** when its reader closes it. `pty.openpty()` returns a master/slave
  pair; the slave fd is deliberately kept open for the lifetime of the attachment, otherwise
  the master reports EIO as soon as the last reader disconnects and the symlink would point
  into nothing. A probe opens and closes the port several times, so a pty which dies with its
  first reader is useless here.
* the serial port is opened **per client**, not for the lifetime of the publisher. A serial
  port can only be held by one process, so keeping it open would lock out PCT14, the EnOcean
  Device Manager or a second runtime while nothing is even connected.
"""

from __future__ import annotations

import errno
import os
import socket
import threading

from ..const import LOGGER

LOG_PREFIX_BRIDGE = "Serial Bridge"

DEFAULT_TCP_PORT = 5100
DEFAULT_PTY_LINK = "/dev/ttyUSB0"

# a read returns as soon as bytes are there; the timeout only decides how fast a stopped
# bridge notices that it should stop
POLL_TIMEOUT = 0.2
CHUNK_SIZE = 1024
RECONNECT_DELAY = 1.0


def _no_delay(connection: socket.socket) -> None:
    """Switch Nagle's algorithm off - it would break the protocol, not just slow it down.

    ESP2 frames are 14 bytes and the answers are timed: a FAM14 is recognized by the **echo**
    of what was written to it, and its base id request has a timeout in the low seconds.
    Nagle holds a small write back until the previous one is acknowledged, which adds up to
    ~40 ms per frame - enough for the echo detection to conclude that the line does not echo
    and for the base id query to run dry. The symptom is a gateway which connects and then
    logs 'Failed to load base_id from FAM14', with the bus scan never starting.
    """
    try:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError as e:    # pragma: no cover - not every platform has the option
        LOGGER.debug(f"[{LOG_PREFIX_BRIDGE}] Cannot set TCP_NODELAY: {e}")


def _make_raw(fd: int) -> None:
    """Put a pty into raw mode - a fresh one is a *terminal*, and that corrupts the protocol.

    `pty.openpty()` hands out a line discipline in canonical mode with echo on, which is right
    for a shell and wrong for everything else: it echoes back what the reader writes (so the
    FAM14 echo detection sees an echo which never came from the bus, or misses the real one),
    it translates CR/LF, and it treats 0x11/0x13 as flow control - all of which occur inside a
    14 byte ESP2 frame. Without this the byte counters of the two halves disagree, which is
    exactly what the corruption looks like from the outside.
    """
    import termios
    import tty

    tty.setraw(fd)
    # setraw already clears the flags below on most platforms; doing it explicitly keeps the
    # bridge byte-transparent on the ones where it does not
    attributes = termios.tcgetattr(fd)
    attributes[0] &= ~(termios.IXON | termios.IXOFF | termios.ICRNL | termios.INLCR)
    attributes[1] &= ~termios.OPOST
    attributes[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG)
    termios.tcsetattr(fd, termios.TCSANOW, attributes)


class SerialBridgeError(Exception):
    """The bridge cannot be set up - the port does not exist, is in use, or is unreachable."""


def _pump(read, write, counter: dict, key: str, stop: threading.Event, name: str) -> None:
    """Move bytes from one side to the other until one of them ends or `stop` is set."""
    try:
        while not stop.is_set():
            data = read()
            if data is None:            # timeout - just look at `stop` again
                continue
            if data == b'':             # the other side closed
                break
            write(data)
            counter[key] += len(data)
    except (OSError, socket.error) as e:
        # EIO on a pty and a reset connection are the normal way a peer goes away
        if not stop.is_set():
            LOGGER.debug(f"[{LOG_PREFIX_BRIDGE}] {name} ended: {e}")
    finally:
        stop.set()


### ---------------------------------------------------------------------------
### host side: publish a serial port over tcp
### ---------------------------------------------------------------------------

class SerialPublisher:
    """Offers a serial port on a tcp port. One client at a time, reconnect is supported."""

    def __init__(self, device: str, baud_rate: int, port: int = DEFAULT_TCP_PORT,
                 host: str = '0.0.0.0'):
        self.device = device
        self.baud_rate = baud_rate
        self.port = port
        self.host = host

        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._client_address: str | None = None
        self._counter = {'to_device': 0, 'from_device': 0}
        self._connections = 0
        self._error: str | None = None

    ### control -------------------------------------------------------------

    def start(self) -> None:
        """Bind the tcp port and serve in the background. Raises if the port cannot be used."""
        import serial

        # fail fast on a device which does not exist or is held by another program, instead of
        # accepting a client and only then reporting it
        try:
            serial.Serial(self.device, baudrate=self.baud_rate, timeout=0.1).close()
        except Exception as e:  # noqa: BLE001 - pyserial raises several unrelated types
            raise SerialBridgeError(f"Cannot open {self.device}: {e}") from e

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind((self.host, self.port))
            server.listen(1)
        except OSError as e:
            server.close()
            raise SerialBridgeError(f"Cannot listen on {self.host}:{self.port}: {e}") from e
        server.settimeout(POLL_TIMEOUT)

        self._server = server
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="eltako-serial-publisher",
                                        daemon=True)
        self._thread.start()
        LOGGER.info(f"[{LOG_PREFIX_BRIDGE}] Publishing {self.device} ({self.baud_rate} baud) "
                    f"on {self.host}:{self.port}")

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None

    ### state ---------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict:
        return {
            'role': 'publish',
            'running': self.is_running,
            'device': self.device,
            'baud_rate': self.baud_rate,
            'listen': f"{self.host}:{self.port}",
            'client': self._client_address,
            'connections': self._connections,
            'bytes_to_device': self._counter['to_device'],
            'bytes_from_device': self._counter['from_device'],
            'error': self._error,
        }

    ### the loop ------------------------------------------------------------

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                client, address = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break               # the server socket was closed by stop()

            self._connections += 1
            self._client_address = f"{address[0]}:{address[1]}"
            LOGGER.info(f"[{LOG_PREFIX_BRIDGE}] {self._client_address} connected to "
                        f"{self.device}")
            try:
                self._serve_client(client)
            except SerialBridgeError as e:
                self._error = str(e)
                LOGGER.warning(f"[{LOG_PREFIX_BRIDGE}] {e}")
            finally:
                try:
                    client.close()
                except OSError:
                    pass
                self._client_address = None

    def _serve_client(self, client: socket.socket) -> None:
        """Open the serial port for exactly this connection and pump both directions."""
        import serial

        try:
            uart = serial.Serial(self.device, baudrate=self.baud_rate, timeout=POLL_TIMEOUT)
        except Exception as e:  # noqa: BLE001
            raise SerialBridgeError(f"Cannot open {self.device} for the client: {e}") from e

        client.settimeout(POLL_TIMEOUT)
        _no_delay(client)
        session = threading.Event()

        def read_client():
            try:
                return client.recv(CHUNK_SIZE)
            except socket.timeout:
                return None

        def read_uart():
            data = uart.read(CHUNK_SIZE if uart.in_waiting else 1)
            return data or None     # a timeout without bytes is not a closed port

        try:
            outbound = threading.Thread(
                target=_pump, args=(read_client, uart.write, self._counter, 'to_device',
                                    session, "tcp -> serial"), daemon=True)
            outbound.start()
            _pump(read_uart, client.sendall, self._counter, 'from_device', session,
                  "serial -> tcp")
            outbound.join(2)
        finally:
            uart.close()


### ---------------------------------------------------------------------------
### container side: attach a published port as a pty
### ---------------------------------------------------------------------------

class PtyAttachment:
    """Connects to a `SerialPublisher` and exposes it as a pty under `link`.

    The pty survives a reader which opens and closes it repeatedly - that is what a detection
    probe does, and what a plain `socat PTY,link=... TCP:...` does not survive.
    """

    def __init__(self, host: str, port: int = DEFAULT_TCP_PORT, link: str = DEFAULT_PTY_LINK):
        self.host = host
        self.port = port
        self.link = link

        self._master: int | None = None
        self._slave: int | None = None
        self._pty_path: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._counter = {'to_device': 0, 'from_device': 0}
        self._connected = False
        self._connections = 0
        self._error: str | None = None

    ### control -------------------------------------------------------------

    def start(self) -> None:
        """Create the pty, place the symlink and connect in the background."""
        try:
            import pty
        except ImportError as e:    # pragma: no cover - windows
            raise SerialBridgeError(
                "A pty is a posix feature - on windows use a virtual serial port pair "
                "(com0com) and the publisher, or run the standalone runtime directly.") from e

        master, slave = pty.openpty()
        # keep the slave open ourselves: without a single open slave fd the master reports EIO
        # the moment the last reader disconnects, and every further probe would fail
        self._master, self._slave = master, slave
        self._pty_path = os.ttyname(slave)
        _make_raw(slave)

        try:
            self._place_link()
        except OSError as e:
            self._close_pty()
            raise SerialBridgeError(f"Cannot create the symlink {self.link}: {e}") from e

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="eltako-pty-attachment",
                                        daemon=True)
        self._thread.start()
        LOGGER.info(f"[{LOG_PREFIX_BRIDGE}] {self.link} -> {self._pty_path} "
                    f"(connects to {self.host}:{self.port})")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None
        self._remove_link()
        self._close_pty()

    ### state ---------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def path(self) -> str | None:
        """The path the integration should be pointed at."""
        return self.link or self._pty_path

    def status(self) -> dict:
        return {
            'role': 'attach',
            'running': self.is_running,
            'connected': self._connected,
            'source': f"{self.host}:{self.port}",
            'link': self.link,
            'pty': self._pty_path,
            'connections': self._connections,
            'bytes_to_device': self._counter['to_device'],
            'bytes_from_device': self._counter['from_device'],
            'error': self._error,
        }

    ### the pty -------------------------------------------------------------

    def _place_link(self) -> None:
        if not self.link:
            return
        # a link left behind by a killed bridge points at a pty which no longer exists
        if os.path.islink(self.link):
            os.unlink(self.link)
        elif os.path.exists(self.link):
            raise OSError(f"{self.link} exists and is not a symlink")
        os.symlink(self._pty_path, self.link)

    def _remove_link(self) -> None:
        if not self.link:
            return
        try:
            if os.path.islink(self.link) and os.readlink(self.link) == self._pty_path:
                os.unlink(self.link)
        except OSError:
            pass

    def _close_pty(self) -> None:
        for fd in (self._master, self._slave):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self._master = self._slave = None

    ### the loop ------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                connection = socket.create_connection((self.host, self.port), timeout=5)
            except OSError as e:
                self._error = f"Cannot reach {self.host}:{self.port}: {e}"
                LOGGER.debug(f"[{LOG_PREFIX_BRIDGE}] {self._error} - retrying")
                if self._stop.wait(RECONNECT_DELAY):
                    break
                continue

            self._error = None
            self._connected = True
            self._connections += 1
            LOGGER.info(f"[{LOG_PREFIX_BRIDGE}] Connected to {self.host}:{self.port}, "
                        f"serving {self.link or self._pty_path}")
            try:
                self._serve(connection)
            finally:
                self._connected = False
                try:
                    connection.close()
                except OSError:
                    pass
            if self._stop.wait(RECONNECT_DELAY):
                break

    def _serve(self, connection: socket.socket) -> None:
        connection.settimeout(POLL_TIMEOUT)
        _no_delay(connection)
        session = threading.Event()
        master = self._master

        def read_connection():
            try:
                return connection.recv(CHUNK_SIZE)
            except socket.timeout:
                return None

        def read_master():
            # the master has no timeout, so it is polled - a pty with no writer simply has
            # nothing to read, which select reports as "not ready"
            import select
            readable, _, _ = select.select([master], [], [], POLL_TIMEOUT)
            if not readable:
                return None
            try:
                return os.read(master, CHUNK_SIZE) or None
            except OSError as e:
                # EIO would mean every slave fd is gone - cannot happen while we hold one
                if e.errno == errno.EIO:
                    return None
                raise

        inbound = threading.Thread(
            target=_pump, args=(read_connection, lambda data: os.write(master, data),
                                self._counter, 'from_device', session, "tcp -> pty"),
            daemon=True)
        inbound.start()
        _pump(read_master, connection.sendall, self._counter, 'to_device', session,
              "pty -> tcp")
        inbound.join(2)


def publish(device: str, baud_rate: int, port: int = DEFAULT_TCP_PORT,
            host: str = '0.0.0.0') -> SerialPublisher:
    """Start a publisher in the background and return it."""
    publisher = SerialPublisher(device, baud_rate, port, host)
    publisher.start()
    return publisher


def attach(host: str, port: int = DEFAULT_TCP_PORT,
           link: str = DEFAULT_PTY_LINK) -> PtyAttachment:
    """Start an attachment in the background and return it."""
    attachment = PtyAttachment(host, port, link)
    attachment.start()
    return attachment


### ---------------------------------------------------------------------------
### control layer - the same calls for the cli, a websocket command and rest
### ---------------------------------------------------------------------------

# Bridges which this process runs, by name. A bridge outlives the call which started it, so
# something has to hold it - and the caller must be able to find it again to stop it. The
# registry is deliberately process local: a bridge is a file descriptor and a thread, neither
# of which survives a restart, so persisting it would only promise something it cannot keep.
_BRIDGES: dict[str, SerialPublisher | PtyAttachment] = {}
_REGISTRY_LOCK = threading.Lock()


def _name_of(role: str, bridge) -> str:
    if role == 'publish':
        return f"publish:{bridge.port}"
    return f"attach:{bridge.link or bridge.path}"


def start_bridge(role: str, device: str = None, baud_rate: int = None,
                 host: str = None, port: int = DEFAULT_TCP_PORT,
                 link: str = DEFAULT_PTY_LINK) -> dict:
    """Start a bridge and return its status. `role` is 'publish' or 'attach'.

    Raises `SerialBridgeError` for everything a caller can fix (missing argument, port in use,
    device not there), so every transport can turn it into its own error format.
    """
    if role == 'publish':
        if not device or not baud_rate:
            raise SerialBridgeError("publish needs 'device' and 'baud_rate'")
        bridge = SerialPublisher(device, int(baud_rate), int(port), host or '0.0.0.0')
    elif role == 'attach':
        if not host:
            raise SerialBridgeError("attach needs 'host' - the machine the port is published on")
        bridge = PtyAttachment(host, int(port), link or DEFAULT_PTY_LINK)
    else:
        raise SerialBridgeError(f"Unknown role '{role}' - expected 'publish' or 'attach'")

    name = _name_of(role, bridge)
    with _REGISTRY_LOCK:
        if name in _BRIDGES and _BRIDGES[name].is_running:
            raise SerialBridgeError(f"A bridge '{name}' is already running")
        bridge.start()          # raises before anything is registered
        _BRIDGES[name] = bridge

    return {'name': name, **bridge.status()}


def stop_bridge(name: str) -> dict:
    """Stop one bridge by the name `start_bridge` returned."""
    with _REGISTRY_LOCK:
        bridge = _BRIDGES.pop(name, None)
    if bridge is None:
        raise SerialBridgeError(f"No bridge '{name}'")
    bridge.stop()
    return {'name': name, **bridge.status()}


def stop_all_bridges() -> list[dict]:
    """Stop everything this process runs - for a shutdown handler or a test teardown."""
    with _REGISTRY_LOCK:
        names = list(_BRIDGES)
    return [stop_bridge(name) for name in names if name in _BRIDGES]


def bridge_status() -> list[dict]:
    """Status of every bridge of this process."""
    with _REGISTRY_LOCK:
        items = list(_BRIDGES.items())
    return [{'name': name, **bridge.status()} for name, bridge in items]


### ---------------------------------------------------------------------------
### websocket api - a thin adapter over the control layer above
### ---------------------------------------------------------------------------

def register_websocket_commands(hass) -> None:
    from homeassistant.components import websocket_api

    websocket_api.async_register_command(hass, ws_bridge_list)
    websocket_api.async_register_command(hass, ws_bridge_start)
    websocket_api.async_register_command(hass, ws_bridge_stop)


def _ws_commands():
    """Imported lazily so this module stays usable without Home Assistant."""
    import voluptuous as vol
    from homeassistant.components import websocket_api

    from ..const import WS_BRIDGE_LIST, WS_BRIDGE_START, WS_BRIDGE_STOP

    @websocket_api.require_admin
    @websocket_api.websocket_command({vol.Required('type'): WS_BRIDGE_LIST})
    @websocket_api.async_response
    async def ws_list(hass, connection, msg) -> None:
        connection.send_result(msg['id'], {'bridges': bridge_status()})

    @websocket_api.require_admin
    @websocket_api.websocket_command({
        vol.Required('type'): WS_BRIDGE_START,
        vol.Required('role'): vol.In(['publish', 'attach']),
        vol.Optional('device'): str,
        vol.Optional('baud_rate'): int,
        vol.Optional('host'): str,
        vol.Optional('port', default=DEFAULT_TCP_PORT): int,
        vol.Optional('link', default=DEFAULT_PTY_LINK): str,
    })
    @websocket_api.async_response
    async def ws_start(hass, connection, msg) -> None:
        # binding a socket and opening a serial port block - keep them out of the event loop
        def run():
            return start_bridge(msg['role'], device=msg.get('device'),
                                baud_rate=msg.get('baud_rate'), host=msg.get('host'),
                                port=msg['port'], link=msg['link'])
        try:
            connection.send_result(msg['id'], await hass.async_add_executor_job(run))
        except SerialBridgeError as e:
            connection.send_error(msg['id'], 'bridge_failed', str(e))

    @websocket_api.require_admin
    @websocket_api.websocket_command({vol.Required('type'): WS_BRIDGE_STOP,
                                      vol.Required('name'): str})
    @websocket_api.async_response
    async def ws_stop(hass, connection, msg) -> None:
        try:
            result = await hass.async_add_executor_job(stop_bridge, msg['name'])
            connection.send_result(msg['id'], result)
        except SerialBridgeError as e:
            connection.send_error(msg['id'], 'bridge_failed', str(e))

    return ws_list, ws_start, ws_stop


try:        # pragma: no cover - the import only fails outside of a runtime
    ws_bridge_list, ws_bridge_start, ws_bridge_stop = _ws_commands()
except ImportError:     # the module is also used by the cli, without any hass api
    ws_bridge_list = ws_bridge_start = ws_bridge_stop = None
