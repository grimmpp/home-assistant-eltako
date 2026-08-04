"""In-memory entity registry mirroring homeassistant.helpers.entity_registry."""

from __future__ import annotations

from dataclasses import dataclass

DATA_REGISTRY = "entity_registry"


@dataclass
class RegistryEntry:
    entity_id: str
    unique_id: str | None = None
    platform: str | None = None     # integration domain, e.g. "eltako"
    domain: str | None = None       # component domain, e.g. "light"
    name: str | None = None
    original_name: str | None = None
    device_id: str | None = None
    area_id: str | None = None
    disabled_by: str | None = None


class EntityRegistry:
    def __init__(self, hass):
        self.hass = hass
        self.entities: dict[str, RegistryEntry] = {}

    def async_get(self, entity_id: str) -> RegistryEntry | None:
        return self.entities.get(entity_id)

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str) -> str | None:
        for entry in self.entities.values():
            if entry.domain == domain and entry.platform == platform \
                    and entry.unique_id == unique_id:
                return entry.entity_id
        return None

    def async_get_or_create(self, *, entity_id: str, unique_id=None, platform=None,
                            domain=None, name=None, **kwargs) -> RegistryEntry:
        entry = self.entities.get(entity_id)
        if entry is None:
            entry = RegistryEntry(entity_id=entity_id)
            self.entities[entity_id] = entry
        entry.unique_id = unique_id or entry.unique_id
        entry.platform = platform or entry.platform
        entry.domain = domain or (entity_id.split(".")[0] if "." in entity_id else None)
        entry.original_name = name or entry.original_name
        return entry

    def async_remove(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)


def async_get(hass) -> EntityRegistry:
    registry = hass.data.get(DATA_REGISTRY)
    if registry is None:
        registry = EntityRegistry(hass)
        hass.data[DATA_REGISTRY] = registry
    return registry
