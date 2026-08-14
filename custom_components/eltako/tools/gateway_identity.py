"""The unique id of a stick - and the only reliable way to recognize it again.

Two different ids can identify the hardware behind a serial port, and they answer different
questions:

* the **usb serial number** of the serial chip (`serial_number` of a `gateway_scan` entry).
  Readable without opening the port, but it belongs to the FTDI/CP210x chip, not to the
  EnOcean hardware: cheap chips carry none at all, both interfaces of a two port stick report
  the *same* one, and inside a container sysfs holds no usb information whatsoever.
* the **chip id** of the EnOcean transceiver and its **base id**. Both are assigned in the
  factory and cannot be changed, so they identify the device itself - but reading them means
  opening the port and asking: an ESP3 stick answers `CO_RD_VERSION` (chip id, versions) and
  `CO_RD_IDBASE` (base id), a FAM-USB answers the ESP2 request `AB 58` with its base id.

That is why this module exists next to the passive scan: `gateway_scan` reads what udev and
sysfs know, this one talks to the stick. The chip id it reads is what makes a gateway
survive a renumbered or swapped `/dev/ttyUSB*` without anybody editing the configuration -
see `gateway_scan.choose_port`.

Not every gateway can say who it is: a FAM14 and an FGW14-USB have no transceiver of their
own (the FGW14-USB uses the base id of the FAM14 on its bus), and reading the base id of a
FAM14 locks the whole RS485 bus for the duration of the request. For those the usb serial
number of their adapter stays the only fingerprint - `can_identify()` says so.
"""

from __future__ import annotations

import asyncio
import time

from eltakobus.gateway_identity import (
    VERSION_RESPONSE_LENGTH,
    fam_usb_base_id_request,
    format_id,
    identity_capabilities,
    parse_fam_usb_base_id,
    parse_version_response,
)
from eltakobus.const import baud_rate_for

from ..const import GatewayDeviceType, LOGGER

LOG_PREFIX_ID = "Gateway Identity"

# A port which is no gateway cannot be told apart from a gateway which stays silent, so every
# question costs its full timeout. A device which is there answers on the first attempt.
CONNECT_TIMEOUT = 1.0               # time granted to a communicator to open the port
BASE_ID_TIMEOUT = 1.0               # the base id request of a FAM-USB really needs up to 1 s
BASE_ID_RETRIES = 1
CHIP_ID_TIMEOUT = 1.0

# base id request of a FAM-USB (ESP2, 'AB 58')
# a base id which is not one - the FAM-USB answers this while it is still starting up
EMPTY_BASE_ID = '00-00-00-00'

# CO_RD_VERSION (ESP3 common command 0x03) is answered with 32 bytes:
# app version (4), api version (4), chip id (4), chip version (4), app description (16)
def can_identify(device_type) -> bool:
    """Whether opening this gateway's port can produce a chip id or base id."""
    capabilities = identity_capabilities(getattr(device_type, 'value', device_type))
    return capabilities['can_read_base_id'] or capabilities['can_read_chip_id']


def baud_rate_of(device_type) -> int:
    """Baud rate the stick of this gateway type is opened with (0 if it has no serial port)."""
    return max(0, baud_rate_for(getattr(device_type, 'value', device_type), 0))


### ---------------------------------------------------------------------------
### reading the ids of an open communicator
### ---------------------------------------------------------------------------

async def async_read_esp2_base_id(communicator, timeout: float = BASE_ID_TIMEOUT,
                                  retries: int = BASE_ID_RETRIES) -> str | None:
    """Base id of an ESP2 transceiver (FAM-USB) - the proof that it is one.

    The communicator must be ours: the callback is switched off for the request, because the
    answer has to be read from the exchange and not handed to a gateway.
    """
    from eltakobus.message import ESP2Message

    try:
        communicator.set_callback(None)
        response = await communicator.exchange(fam_usb_base_id_request(),
                                               ESP2Message, retries=retries, timeout=timeout)
        return parse_fam_usb_base_id(response)
    except Exception:   # noqa: BLE001 - no answer means: nothing which answers this request
        return None


