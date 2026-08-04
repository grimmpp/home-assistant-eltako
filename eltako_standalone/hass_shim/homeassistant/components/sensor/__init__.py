"""Sensor platform mirroring homeassistant.components.sensor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from ...helpers.entity import Entity, EntityDescription


class SensorDeviceClass(StrEnum):
    APPARENT_POWER = "apparent_power"
    AQI = "aqi"
    ATMOSPHERIC_PRESSURE = "atmospheric_pressure"
    BATTERY = "battery"
    CO = "carbon_monoxide"
    CO2 = "carbon_dioxide"
    CURRENT = "current"
    DATE = "date"
    DISTANCE = "distance"
    DURATION = "duration"
    ENERGY = "energy"
    ENUM = "enum"
    FREQUENCY = "frequency"
    GAS = "gas"
    HUMIDITY = "humidity"
    ILLUMINANCE = "illuminance"
    IRRADIANCE = "irradiance"
    MOISTURE = "moisture"
    MONETARY = "monetary"
    NITROGEN_DIOXIDE = "nitrogen_dioxide"
    NITROGEN_MONOXIDE = "nitrogen_monoxide"
    NITROUS_OXIDE = "nitrous_oxide"
    OZONE = "ozone"
    PH = "ph"
    PM1 = "pm1"
    PM10 = "pm10"
    PM25 = "pm25"
    POWER = "power"
    POWER_FACTOR = "power_factor"
    PRECIPITATION = "precipitation"
    PRECIPITATION_INTENSITY = "precipitation_intensity"
    PRESSURE = "pressure"
    REACTIVE_POWER = "reactive_power"
    SIGNAL_STRENGTH = "signal_strength"
    SOUND_PRESSURE = "sound_pressure"
    SPEED = "speed"
    SULPHUR_DIOXIDE = "sulphur_dioxide"
    TEMPERATURE = "temperature"
    TIMESTAMP = "timestamp"
    VOLATILE_ORGANIC_COMPOUNDS = "volatile_organic_compounds"
    VOLATILE_ORGANIC_COMPOUNDS_PARTS = "volatile_organic_compounds_parts"
    VOLTAGE = "voltage"
    VOLUME = "volume"
    VOLUME_FLOW_RATE = "volume_flow_rate"
    VOLUME_STORAGE = "volume_storage"
    WATER = "water"
    WEIGHT = "weight"
    WIND_SPEED = "wind_speed"


class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


@dataclass(frozen=False, kw_only=True)
class SensorEntityDescription(EntityDescription):
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | str | None = None
    suggested_display_precision: int | None = None
    suggested_unit_of_measurement: str | None = None


class SensorEntity(Entity):
    entity_description: SensorEntityDescription | None = None

    @property
    def native_value(self):
        return getattr(self, "_attr_native_value", None)

    @property
    def native_unit_of_measurement(self):
        value = getattr(self, "_attr_native_unit_of_measurement", None)
        if value is not None:
            return value
        if self.entity_description is not None:
            return self.entity_description.native_unit_of_measurement
        return None

    @property
    def state_class(self):
        value = getattr(self, "_attr_state_class", None)
        if value is not None:
            return value
        if self.entity_description is not None:
            return self.entity_description.state_class
        return None

    @property
    def suggested_display_precision(self):
        value = getattr(self, "_attr_suggested_display_precision", None)
        if value is not None:
            return value
        if self.entity_description is not None:
            return self.entity_description.suggested_display_precision
        return None

    @property
    def state(self):
        value = self.native_value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        precision = self.suggested_display_precision
        if precision is not None and isinstance(value, float):
            return round(value, precision)
        return value

    @property
    def state_attributes(self) -> dict | None:
        attributes = {}
        unit = self.native_unit_of_measurement
        if unit is not None:
            attributes["unit_of_measurement"] = str(unit)
        state_class = self.state_class
        if state_class is not None:
            attributes["state_class"] = str(state_class)
        return attributes or None
