"""Climate platform mirroring homeassistant.components.climate."""

from __future__ import annotations

from enum import IntFlag, StrEnum

from ...helpers.entity import Entity

ATTR_HVAC_MODE = "hvac_mode"
ATTR_TARGET_TEMP_HIGH = "target_temp_high"
ATTR_TARGET_TEMP_LOW = "target_temp_low"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_PRESET_MODE = "preset_mode"

PRESET_NONE = "none"
PRESET_ECO = "eco"
PRESET_AWAY = "away"
PRESET_BOOST = "boost"
PRESET_COMFORT = "comfort"
PRESET_HOME = "home"
PRESET_SLEEP = "sleep"
PRESET_ACTIVITY = "activity"


class HVACMode(StrEnum):
    OFF = "off"
    HEAT = "heat"
    COOL = "cool"
    HEAT_COOL = "heat_cool"
    AUTO = "auto"
    DRY = "dry"
    FAN_ONLY = "fan_only"


class HVACAction(StrEnum):
    COOLING = "cooling"
    DEFROSTING = "defrosting"
    DRYING = "drying"
    FAN = "fan"
    HEATING = "heating"
    IDLE = "idle"
    OFF = "off"
    PREHEATING = "preheating"


class ClimateEntityFeature(IntFlag):
    TARGET_TEMPERATURE = 1
    TARGET_TEMPERATURE_RANGE = 2
    TARGET_HUMIDITY = 4
    FAN_MODE = 8
    PRESET_MODE = 16
    SWING_MODE = 32
    AUX_HEAT = 64
    TURN_OFF = 128
    TURN_ON = 256


class ClimateEntity(Entity):
    _enable_turn_on_off_backwards_compatibility = True

    @property
    def hvac_mode(self):
        return getattr(self, "_attr_hvac_mode", None)

    @property
    def hvac_modes(self):
        return getattr(self, "_attr_hvac_modes", [])

    @property
    def hvac_action(self):
        return getattr(self, "_attr_hvac_action", None)

    @property
    def current_temperature(self):
        return getattr(self, "_attr_current_temperature", None)

    @property
    def target_temperature(self):
        return getattr(self, "_attr_target_temperature", None)

    @property
    def temperature_unit(self):
        return getattr(self, "_attr_temperature_unit", "°C")

    @property
    def min_temp(self):
        return getattr(self, "_attr_min_temp", 7)

    @property
    def max_temp(self):
        return getattr(self, "_attr_max_temp", 35)

    @property
    def preset_mode(self):
        return getattr(self, "_attr_preset_mode", None)

    @property
    def preset_modes(self):
        return getattr(self, "_attr_preset_modes", None)

    @property
    def state(self):
        mode = self.hvac_mode
        return str(mode) if mode is not None else None

    @property
    def capability_attributes(self) -> dict | None:
        return {
            "hvac_modes": [str(mode) for mode in self.hvac_modes],
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "preset_modes": self.preset_modes,
        }

    @property
    def state_attributes(self) -> dict | None:
        attributes = {
            "current_temperature": self.current_temperature,
            "temperature": self.target_temperature,
            "temperature_unit": str(self.temperature_unit),
        }
        if self.hvac_action is not None:
            attributes["hvac_action"] = str(self.hvac_action)
        if self.preset_mode is not None:
            attributes["preset_mode"] = str(self.preset_mode)
        return attributes
