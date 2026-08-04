"""In-memory area registry mirroring homeassistant.helpers.area_registry."""

from __future__ import annotations

import re
from dataclasses import dataclass

DATA_REGISTRY = "area_registry"


@dataclass
class AreaEntry:
    id: str
    name: str


class AreaRegistry:
    def __init__(self, hass):
        self.hass = hass
        self.areas: dict[str, AreaEntry] = {}

    def async_get_area(self, area_id: str) -> AreaEntry | None:
        return self.areas.get(area_id)

    def async_get_area_by_name(self, name: str) -> AreaEntry | None:
        wanted = str(name).casefold()
        for area in self.areas.values():
            if area.name.casefold() == wanted:
                return area
        return None

    def async_list_areas(self) -> list[AreaEntry]:
        return list(self.areas.values())

    def async_create(self, name: str) -> AreaEntry:
        existing = self.async_get_area_by_name(name)
        if existing is not None:
            return existing
        area_id = re.sub(r"[^a-z0-9_]+", "_", str(name).lower()).strip("_") or "area"
        base, index = area_id, 2
        while area_id in self.areas:
            area_id = f"{base}_{index}"
            index += 1
        area = AreaEntry(id=area_id, name=str(name))
        self.areas[area_id] = area
        return area


def async_get(hass) -> AreaRegistry:
    registry = hass.data.get(DATA_REGISTRY)
    if registry is None:
        registry = AreaRegistry(hass)
        hass.data[DATA_REGISTRY] = registry
    return registry
