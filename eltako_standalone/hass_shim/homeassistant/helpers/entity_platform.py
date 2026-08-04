"""Entity platform mirroring homeassistant.helpers.entity_platform.

The integration reads hass.data[DATA_ENTITY_PLATFORM][<integration domain>] and
expects a list of platforms, each with `.domain` and an `.entities` dict - this
module provides exactly that structure.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

LOGGER = logging.getLogger("homeassistant.shim.entity_platform")

DATA_ENTITY_PLATFORM = "entity_platform"

# typing alias like in HA
AddEntitiesCallback = Callable[[Iterable, bool], None]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(text).lower())
    return re.sub(r"_+", "_", slug).strip("_") or "entity"


class EntityPlatform:
    def __init__(self, hass, *, domain: str, platform_name: str, config_entry=None):
        self.hass = hass
        self.domain = str(domain)                  # e.g. "light"
        self.platform_name = platform_name         # e.g. "eltako"
        self.config_entry = config_entry
        self.entities: dict[str, object] = {}

    # signature compatible with AddEntitiesCallback
    def async_add_entities(self, new_entities, update_before_add: bool = False) -> None:
        from . import entity_registry as er, device_registry as dr

        for entity in new_entities:
            entity.hass = self.hass
            entity.platform = self

            unique_id = getattr(entity, "unique_id", None)
            if unique_id and any(getattr(existing, "unique_id", None) == unique_id
                                 for existing in self._all_domain_entities()):
                LOGGER.warning("Skipping entity with duplicated unique id '%s' (%s)",
                               unique_id, type(entity).__name__)
                continue

            entity_id = getattr(entity, "entity_id", None) or \
                f"{self.domain}.{_slugify(getattr(entity, 'name', None) or unique_id or 'entity')}"
            entity_id = self._deduplicate_entity_id(entity_id)
            entity.entity_id = entity_id
            self.entities[entity_id] = entity

            # keep the registries in sync so that the web ui can count/summarize
            registry = er.async_get(self.hass)
            registry.async_get_or_create(entity_id=entity_id, unique_id=unique_id,
                                         platform=self.platform_name, domain=self.domain,
                                         name=getattr(entity, "name", None))
            device_info = getattr(entity, "device_info", None)
            if device_info:
                try:
                    dr.async_get(self.hass).async_get_or_create(
                        config_entry_id=getattr(self.config_entry, "entry_id", None),
                        **dict(device_info))
                except Exception:  # noqa: BLE001 - registry sugar must not break adding
                    LOGGER.debug("Cannot register device of %s", entity_id, exc_info=True)

            self.hass.async_create_task(self._async_finish_add(entity))

    async def _async_finish_add(self, entity) -> None:
        try:
            await entity.async_added_to_hass()
        except Exception:  # noqa: BLE001 - one entity must not stop the platform
            LOGGER.exception("async_added_to_hass of %s failed", entity.entity_id)
        entity.async_write_ha_state()

    def _deduplicate_entity_id(self, entity_id: str) -> str:
        if entity_id not in self._all_domain_entity_ids():
            return entity_id
        index = 2
        while f"{entity_id}_{index}" in self._all_domain_entity_ids():
            index += 1
        return f"{entity_id}_{index}"

    def _platforms(self) -> list["EntityPlatform"]:
        return self.hass.data.get(DATA_ENTITY_PLATFORM, {}).get(self.platform_name, [])

    def _all_domain_entities(self):
        for platform in self._platforms():
            yield from platform.entities.values()

    def _all_domain_entity_ids(self) -> set[str]:
        ids = set()
        for platform in self._platforms():
            ids.update(platform.entities.keys())
        return ids

    async def async_destroy(self) -> None:
        """Remove all entities of this platform (used on unload/reload)."""
        for entity in list(self.entities.values()):
            try:
                await entity.async_remove()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Cannot remove %s", entity.entity_id)
        self.entities.clear()


def register_platform(hass, platform: EntityPlatform) -> None:
    hass.data.setdefault(DATA_ENTITY_PLATFORM, {}) \
        .setdefault(platform.platform_name, []).append(platform)


def unregister_platform(hass, platform: EntityPlatform) -> None:
    platforms = hass.data.get(DATA_ENTITY_PLATFORM, {}).get(platform.platform_name, [])
    if platform in platforms:
        platforms.remove(platform)
