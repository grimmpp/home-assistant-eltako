"""Constants mirroring homeassistant.const (only what the Eltako integration uses)."""

from enum import StrEnum

__version__ = "standalone"

# --- config keys -------------------------------------------------------------
CONF_ID = "id"
CONF_NAME = "name"
CONF_DEVICE = "device"
CONF_DEVICES = "devices"
CONF_DEVICE_CLASS = "device_class"
CONF_TEMPERATURE_UNIT = "temperature_unit"
CONF_LANGUAGE = "language"
CONF_MAC = "mac"

# --- events ------------------------------------------------------------------
EVENT_HOMEASSISTANT_START = "homeassistant_start"
EVENT_HOMEASSISTANT_STARTED = "homeassistant_started"
EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
EVENT_STATE_CHANGED = "state_changed"

# --- states ------------------------------------------------------------------
STATE_ON = "on"
STATE_OFF = "off"
STATE_OPEN = "open"
STATE_OPENING = "opening"
STATE_CLOSED = "closed"
STATE_CLOSING = "closing"
STATE_UNKNOWN = "unknown"
STATE_UNAVAILABLE = "unavailable"

# --- units -------------------------------------------------------------------
PERCENTAGE = "%"
LIGHT_LUX = "lx"
ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"
ATTR_FRIENDLY_NAME = "friendly_name"
ATTR_DEVICE_CLASS = "device_class"
ATTR_ICON = "icon"
ATTR_SUPPORTED_FEATURES = "supported_features"
ATTR_TEMPERATURE = "temperature"


class UnitOfTemperature(StrEnum):
    CELSIUS = "°C"
    FAHRENHEIT = "°F"
    KELVIN = "K"


class UnitOfPower(StrEnum):
    WATT = "W"
    KILO_WATT = "kW"
    BTU_PER_HOUR = "BTU/h"


class UnitOfEnergy(StrEnum):
    KILO_WATT_HOUR = "kWh"
    MEGA_WATT_HOUR = "MWh"
    WATT_HOUR = "Wh"


class UnitOfSpeed(StrEnum):
    METERS_PER_SECOND = "m/s"
    KILOMETERS_PER_HOUR = "km/h"
    MILES_PER_HOUR = "mph"
    KNOTS = "kn"
    FEET_PER_SECOND = "ft/s"


class UnitOfVolume(StrEnum):
    CUBIC_METERS = "m³"
    CUBIC_FEET = "ft³"
    LITERS = "L"
    MILLILITERS = "mL"
    GALLONS = "gal"


class UnitOfVolumeFlowRate(StrEnum):
    CUBIC_METERS_PER_HOUR = "m³/h"
    CUBIC_FEET_PER_MINUTE = "ft³/min"
    LITERS_PER_MINUTE = "L/min"
    GALLONS_PER_MINUTE = "gal/min"


class UnitOfElectricPotential(StrEnum):
    MILLIVOLT = "mV"
    VOLT = "V"


class Platform(StrEnum):
    """Available entity platforms (subset relevant for Eltako)."""

    AIR_QUALITY = "air_quality"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    CLIMATE = "climate"
    COVER = "cover"
    DATE = "date"
    DATETIME = "datetime"
    EVENT = "event"
    FAN = "fan"
    LIGHT = "light"
    LOCK = "lock"
    NUMBER = "number"
    SCENE = "scene"
    SELECT = "select"
    SENSOR = "sensor"
    SIREN = "siren"
    SWITCH = "switch"
    TEXT = "text"
    TIME = "time"
    UPDATE = "update"
    VACUUM = "vacuum"
    VALVE = "valve"
    WATER_HEATER = "water_heater"
    WEATHER = "weather"
