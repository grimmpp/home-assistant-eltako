"""Which address a simulated gateway and its devices get.

The rules follow the real hardware, because the rest of the integration validates against
them: a bus gateway (FAM14) has devices with local addresses and senders at the usual
00-00-B0-xx offset, a wireless transceiver (USB300, LAN gateway) has devices and senders
inside its base id range.
"""

from __future__ import annotations

from eltakobus.util import AddressExpression, b2s

from .constants import (ADDRESS_PATTERN, BUS_GATEWAY_TYPES, LOCAL_SENDER_OFFSET,
                        SIMULATOR_BASE_ID_PREFIX, SIMULATOR_SERIAL_PATH_PREFIX)
from .errors import SimulationError


def serial_path(gateway_id: int) -> str:
    """'Serial port' of a simulated gateway, e.g. 'simulator-2'."""
    return f"{SIMULATOR_SERIAL_PATH_PREFIX}{int(gateway_id)}"


def is_simulator_serial_path(path: str) -> bool:
    """True for a 'port' which belongs to the simulation and therefore is no real device."""
    return str(path or '').startswith(SIMULATOR_SERIAL_PATH_PREFIX)


def default_base_id(gateway_id: int) -> str:
    """Base id a simulated gateway reports, e.g. 2 -> 'FF-C0-02-00'."""
    return f"{SIMULATOR_BASE_ID_PREFIX}-{int(gateway_id) & 0xFF:02X}-00"


def is_bus_gateway_type(device_type) -> bool:
    """True for a gateway which sits on the RS485 bus (FAM14, FGW14-USB, FTD14)."""
    return str(getattr(device_type, 'value', device_type) or '').lower() in BUS_GATEWAY_TYPES


def normalize_address(address) -> str:
    """'ff-c0-02-01' -> 'FF-C0-02-01'. Raises SimulationError for everything else."""
    try:
        normalized = b2s(AddressExpression.parse(str(address))[0])
    except Exception as e:      # noqa: BLE001 - the library raises several types
        raise SimulationError(f"'{address}' is not a valid EnOcean address (e.g. FF-C0-02-01).") from e
    if not ADDRESS_PATTERN.match(normalized):
        raise SimulationError(f"'{address}' is not a valid EnOcean address (e.g. FF-C0-02-01).")
    return normalized


def address_bytes(address) -> bytes:
    """The four bytes of an address, ready for `EEP.encode_message()`."""
    return AddressExpression.parse(normalize_address(address))[0]


def device_address(base_id: str, index: int, bus: bool = False) -> str:
    """Address of the n-th simulated device.

    A device of a simulated bus gateway gets a local bus address (00-00-00-xx - its position on
    the bus), a device of a simulated transceiver a wireless address inside the base id range
    of that gateway (FF-C0-02-01).
    """
    if bus:
        return f"00-00-00-{int(index) & 0x7F:02X}"
    prefix = '-'.join(normalize_address(base_id).split('-')[:3])
    return f"{prefix}-{int(index) & 0x7F:02X}"


def sender_address(base_id: str, index: int, bus: bool = False) -> str:
    """Address the automation system controls the n-th simulated actuator with.

    It has to be an address the gateway is allowed to transmit: inside its base id range for a
    wireless transceiver (an ESP3 chip enforces that), and the 00-00-B0-xx offset for a bus
    gateway.
    """
    if bus:
        value = LOCAL_SENDER_OFFSET + (int(index) & 0xFF)
        return f"00-00-{value >> 8:02X}-{value & 0xFF:02X}"
    prefix = '-'.join(normalize_address(base_id).split('-')[:3])
    return f"{prefix}-{0x80 | (int(index) & 0x7F):02X}"


def address_to_int(address) -> int:
    """'FF-C0-02-01' -> 0xFFC00201."""
    return int.from_bytes(address_bytes(address), 'big')


def int_to_address(value: int) -> str:
    """0xFFC00201 -> 'FF-C0-02-01'."""
    return b2s(int(value).to_bytes(4, 'big'))


def wireless_address_range(base_id: str) -> tuple[str, str]:
    """First and last address a wireless transceiver may transmit: base id .. base id + 127."""
    base = address_to_int(base_id)
    return int_to_address(base), int_to_address(base + 127)


def validate_hosted_address(base_id: str, address, bus: bool = False) -> str:
    """An address a *real* gateway is able to transmit - normalized, or a `SimulationError`.

    A bus gateway addresses freely, so every well-formed address passes. The ESP3 chip of a
    wireless transceiver refuses to transmit any sender outside its base id range, so such an
    address is refused here - with the valid range in the message, because the base id is
    hardware-given and cannot be read off the housing.
    """
    normalized = normalize_address(address)
    if bus:
        return normalized
    base = address_to_int(base_id)
    if not base <= address_to_int(normalized) <= base + 127:
        low, high = wireless_address_range(base_id)
        raise SimulationError(
            f"{normalized} cannot be transmitted by this gateway: a wireless transceiver only "
            f"sends addresses of its own base id range, {low} to {high}.")
    return normalized


def index_of_address(address) -> int | None:
    """The device number inside an address, e.g. 'FF-C0-02-83' -> 3."""
    try:
        return int(str(address).split('-')[-1], 16) & 0x7F
    except (AttributeError, ValueError):
        return None


def next_free_index(addresses) -> int:
    """Smallest device number which is not used by any of the given addresses yet."""
    used = {index for index in (index_of_address(address) for address in addresses or [])
            if index is not None}
    index = 1
    while index in used:
        index += 1
    return index
