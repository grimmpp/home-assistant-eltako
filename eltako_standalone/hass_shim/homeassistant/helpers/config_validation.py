"""Validators mirroring homeassistant.helpers.config_validation (cv)."""

from __future__ import annotations

import re
from numbers import Number as _NumberType

import voluptuous as vol


def string(value) -> str:
    if value is None:
        raise vol.Invalid("string value is None")
    if isinstance(value, (list, dict)):
        raise vol.Invalid("value should be a string")
    return str(value)


def boolean(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.lower().strip()
        if value in ("1", "true", "yes", "on", "enable"):
            return True
        if value in ("0", "false", "no", "off", "disable"):
            return False
    elif isinstance(value, _NumberType):
        return value != 0
    raise vol.Invalid(f"invalid boolean value {value}")


def ensure_list(value) -> list:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def matches_regex(regex: str):
    compiled = re.compile(regex)

    def validator(value) -> str:
        if not isinstance(value, str):
            raise vol.Invalid(f"not a string value: {value}")
        if not compiled.match(value):
            raise vol.Invalid(f"value {value} does not match regular expression {regex}")
        return value
    return validator


def Number(value):
    if isinstance(value, bool) or not isinstance(value, _NumberType):
        raise vol.Invalid(f"invalid number {value}")
    return value


def byte(value) -> int:
    return vol.All(vol.Coerce(int), vol.Range(min=0, max=255))(value)


positive_int = vol.All(vol.Coerce(int), vol.Range(min=0))
positive_float = vol.All(vol.Coerce(float), vol.Range(min=0))
