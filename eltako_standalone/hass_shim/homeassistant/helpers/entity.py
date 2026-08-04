"""Entity base class mirroring homeassistant.helpers.entity.

Implements the `_attr_*` fallback pattern of Home Assistant for exactly the
attributes the Eltako integration uses. The computed state is written into
hass.states, from where the CLI and the web ui read it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger("homeassistant.shim.entity")

STATE_UNKNOWN = "unknown"
STATE_UNAVAILABLE = "unavailable"


@dataclass(frozen=False, kw_only=True)
class EntityDescription:
    key: str
    device_class: Any = None
    entity_category: Any = None
    entity_registry_enabled_default: bool = True
    has_entity_name: bool = False
    icon: str | None = None
    name: str | None = None
    translation_key: str | None = None
    unit_of_measurement: str | None = None


class DeviceInfo(dict):
    """Device registry description, accepted as keyword arguments like in HA."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e


class Entity:
    entity_description: EntityDescription | None = None
    hass = None
    platform = None
    entity_id: str | None = None

    _attr_should_poll: bool = False
    _attr_has_entity_name: bool = False

    def __init__(self):
        pass

    # ------------------------------------------------------- _attr_* pattern
    def _attr(self, name: str, default=None):
        value = getattr(self, f"_attr_{name}", None)
        if value is not None:
            return value
        if self.entity_description is not None:
            return getattr(self.entity_description, name, default) or default
        return default

    @property
    def unique_id(self) -> str | None:
        return getattr(self, "_attr_unique_id", None)

    @property
    def name(self) -> str | None:
        name = self._attr("name")
        if name is not None:
            return name
        return getattr(self, "_attr_dev_name", None) or self.entity_id

    @name.setter
    def name(self, value) -> None:
        # In HA `name` is a cached_property, so entities can simply assign it
        # (e.g. select.py does `self.name = "Repeater Mode"`). Mirror that.
        self._attr_name = value

    @property
    def available(self) -> bool:
        return getattr(self, "_attr_available", True)

    @property
    def device_class(self):
        return self._attr("device_class")

    @property
    def icon(self) -> str | None:
        return self._attr("icon")

    @property
    def entity_category(self):
        return self._attr("entity_category")

    @property
    def supported_features(self):
        return getattr(self, "_attr_supported_features", None)

    @property
    def extra_state_attributes(self) -> dict | None:
        return getattr(self, "_attr_extra_state_attributes", None)

    @property
    def device_info(self) -> DeviceInfo | None:
        return getattr(self, "_attr_device_info", None)

    @property
    def state(self):
        """Overridden by the component base classes (LightEntity, SensorEntity, ...)."""
        return getattr(self, "_attr_state", None)

    @property
    def capability_attributes(self) -> dict | None:
        return None

    @property
    def state_attributes(self) -> dict | None:
        return None

    # ------------------------------------------------------------- lifecycle
    async def async_added_to_hass(self) -> None:
        """Overridden by entities; the platform calls it after adding."""

    async def async_will_remove_from_hass(self) -> None:
        """Overridden by entities."""

    def async_on_remove(self, func) -> None:
        if not hasattr(self, "_on_remove"):
            self._on_remove = []
        self._on_remove.append(func)

    async def async_remove(self) -> None:
        await self.async_will_remove_from_hass()
        for func in getattr(self, "_on_remove", []):
            try:
                func()
            except Exception:  # noqa: BLE001
                LOGGER.exception("on_remove callback of %s failed", self.entity_id)
        self._on_remove = []
        if self.hass is not None and self.entity_id:
            self.hass.states.async_remove(self.entity_id)

    # ----------------------------------------------------------- state write
    def _stringify_state(self) -> str:
        if not self.available:
            return STATE_UNAVAILABLE
        state = self.state
        if state is None:
            return STATE_UNKNOWN
        if isinstance(state, bool):
            return "on" if state else "off"
        return str(state)

    def _collect_attributes(self) -> dict:
        attributes: dict = {}
        for source in (self.capability_attributes, self.state_attributes,
                       self.extra_state_attributes):
            if source:
                attributes.update(source)
        if self.name:
            attributes["friendly_name"] = str(self.name)
        device_class = self.device_class
        if device_class is not None:
            attributes["device_class"] = str(device_class)
        if self.icon:
            attributes["icon"] = self.icon
        supported = self.supported_features
        if supported is not None:
            attributes["supported_features"] = int(supported)
        return attributes

    def async_write_ha_state(self) -> None:
        if self.hass is None or self.entity_id is None:
            return
        try:
            self.hass.states.async_set(self.entity_id, self._stringify_state(),
                                       self._collect_attributes())
        except Exception:  # noqa: BLE001 - a broken attribute must not kill the caller
            LOGGER.exception("Cannot write state of %s", self.entity_id)

    def schedule_update_ha_state(self, force_refresh: bool = False) -> None:
        """Thread-safe state write (the integration calls this from bus callbacks)."""
        if self.hass is None:
            return
        self.hass.run_in_loop(self.async_write_ha_state)

    def async_schedule_update_ha_state(self, force_refresh: bool = False) -> None:
        self.schedule_update_ha_state(force_refresh)

    async def async_update_ha_state(self, force_refresh: bool = False) -> None:
        self.async_write_ha_state()
