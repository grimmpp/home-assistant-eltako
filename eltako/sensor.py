"""Support for Eltako sensors."""
from __future__ import annotations

from enum import Enum

from collections.abc import Callable
from dataclasses import dataclass

from eltakobus.util import combine_hex
from eltakobus.util import AddressExpression
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_ID,
    CONF_NAME,
    PERCENTAGE,
    STATE_CLOSED,
    STATE_OPEN,
    LIGHT_LUX,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfSpeed,
    UnitOfEnergy,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP

CONF_EEP_SUPPORTED = ["A5-13-01", "F6-10-00", "A5-12-01", "A5-12-02", "A5-12-03"]
CONF_METER_TARIFFS = "meter_tariffs"
CONF_METER_TARIFFS_DEFAULT = [1]

DEFAULT_NAME = "Eltako sensor"

SENSOR_TYPE_ELECTRICITY_CUMULATIVE = "electricity_cumulative"
SENSOR_TYPE_ELECTRICITY_CURRENT = "electricity_current"
SENSOR_TYPE_GAS_CUMULATIVE = "gas_cumulative"
SENSOR_TYPE_GASY_CURRENT = "gas_current"
SENSOR_TYPE_WATER_CUMULATIVE = "water_cumulative"
SENSOR_TYPE_WATERY_CURRENT = "water_current"
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_HUMIDITY = "humidity"
SENSOR_TYPE_WINDOWHANDLE = "windowhandle"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN = "weather_station_illuminance_dawn"
SENSOR_TYPE_WEATHER_STATION_TEMPERATURE = "weather_station_temperature"
SENSOR_TYPE_WEATHER_STATION_WIND_SPEED = "weather_station_wind_speed"
SENSOR_TYPE_WEATHER_STATION_RAIN = "weather_station_rain"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST = "weather_station_illuminance_west"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL = "weather_station_illuminance_central"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST = "weather_station_illuminance_east"


@dataclass
class EltakoSensorEntityDescriptionMixin:
    """Mixin for required keys."""

    unique_id: Callable[[list[int]], str | None]


@dataclass
class EltakoSensorEntityDescription(
    SensorEntityDescription, EltakoSensorEntityDescriptionMixin
):
    """Describes Eltako sensor entity."""


SENSOR_DESC_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_TEMPERATURE}",
)

SENSOR_DESC_HUMIDITY = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_HUMIDITY,
    name="Humidity",
    native_unit_of_measurement=PERCENTAGE,
    icon="mdi:water-percent",
    device_class=SensorDeviceClass.HUMIDITY,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_HUMIDITY}",
)

SENSOR_DESC_ELECTRICITY_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_ELECTRICITY_CUMULATIVE,
    name="Electricity",
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    icon="mdi:lightning-bolt",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_ELECTRICITY_CUMULATIVE}",
)

SENSOR_DESC_ELECTRICITY_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_ELECTRICITY_CURRENT,
    name="Electricity",
    native_unit_of_measurement=UnitOfPower.WATT,
    icon="mdi:lightning-bolt",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_ELECTRICITY_CURRENT}",
)

SENSOR_DESC_GAS_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_GAS_CUMULATIVE,
    name="Gas",
    native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    icon="mdi:fire",
    device_class=SensorDeviceClass.GAS,
    state_class=SensorStateClass.TOTAL_INCREASING,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_GAS_CUMULATIVE}",
)

SENSOR_DESC_GAS_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_GAS_CURRENT,
    name="Gas",
    native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    icon="mdi:fire",
    device_class=SensorDeviceClass.GAS,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_GAS_CURRENT}",
)

SENSOR_DESC_WATER_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WATER_CUMULATIVE,
    name="Water",
    native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    icon="mdi:water",
    device_class=SensorDeviceClass.WATER,
    state_class=SensorStateClass.TOTAL_INCREASING,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WATER_CUMULATIVE}",
)

SENSOR_DESC_WATER_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WATER_CURRENT,
    name="Water",
    native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    icon="mdi:water",
    device_class=SensorDeviceClass.WATER,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WATER_CURRENT}",
)

SENSOR_DESC_WINDOWHANDLE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WINDOWHANDLE,
    name="Window handle",
    icon="mdi:window-open-variant",
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WINDOWHANDLE}",
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN,
    name="Illuminance (dawn)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunset",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN}",
)

SENSOR_DESC_WEATHER_STATION_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_TEMPERATURE}",
)

