"""Switch platform mirroring homeassistant.components.switch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ...helpers.entity import Entity, EntityDescription


class SwitchDeviceClass(StrEnum):
    OUTLET = "outlet"
    SWITCH = "switch"


@dataclass(frozen=False, kw_only=True)
class SwitchEntityDescription(EntityDescription):
    pass


class SwitchEntity(Entity):
    @property
    def is_on(self):
        return getattr(self, "_attr_is_on", None)

    @property
    def state(self):
        is_on = self.is_on
        if is_on is None:
            return None
        return "on" if is_on else "off"
