"""Select platform mirroring homeassistant.components.select."""

from __future__ import annotations

from dataclasses import dataclass

from ...helpers.entity import Entity, EntityDescription

ATTR_OPTIONS = "options"
ATTR_OPTION = "option"


@dataclass(frozen=False, kw_only=True)
class SelectEntityDescription(EntityDescription):
    options: list[str] | None = None


class SelectEntity(Entity):
    @property
    def options(self) -> list[str]:
        value = getattr(self, "_attr_options", None)
        if value is not None:
            return value
        if self.entity_description is not None and getattr(self.entity_description, "options", None):
            return self.entity_description.options
        return []

    @property
    def current_option(self) -> str | None:
        return getattr(self, "_attr_current_option", None)

    @property
    def state(self):
        return self.current_option

    @property
    def capability_attributes(self) -> dict | None:
        return {ATTR_OPTIONS: list(self.options)}

    def select_option(self, option: str) -> None:
        raise NotImplementedError

    async def async_select_option(self, option: str) -> None:
        await self.hass.async_add_executor_job(self.select_option, option)