async def async_read_esp3_identity(communicator, timeout: float = CHIP_ID_TIMEOUT) -> dict:
    """{chip_id, base_id, versions} of an ESP3 stick whose port we hold open.

    Without a callback the library puts every received packet into `communicator.receive`, so
    the answer is picked from that queue - and everything which is not the answer is put back,
    the same way the library does it for the base id request.
    """
    import queue

    from enocean.protocol.constants import PACKET, RETURN_CODE

    base_id = None
    try:
        base_id = format_id(await communicator.async_base_id)
    except Exception as e:      # noqa: BLE001 - an unreachable stick has no identity
        LOGGER.debug(f"[{LOG_PREFIX_ID}] Cannot read the base id: {e}")

    if not base_id:
        # nothing answered the base id request, so this is no ESP3 gateway. Asking for the
        # version as well would only cost another timeout - which the probe pays per port.
        return {}

    identity = {'base_id': base_id}
    try:
        await communicator.send_version_request()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                packet = communicator.receive.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            if (getattr(packet, 'packet_type', None) == PACKET.RESPONSE
                    and getattr(packet, 'response', None) == RETURN_CODE.OK
                    and len(packet.response_data) == VERSION_RESPONSE_LENGTH):
                identity.update({key: value for key, value
                                 in parse_version_response(packet.response_data).items() if value})
                communicator.receive.put(packet)     # a caller may still want to see it
                break
            communicator.receive.put(packet)
    except Exception as e:      # noqa: BLE001
        LOGGER.debug(f"[{LOG_PREFIX_ID}] Cannot read the chip id: {e}")

    return {key: value for key, value in identity.items() if value}


### ---------------------------------------------------------------------------
### opening a free port to ask the stick behind it
### ---------------------------------------------------------------------------

def start_communicator(communicator) -> None:
    """A port which blocks while being read must not keep the process alive."""
    communicator.daemon = True
    communicator.start()


def stop_communicator(communicator) -> None:
    if communicator is None:
        return
    try:
        communicator.stop()
        communicator.join(0.5)
    except Exception as e:  # noqa: BLE001
        LOGGER.debug(f"[{LOG_PREFIX_ID}] Cannot stop the communicator: {e}")


async def async_read_identity(device: str, device_type, baud_rate: int = 0) -> dict:
    """Open a free port and ask the stick who it is. {} for everything which cannot say.

    The port must not be in use - opening it a second time fails (pyserial locks it
    exclusively), and opening the port of a running gateway would interrupt its reception.
    The caller decides that, see `gateway_scan._async_identify_ports`.
    """
    if not can_identify(device_type):
        return {}

    baud_rate = baud_rate or baud_rate_of(device_type)
    if not baud_rate:
        return {}

    is_esp2 = GatewayDeviceType.is_esp2_gateway(
        device_type if isinstance(device_type, GatewayDeviceType)
        else GatewayDeviceType.find(str(device_type)))

    communicator = None
    try:
        if is_esp2:
            from eltakobus.serial import RS485SerialInterfaceV2
            communicator = RS485SerialInterfaceV2(device, baud_rate=baud_rate, delay_message=0.2,
                                                  auto_reconnect=False)
            start_communicator(communicator)
            if not communicator.is_serial_connected.wait(CONNECT_TIMEOUT):
                return {}
            base_id = await async_read_esp2_base_id(communicator)
            return {'base_id': base_id} if base_id and base_id != EMPTY_BASE_ID else {}

        from esp2_gateway_adapter.esp3_serial_com import ESP3SerialCommunicator
        communicator = ESP3SerialCommunicator(device, auto_reconnect=False)
        start_communicator(communicator)
        if not communicator.is_serial_connected.wait(CONNECT_TIMEOUT):
            return {}
        return await async_read_esp3_identity(communicator)
    except Exception as e:      # noqa: BLE001 - a port which says nothing is the normal case
        LOGGER.debug(f"[{LOG_PREFIX_ID}] {device} did not report an identity: {e}")
        return {}
    finally:
        stop_communicator(communicator)


def read_identity(device: str, device_type, baud_rate: int = 0) -> dict:
    """`async_read_identity` for an executor thread - it brings its own event loop.

    Must NOT be called in the event loop of Home Assistant, same reason as
    `plug_and_play.probe_ports`.
    """
    return asyncio.run(async_read_identity(device, device_type, baud_rate))
