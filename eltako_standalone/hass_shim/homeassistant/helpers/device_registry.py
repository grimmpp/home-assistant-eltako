"""In-memory device registry mirroring homeassistant.helpers.device_registry."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .entity import DeviceInfo  # noqa: F401 - DeviceInfo is importable from both places

DATA_REGISTRY = "device_registry"


@dataclass
class DeviceEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    identifiers: set = field(default_factory=set)
    connections: set = field(default_factory=set)
    name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    area_id: str | None = None
    via_device_id: str | None = None
    suggested_area: str | None = None
    config_entries: set = field(default_factory=set)


class DeviceRegistry:
    def __init__(self, hass):
        self.hass = hass
        self.devices: dict[str, DeviceEntry] = {}

    def async_get_device(self, identifiers=None, connections=None) -> DeviceEntry | None:
        identifiers = set(map(tuple, identifiers or set()))
        for device in self.devices.values():
            if identifiers and identifiers & device.identifiers:
                return device
        return None

    def async_get_or_create(self, *, config_entry_id=None, identifiers=None, connections=None,
                            manufacturer=None, name=None, model=None, suggested_area=None,
                            via_device=None, **kwargs) -> DeviceEntry:
        identifiers = set(map(tuple, identifiers or set()))
        device = self.async_get_device(identifiers=identifiers)
        if device is None:
            device = DeviceEntry(identifiers=identifiers)
            self.devices[device.id] = device
        if connections:
            device.connections |= set(map(tuple, connections))
        if name:
            device.name = name
        if manufacturer:
            device.manufacturer = manufacturer
        if model:
            device.model = model
        if config_entry_id:
            device.config_entries.add(config_entry_id)
        if suggested_area and device.area_id is None:
            from . import area_registry as ar
            registry = ar.async_get(self.hass)
            area = registry.async_get_area_by_name(suggested_area) or registry.async_create(suggested_area)
            device.area_id = area.id
        if via_device:
            parent = self.async_get_device(identifiers={tuple(via_device)})
            device.via_device_id = parent.id if parent else None
        return device

    def async_update_device(self, device_id: str, *, area_id=None, **kwargs) -> DeviceEntry | None:
        device = self.devices.get(device_id)
        if device is None:
            return None
        if area_id is not None:
            device.area_id = area_id
        for key, value in kwargs.items():
            if hasattr(device, key):
                setattr(device, key, value)
        return device

    def async_remove_device(self, device_id: str) -> None:
        self.devices.pop(device_id, None)


def async_get(hass) -> DeviceRegistry:
    registry = hass.data.get(DATA_REGISTRY)
    if registry is None:
        registry = DeviceRegistry(hass)
        hass.data[DATA_REGISTRY] = registry
    return registry
