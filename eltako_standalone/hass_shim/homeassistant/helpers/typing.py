"""Typing helpers mirroring homeassistant.helpers.typing."""

from typing import Any

ConfigType = dict[str, Any]
DiscoveryInfoType = dict[str, Any]
StateType = str | int | float | None
