"""DateTime platform mirroring homeassistant.components.datetime."""

from __future__ import annotations

from datetime import datetime

from ...helpers.entity import Entity


class DateTimeEntity(Entity):
    @property
    def native_value(self) -> datetime | None:
        return getattr(self, "_attr_native_value", None)

    @property
    def state(self):
        value = self.native_value
        return value.isoformat() if value is not None else None

    def set_value(self, value: datetime) -> None:
        raise NotImplementedError

    async def async_set_value(self, value: datetime) -> None:
        await self.hass.async_add_executor_job(self.set_value, value)
