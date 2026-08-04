"""Button platform mirroring homeassistant.components.button."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ...helpers.entity import Entity, EntityDescription


class ButtonDeviceClass(StrEnum):
    IDENTIFY = "identify"
    RESTART = "restart"
    UPDATE = "update"


@dataclass(frozen=False, kw_only=True)
class ButtonEntityDescription(EntityDescription):
    pass


class ButtonEntity(Entity):
    @property
    def state(self):
        # buttons in HA expose the timestamp of the last press
        return getattr(self, "_attr_last_pressed", None)

    def press(self) -> None:
        raise NotImplementedError

    async def async_press(self) -> None:
        await self.hass.async_add_executor_job(self.press)
