"""The simulated gateways and their devices - plain data, no runtime.

`SimulationModel` is what a caller keeps: it answers which gateways are simulated, which
devices sit behind them and which addresses are still free. It knows nothing about how it is
stored or how a telegram reaches an automation system - that is the job of the layer around it
(in this integration: `simulation/store.py` and `simulation/runtime.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .addressing import (default_base_id, device_address, is_bus_gateway_type, next_free_index,
                         normalize_address, sender_address)
from .constants import ACTUATOR_PLATFORMS, SIMULATED_PLATFORMS, SIMULATOR_DEFAULT_NAME
from .devices import SimulatedDevice
from .errors import SimulationError
from .telegrams import default_state


@dataclass
class SimulatedGateway:
    """A gateway whose hardware does not exist, and the devices behind it.

    `device_type` is a normal gateway type of the integration ('fam14', 'enocean-usb300',
    'mgw-lan', ...): the simulation imitates that very device, so everything which depends on
    the type stays as it is - a simulated FAM14 has devices with local bus addresses, a
    simulated transceiver wireless ones inside its base id range.
    """

    id: int
    device_type: str
    name: str = SIMULATOR_DEFAULT_NAME
    base_id: str = ""
    # False for a *real* gateway which hosts simulated devices: their telegrams are then really
    # transmitted instead of being injected, and their addresses derive from the base id the
    # hardware reported.
    simulated: bool = True
    devices: list[SimulatedDevice] = field(default_factory=list)

    def __post_init__(self):
        self.id = int(self.id)
        self.device_type = str(self.device_type or '')
        self.name = self.name or SIMULATOR_DEFAULT_NAME
        self.base_id = normalize_address(self.base_id) if self.base_id else default_base_id(self.id)

    ### ------------------------------------------------------------------ queries

    @property
    def is_bus_gateway(self) -> bool:
        """A bus gateway (FAM14, FGW14-USB) addresses its devices by their bus position."""
        return is_bus_gateway_type(self.device_type)

    @property
    def used_addresses(self) -> list[str]:
        return [address for device in self.devices
                for address in (device.address, device.sender_id) if address]

    def find(self, address) -> SimulatedDevice | None:
        address = normalize_address(address)
        return next((device for device in self.devices if device.address == address), None)

    def require(self, address) -> SimulatedDevice:
        device = self.find(address)
        if device is None:
            raise SimulationError(f"Gateway {self.id} does not simulate a device with the "
                                  f"address {normalize_address(address)}.")
        return device

    def find_by_sender(self, sender_id) -> SimulatedDevice | None:
        """The first simulated actuator this sender may control."""
        devices = self.find_all_by_sender(sender_id)
        return devices[0] if devices else None

    def find_all_by_sender(self, sender_id) -> list[SimulatedDevice]:
        """Every simulated actuator this sender may control.

        A sender can control more than one actuator - a wall switch taught into three relays is
        the normal case in a real installation, and every one of them answers.
        """
        if sender_id is None:
            return []
        try:
            wanted = normalize_address(sender_id if isinstance(sender_id, str)
                                       else _bytes_to_address(sender_id))
        except SimulationError:
            return []
        return [device for device in self.devices if device.knows_sender(wanted)]

    ### ------------------------------------------------------------- new addresses

    def next_index(self) -> int:
        """Number of the next device - it decides its address and its sender address."""
        return next_free_index(self.used_addresses)

    def suggest_device(self, platform: str, eep: str, sender_eep: str = None, name: str = None,
                       hw_type: str = None) -> dict:
        """A ready to add device with free addresses of this gateway.

        Only what the device *is* has to be given; where it sits follows from the gateway.
        """
        if platform not in SIMULATED_PLATFORMS:
            raise SimulationError(f"'{platform}' cannot be simulated. Known platforms: "
                                  f"{', '.join(sorted(SIMULATED_PLATFORMS))}.")

        index = self.next_index()
        suggestion = {
            'address': device_address(self.base_id, index, self.is_bus_gateway),
            'name': name or hw_type or f"Simulated {platform}",
            'platform': platform,
            'eep': str(eep).upper(),
            'hw_type': hw_type,
            'state': default_state(eep),
        }
        if platform in ACTUATOR_PLATFORMS:
            suggestion['sender_id'] = sender_address(self.base_id, index, self.is_bus_gateway)
            suggestion['sender_eep'] = str(sender_eep).upper() if sender_eep else None
        return suggestion

    ### ----------------------------------------------------------------- changing

    def add(self, device: SimulatedDevice | dict) -> SimulatedDevice:
        device = device if isinstance(device, SimulatedDevice) else SimulatedDevice.from_dict(device)
        if self.find(device.address) is not None:
            raise SimulationError(f"Gateway {self.id} already simulates a device with the "
                                  f"address {device.address}.")
        if device.sender_id:
            other = self.find_by_sender(device.sender_id)
            if other is not None:
                raise SimulationError(f"The sender address {device.sender_id} is already used "
                                      f"by {other.address}.")
        self.devices.append(device)
        return device

    def update(self, address, changes: dict) -> SimulatedDevice:
        """Change a device. Only what is given changes, the rest keeps its value."""
        existing = self.require(address)
        values = existing.to_dict()

        for key in ('name', 'platform', 'eep', 'sender_id', 'sender_eep', 'hw_type', 'area',
                    'interval'):
            if key in (changes or {}):
                values[key] = changes[key]

        # A changed profile starts from the default values of the new one: the fields of the
        # old profile are meaningless for it and would only pile up. Everything else keeps
        # the values the device reported so far, with the given ones merged on top.
        eep_changed = str(values['eep']).upper() != existing.eep
        values['state'] = {**({} if eep_changed else existing.state),
                           **((changes or {}).get('state') or {})}

        updated = SimulatedDevice.create(**values)
        for other in self.devices:
            if other is existing:
                continue
            if other.address == updated.address:
                raise SimulationError(f"Gateway {self.id} already simulates a device with the "
                                      f"address {updated.address}.")
            if updated.sender_id and other.sender_id == updated.sender_id:
                raise SimulationError(f"The sender address {updated.sender_id} is already used "
                                      f"by {other.address}.")

        self.devices[self.devices.index(existing)] = updated
        return updated

    def teach_in(self, address, sender_id, eep: str = None, name: str = None) -> dict:
        """Teach a sender into one of the devices of this gateway."""
        return self.require(address).teach_in(sender_id, eep, name)

    def forget_sender(self, address, sender_id) -> bool:
        return self.require(address).forget_sender(sender_id)

    def remove(self, address) -> bool:
        existing = self.find(address)
        if existing is None:
            return False
        self.devices.remove(existing)
        return True

    ### ------------------------------------------------------------ serialization

    def to_dict(self) -> dict:
        return {'id': self.id, 'device_type': self.device_type, 'name': self.name,
                'base_id': self.base_id, 'simulated': self.simulated,
                'devices': [device.to_dict() for device in self.devices]}

    @classmethod
    def from_dict(cls, data: dict, on_error=None) -> 'SimulatedGateway':
        gateway = cls(id=data['id'], device_type=data.get('device_type', ''),
                      name=data.get('name'), base_id=data.get('base_id'),
                      simulated=bool(data.get('simulated', True)))
        for device in data.get('devices') or []:
            try:
                gateway.add(SimulatedDevice.from_dict(device))
            except SimulationError as e:
                if on_error:
                    on_error(f"Ignoring stored simulated device {device}: {e}")
        return gateway

    def describe(self) -> dict:
        return {'id': self.id, 'device_type': self.device_type, 'name': self.name,
                'base_id': self.base_id, 'bus_gateway': self.is_bus_gateway,
                'simulated': self.simulated,
                'devices': [device.describe() for device in self.devices]}


def _bytes_to_address(value) -> str:
    from eltakobus.util import b2s

    return b2s(bytes(value))


class SimulationModel:
    """All simulated gateways and their devices, plus whether the simulation is paused."""

    def __init__(self, gateways: list[SimulatedGateway] = None, active: bool = True):
        self._gateways: dict[int, SimulatedGateway] = {}
        for gateway in gateways or []:
            self._gateways[gateway.id] = gateway
        # A deactivated simulation exists but is not used: nothing is sent on its own, and the
        # layer above takes its devices out of the automation system. It is deliberately part of
        # the model (and therefore stored): a simulation which was switched off stays off after a
        # restart instead of coming back on its own.
        self.active = bool(active)

    @property
    def paused(self) -> bool:
        """A deactivated simulation is paused as well - nothing of it runs."""
        return not self.active

    ### ---------------------------------------------------------------- gateways

    def add_gateway(self, gateway_id: int, device_type: str, name: str = None,
                    base_id: str = None, simulated: bool = True) -> SimulatedGateway:
        gateway_id = int(gateway_id)
        if gateway_id in self._gateways:
            raise SimulationError(f"Gateway {gateway_id} is already simulated.")
        gateway = SimulatedGateway(id=gateway_id, device_type=device_type, name=name,
                                   base_id=base_id or "", simulated=simulated)
        self._gateways[gateway_id] = gateway
        return gateway

    def remove_gateway(self, gateway_id: int) -> int:
        """Remove a gateway; returns how many of its devices went with it."""
        gateway = self._gateways.pop(int(gateway_id), None)
        return len(gateway.devices) if gateway else 0

    def get_gateway(self, gateway_id: int) -> SimulatedGateway | None:
        try:
            return self._gateways.get(int(gateway_id))
        except (TypeError, ValueError):
            return None

    def require_gateway(self, gateway_id: int) -> SimulatedGateway:
        gateway = self.get_gateway(gateway_id)
        if gateway is None:
            raise SimulationError(f"Gateway {gateway_id} is not simulated.")
        return gateway

    def get_gateway_ids(self) -> list[int]:
        return sorted(self._gateways)

    def get_gateways(self) -> list[SimulatedGateway]:
        return [self._gateways[gateway_id] for gateway_id in self.get_gateway_ids()]

    def is_bus_gateway(self, gateway_id: int) -> bool:
        gateway = self.get_gateway(gateway_id)
        return bool(gateway and gateway.is_bus_gateway)

    ### ----------------------------------------------------------------- devices

    def get_devices(self, gateway_id: int = None) -> list[SimulatedDevice]:
        if gateway_id is None:
            return [device for gateway in self.get_gateways() for device in gateway.devices]
        gateway = self.get_gateway(gateway_id)
        return list(gateway.devices) if gateway else []

    def find(self, gateway_id: int, address) -> SimulatedDevice | None:
        gateway = self.get_gateway(gateway_id)
        return gateway.find(address) if gateway else None

    def require(self, gateway_id: int, address) -> SimulatedDevice:
        return self.require_gateway(gateway_id).require(address)

    def find_by_sender(self, gateway_id: int, sender_id) -> SimulatedDevice | None:
        gateway = self.get_gateway(gateway_id)
        return gateway.find_by_sender(sender_id) if gateway else None

    def add_device(self, gateway_id: int, device) -> SimulatedDevice:
        return self.require_gateway(gateway_id).add(device)

    def update_device(self, gateway_id: int, address, changes: dict) -> SimulatedDevice:
        return self.require_gateway(gateway_id).update(address, changes)

    def set_state(self, gateway_id: int, address, state: dict) -> SimulatedDevice:
        return self.update_device(gateway_id, address, {'state': state})

    def teach_in(self, gateway_id: int, address, sender_id, eep: str = None,
                 name: str = None) -> dict:
        return self.require_gateway(gateway_id).teach_in(address, sender_id, eep, name)

    def forget_sender(self, gateway_id: int, address, sender_id) -> bool:
        return self.require_gateway(gateway_id).forget_sender(address, sender_id)

    def find_all_by_sender(self, gateway_id: int, sender_id) -> list[SimulatedDevice]:
        gateway = self.get_gateway(gateway_id)
        return gateway.find_all_by_sender(sender_id) if gateway else []

    def remove_device(self, gateway_id: int, address) -> bool:
        gateway = self.get_gateway(gateway_id)
        return bool(gateway and gateway.remove(address))

    def suggest_device(self, gateway_id: int, platform: str, eep: str, sender_eep: str = None,
                       name: str = None, hw_type: str = None) -> dict:
        return self.require_gateway(gateway_id).suggest_device(platform, eep, sender_eep,
                                                              name, hw_type)

    ### ------------------------------------------------------------ serialization

    def to_dict(self) -> dict:
        return {'active': self.active,
                'gateways': [gateway.to_dict() for gateway in self.get_gateways()]}

    @classmethod
    def from_dict(cls, data: dict, on_error=None) -> 'SimulationModel':
        """Read back what `to_dict()` produced. A broken entry is skipped, not fatal."""
        # 'paused' is what earlier versions stored
        data = data or {}
        model = cls(active=bool(data.get('active', not data.get('paused', False))))
        for entry in (data or {}).get('gateways') or []:
            try:
                gateway = SimulatedGateway.from_dict(entry, on_error=on_error)
            except (SimulationError, KeyError, TypeError) as e:
                if on_error:
                    on_error(f"Ignoring stored simulated gateway {entry}: {e}")
                continue
            if gateway.id in model._gateways and on_error:
                on_error(f"Simulated gateway {gateway.id} is stored twice - keeping the first.")
                continue
            model._gateways[gateway.id] = gateway
        return model

    def describe(self) -> list[dict]:
        return [gateway.describe() for gateway in self.get_gateways()]