SENSOR_DESC_WEATHER_STATION_WIND_SPEED = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_WIND_SPEED,
    name="Wind speed",
    native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
    icon="mdi:windsock",
    device_class=SensorDeviceClass.WIND_SPEED,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_WIND_SPEED}",
)

SENSOR_DESC_WEATHER_STATION_RAIN = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_RAIN,
    name="Rain",
    native_unit_of_measurement="",
    icon="mdi:weather-pouring",
    device_class="rain",
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_RAIN}",
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST,
    name="Illuminance (dawn)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunset",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST}",
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL,
    name="Illuminance (dawn)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunset",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL}",
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST,
    name="Illuminance (dawn)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunset",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address().hex()}-{SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST}",
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
        vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_METER_TARIFFS, default=CONF_METER_TARIFFS_DEFAULT): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=16))]),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up an Eltako sensor device."""
    dev_id = AddressExpression.parse(config.get(CONF_ID))
    dev_name = config[CONF_NAME]
    dev_eep = config.get(CONF_EEP)
    meter_tariffs = config.get(CONF_METER_TARIFFS)

    entities: list[EltakoSensor] = []
    
    if dev_eep in ["A5-13-01"]:
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_TEMPERATURE)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_WIND_SPEED)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_RAIN)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL)]
        entities = [EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST)]
        
    elif dev_eep in ["F6-10-00"]:
        entities = [EltakoWindowHandle(dev_id, dev_name, dev_eep, SENSOR_DESC_WINDOWHANDLE)]
        
    elif dev_eep in ["A5-12-01"]:
        for tariff in meter_tariffs:
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_ELECTRICITY_CUMULATIVE, tariff - 1)]
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_ELECTRICITY_CURRENT, tariff - 1)]

    elif dev_eep in ["A5-12-02"]:
        for tariff in meter_tariffs:
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_GAS_CUMULATIVE, tariff - 1)]
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_GAS_CURRENT, tariff - 1)]

    elif dev_eep in ["A5-12-03"]:
        for tariff in meter_tariffs:
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_WATER_CUMULATIVE, tariff - 1)]
            entities = [EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_WATER_CURRENT, tariff - 1)]

    add_entities(entities)


class EltakoSensor(EltakoEntity, RestoreEntity, SensorEntity):
    """Representation of an  Eltako sensor device such as a power meter."""

    def __init__(
        self, dev_id, dev_name, dev_eep, description: EltakoSensorEntityDescription
    ) -> None:
        """Initialize the Eltako sensor device."""
        super().__init__(dev_id, dev_name)
        self.dev_eep = dev_eep
        self.entity_description = description
        self._attr_name = f"{description.name} {dev_name}"
        self._attr_unique_id = description.unique_id(dev_id)

    async def async_added_to_hass(self) -> None:
        """Call when entity about to be added to hass."""
        # If not None, we got an initial value.
        await super().async_added_to_hass()
        if self._attr_native_value is not None:
            return

        if (state := await self.async_get_last_state()) is not None:
            self._attr_native_value = state.state

    def value_changed(self, msg):
        """Update the internal state of the sensor."""


class EltakoMeterSensor(EltakoSensor):
    """Representation of an Eltako electricity sensor.

    EEPs (EnOcean Equipment Profiles):
    - A5-12-01 (Automated Meter Reading, Electricity)
    - A5-12-02 (Automated Meter Reading, Gas)
    - A5-12-03 (Automated Meter Reading, Water)
    """
    def __init__(self, dev_id, dev_name, description: EltakoSensorEntityDescription, *, tariff) -> None:
        """Initialize the Eltako temperature sensor device."""
        super().__init__(dev_id, dev_name, description)
        self._tariff = tariff

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        if msg.org != 0x07 or self._tariff != data[3] >> 4:
            return
        
        cumulative = not (data[3] & 0x04)
        value = (data[0] << 16) + (data[1] << 8) + data[2]
        divisor = 10 ** (data[3] & 0x03)
        calculatedValue = value / divisor
        
        if cumulative and (
            self.description.key == SENSOR_TYPE_ELECTRICITY_CUMULATIVE or
            self.description.key == SENSOR_TYPE_GAS_CUMULATIVE or
            self.description.key == SENSOR_DESC_WATER_CUMULATIVE):
            self._attr_native_value = calculatedValue
        elif not cumulative and self.description.key == SENSOR_TYPE_ELECTRICITY_CURRENT
            self._attr_native_value = calculatedValue
        elif not cumulative and (
            self.description.key == SENSOR_TYPE_GAS_CURRENT or
            self.description.key == SENSOR_DESC_WATER_CURRENT):
            # l/s -> m3/h
            self._attr_native_value = calculatedValue * 3.6
            
        self.schedule_update_ha_state()


class EltakoTemperatureSensor(EltakoSensor):
    """Representation of an Eltako temperature sensor device.

    EEPs (EnOcean Equipment Profiles):
    - A5-02-01 to A5-02-1B All 8 Bit Temperature Sensors of A5-02
    - A5-10-01 to A5-10-14 (Room Operating Panels)
    - A5-04-01 (Temp. and Humidity Sensor, Range 0°C to +40°C and 0% to 100%)
    - A5-04-02 (Temp. and Humidity Sensor, Range -20°C to +60°C and 0% to 100%)
    - A5-10-10 (Temp. and Humidity Sensor and Set Point)
    - A5-10-12 (Temp. and Humidity Sensor, Set Point and Occupancy Control)
    - 10 Bit Temp. Sensors are not supported (A5-02-20, A5-02-30)

    For the following EEPs the scales must be set to "0 to 250":
    - A5-04-01
    - A5-04-02
    - A5-10-10 to A5-10-14
    """

    def __init__(
        self,
        dev_id,
        dev_name,
        description: EltakoSensorEntityDescription,
        *,
        scale_min,
        scale_max,
        range_from,
        range_to,
    ) -> None:
        """Initialize the Eltako temperature sensor device."""
        super().__init__(dev_id, dev_name, description)
        self._scale_min = scale_min
        self._scale_max = scale_max
        self.range_from = range_from
        self.range_to = range_to

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        if msg.org != 0x07:
            return

        temp_scale = self._scale_max - self._scale_min
        temp_range = self.range_to - self.range_from
        raw_val = msg.data[3]
        temperature = temp_scale / temp_range * (raw_val - self.range_from)
        temperature += self._scale_min
        self._attr_native_value = round(temperature, 1)
        self.schedule_update_ha_state()


class EltakoHumiditySensor(EltakoSensor):
    """Representation of an Eltako humidity sensor device.

    EEPs (EnOcean Equipment Profiles):
    - A5-04-01 (Temp. and Humidity Sensor, Range 0°C to +40°C and 0% to 100%)
    - A5-04-02 (Temp. and Humidity Sensor, Range -20°C to +60°C and 0% to 100%)
    - A5-10-10 to A5-10-14 (Room Operating Panels)
    """

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        if msg.org != 0x07:
            return
            
        humidity = msg.data[2] * 100 / 250
        self._attr_native_value = round(humidity, 1)
        self.schedule_update_ha_state()


class EltakoWindowHandle(EltakoSensor):
    """Representation of an Eltako window handle device.

    EEPs (EnOcean Equipment Profiles):
    - F6-10-00 (Mechanical handle / Hoppe AG)
    """

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        
        if msg.org != 0x05:
            return

        action = (msg.data[0] & 0x70) >> 4

        if action == 0x07:
            self._attr_native_value = STATE_CLOSED
        elif action in (0x04, 0x06):
            self._attr_native_value = STATE_OPEN
        elif action == 0x05:
            self._attr_native_value = "tilt"

        self.schedule_update_ha_state()


class EltakoWeatherStation(EltakoSensor):
    """Representation of an Eltako weather station.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-13-01 (Weather station)
    """

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        
        if msg.org != 0x07 or data == bytes((0, 0, 0xff, 0x1a)):
            return

        if self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN:
            if data[3] >> 4 != 1:
                return
            
            self._attr_native_value = 999 * data[0] / 255
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_TEMPERATURE:
            if data[3] >> 4 != 1:
                return
            
            self._attr_native_value = -40 + 120 * data[1] / 255
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_WIND_SPEED:
            if data[3] >> 4 != 1:
                return
            
            self._attr_native_value = 70 * data[2] / 255
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_RAIN:
            if data[3] >> 4 != 1:
                return
            
            self._attr_native_value = bool(data[3] & 0x02)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST:
            if data[3] >> 4 != 2:
                return
            
            self._attr_native_value = 150000 * data[0] / 255
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL:
            if data[3] >> 4 != 2:
                return
            
            self._attr_native_value = 150000 * data[1] / 255
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST:
            if data[3] >> 4 != 2:
                return
            
            self._attr_native_value = 150000 * data[2] / 255

        self.schedule_update_ha_state()
