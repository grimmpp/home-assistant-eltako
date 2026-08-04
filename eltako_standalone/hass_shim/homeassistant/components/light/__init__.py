"""Light platform mirroring homeassistant.components.light."""

from __future__ import annotations

from enum import IntFlag, StrEnum

from ...helpers.entity import Entity

ATTR_BRIGHTNESS = "brightness"
ATTR_COLOR_MODE = "color_mode"
ATTR_SUPPORTED_COLOR_MODES = "supported_color_modes"


class ColorMode(StrEnum):
    UNKNOWN = "unknown"
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    HS = "hs"
    XY = "xy"
    RGB = "rgb"
    RGBW = "rgbw"
    RGBWW = "rgbww"
    WHITE = "white"


class LightEntityFeature(IntFlag):
    EFFECT = 4
    FLASH = 8
    TRANSITION = 32


class LightEntity(Entity):
    @property
    def is_on(self):
        return getattr(self, "_attr_is_on", None)

    @property
    def brightness(self):
        return getattr(self, "_attr_brightness", None)

    @property
    def color_mode(self):
        return getattr(self, "_attr_color_mode", None)

    @property
    def supported_color_modes(self):
        return getattr(self, "_attr_supported_color_modes", None)

    @property
    def state(self):
        is_on = self.is_on
        if is_on is None:
            return None
        return "on" if is_on else "off"

    @property
    def capability_attributes(self) -> dict | None:
        modes = self.supported_color_modes
        if modes:
            return {ATTR_SUPPORTED_COLOR_MODES: [str(mode) for mode in modes]}
        return None

    @property
    def state_attributes(self) -> dict | None:
        if not self.is_on:
            return None
        attributes = {}
        if self.brightness is not None:
            attributes[ATTR_BRIGHTNESS] = self.brightness
        if self.color_mode is not None:
            attributes[ATTR_COLOR_MODE] = str(self.color_mode)
        return attributes or None
