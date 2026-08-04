"""Binary sensor platform mirroring homeassistant.components.binary_sensor."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import voluptuous as vol

from ...helpers.entity import Entity, EntityDescription


class BinarySensorDeviceClass(StrEnum):
    BATTERY = "battery"
    BATTERY_CHARGING = "battery_charging"
    CO = "carbon_monoxide"
    COLD = "cold"
    CONNECTIVITY = "connectivity"
    DOOR = "door"
    GARAGE_DOOR = "garage_door"
    GAS = "gas"
    HEAT = "heat"
    LIGHT = "light"
    LOCK = "lock"
    MOISTURE = "moisture"
    MOTION = "motion"
    MOVING = "moving"
    OCCUPANCY = "occupancy"
    OPENING = "opening"
    PLUG = "plug"
    POWER = "power"
    PRESENCE = "presence"
    PROBLEM = "problem"
    RUNNING = "running"
    SAFETY = "safety"
    SMOKE = "smoke"
    SOUND = "sound"
    TAMPER = "tamper"
    UPDATE = "update"
    VIBRATION = "vibration"
    WINDOW = "window"


DEVICE_CLASSES_SCHEMA = vol.All(vol.Lower, vol.Coerce(BinarySensorDeviceClass))


@dataclass(frozen=False, kw_only=True)
class BinarySensorEntityDescription(EntityDescription):
    pass


class BinarySensorEntity(Entity):
    @property
    def is_on(self):
        return getattr(self, "_attr_is_on", None)

    @property
    def state(self):
        is_on = self.is_on
        if is_on is None:
            return None
        return "on" if is_on else "off"
