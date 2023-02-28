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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, DOMAIN, MANUFACTURER

CONF_EEP_SUPPORTED = ["A5-13-01", "F6-10-00", "A5-12-01", "A5-12-02", "A5-12-03"]
CONF_METER_TARIFFS = "meter_tariffs"
CONF_METER_TARIFFS_DEFAULT = [1]

DEFAULT_DEVICE_NAME_WINDOW_HANDLE = "Window handle"
DEFAULT_DEVICE_NAME_WEATHER_STATION = "Weather station"
DEFAULT_DEVICE_NAME_ELECTRICITY_METER = "Electricity meter"
DEFAULT_DEVICE_NAME_GAS_METER = "Gas meter"
DEFAULT_DEVICE_NAME_WATER_METER = "Water meter"

SENSOR_TYPE_ELECTRICITY_CUMULATIVE = "electricity_cumulative"
SENSOR_TYPE_ELECTRICITY_CURRENT = "electricity_current"
SENSOR_TYPE_GAS_CUMULATIVE = "gas_cumulative"
SENSOR_TYPE_GAS_CURRENT = "gas_current"
SENSOR_TYPE_WATER_CUMULATIVE = "water_cumulative"
SENSOR_TYPE_WATER_CURRENT = "water_current"
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
class EltakoSensorEntityDescription(SensorEntityDescription):
    """Describes Eltako sensor entity."""


SENSOR_DESC_ELECTRICITY_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_ELECTRICITY_CUMULATIVE,
    name="Reading",
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    icon="mdi:lightning-bolt",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
)

SENSOR_DESC_ELECTRICITY_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_ELECTRICITY_CURRENT,
    name="Power",
    native_unit_of_measurement=UnitOfPower.WATT,
    icon="mdi:lightning-bolt",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_GAS_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_GAS_CUMULATIVE,
    name="Reading",
    native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    icon="mdi:fire",
    device_class=SensorDeviceClass.GAS,
    state_class=SensorStateClass.TOTAL_INCREASING,
)

SENSOR_DESC_GAS_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_GAS_CURRENT,
    name="Flow rate",
    native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    icon="mdi:fire",
    device_class=SensorDeviceClass.GAS,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WATER_CUMULATIVE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WATER_CUMULATIVE,
    name="Reading",
    native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
    icon="mdi:water",
    device_class=SensorDeviceClass.WATER,
    state_class=SensorStateClass.TOTAL_INCREASING,
)

SENSOR_DESC_WATER_CURRENT = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WATER_CURRENT,
    name="Flow rate",
    native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    icon="mdi:water",
    device_class=SensorDeviceClass.WATER,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WINDOWHANDLE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WINDOWHANDLE,
    name="Window handle",
    icon="mdi:window-open-variant",
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN,
    name="Illuminance (dawn)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunset",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_WIND_SPEED = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_WIND_SPEED,
    name="Wind speed",
    native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
    icon="mdi:windsock",
    device_class=SensorDeviceClass.WIND_SPEED,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_RAIN = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_RAIN,
    name="Rain",
    native_unit_of_measurement="",
    icon="mdi:weather-pouring",
    device_class="rain",
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST,
    name="Illuminance (west)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunny",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL,
    name="Illuminance (central)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunny",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST,
    name="Illuminance (east)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunny",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
        vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
        vol.Optional(CONF_NAME, default=''): cv.string,
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
        if dev_name == '':
            dev_name = DEFAULT_DEVICE_NAME_WEATHER_STATION
            
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_TEMPERATURE))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_WIND_SPEED))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_RAIN))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL))
        entities.append(EltakoWeatherStation(dev_id, dev_name, dev_eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST))
        
    elif dev_eep in ["F6-10-00"]:
        if dev_name == '':
            dev_name = DEFAULT_DEVICE_NAME_WINDOW_HANDLE
        
        entities.append(EltakoWindowHandle(dev_id, dev_name, dev_eep, SENSOR_DESC_WINDOWHANDLE))
        
    elif dev_eep in ["A5-12-01"]:
        if dev_name == '':
            dev_name = DEFAULT_DEVICE_NAME_ELECTRICITY_METER
            
        for tariff in meter_tariffs:
            entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_ELECTRICITY_CUMULATIVE, tariff=(tariff - 1)))
        entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_ELECTRICITY_CURRENT, tariff=0))

    elif dev_eep in ["A5-12-02"]:
        if dev_name == '':
            dev_name = DEFAULT_DEVICE_NAME_GAS_METER
            
        for tariff in meter_tariffs:
            entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_GAS_CUMULATIVE, tariff=(tariff - 1)))
            entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_GAS_CURRENT, tariff=(tariff - 1)))

    elif dev_eep in ["A5-12-03"]:
        if dev_name == '':
            dev_name = DEFAULT_DEVICE_NAME_WATER_METER
            
        for tariff in meter_tariffs:
            entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_WATER_CUMULATIVE, tariff=(tariff - 1)))
            entities.append(EltakoMeterSensor(dev_id, dev_name, dev_eep, SENSOR_DESC_WATER_CURRENT, tariff=(tariff - 1)))

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
    def __init__(self, dev_id, dev_name, dev_eep, description: EltakoSensorEntityDescription, *, tariff) -> None:
        """Initialize the Eltako meter sensor device."""
        super().__init__(dev_id, dev_name, dev_eep, description)
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{description.key}_{tariff}"
        self.entity_id = f"sensor.{self.unique_id}"

        self._tariff = tariff
        
    @property
    def name(self):
        """Return the default name for the sensor."""
        return f"{self.entity_description.name} (Tariff {self._tariff + 1})"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.unique_id)
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self.dev_eep,
        )

    def value_changed(self, msg):
        """Update the internal state of the sensor.
        For cumulative values, we alway respect the channel.
        For current values, we respect the channel just for gas and water.
        """
        if msg.org != 0x07:
            return
        
        tariff = msg.data[3] >> 4
        cumulative = not (msg.data[3] & 0x04)
        value = (msg.data[0] << 16) + (msg.data[1] << 8) + msg.data[2]
        divisor = 10 ** (msg.data[3] & 0x03)
        calculatedValue = value / divisor
        
        if cumulative and self._tariff == tariff and (
            self.entity_description.key == SENSOR_TYPE_ELECTRICITY_CUMULATIVE or
            self.entity_description.key == SENSOR_TYPE_GAS_CUMULATIVE or
            self.entity_description.key == SENSOR_TYPE_WATER_CUMULATIVE):
            self._attr_native_value = round(calculatedValue, 2)
            self.schedule_update_ha_state()
        elif (not cumulative) and msg.data[3] != 0x8f and self.entity_description.key == SENSOR_TYPE_ELECTRICITY_CURRENT:
            self._attr_native_value = round(calculatedValue, 2)
            self.schedule_update_ha_state()
        elif (not cumulative) and self._tariff == tariff and (
            self.entity_description.key == SENSOR_TYPE_GAS_CURRENT or
            self.entity_description.key == SENSOR_TYPE_WATER_CURRENT):
            # l/s -> m3/h
            self._attr_native_value = round(calculatedValue * 3.6, 2)
            self.schedule_update_ha_state()


class EltakoWindowHandle(EltakoSensor):
    """Representation of an Eltako window handle device.

    EEPs (EnOcean Equipment Profiles):
    - F6-10-00 (Mechanical handle / Hoppe AG)
    """

    def __init__(self, dev_id, dev_name, dev_eep, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako window handle sensor device."""
        super().__init__(dev_id, dev_name, dev_eep, description)
        
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{description.key}"
        self.entity_id = f"sensor.{self.unique_id}"

    @property
    def name(self):
        """Return the default name for the sensor."""
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.unique_id)
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self.dev_eep,
        )

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

    def __init__(self, dev_id, dev_name, dev_eep, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako weather station device."""
        super().__init__(dev_id, dev_name, dev_eep, description)
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{description.key}"
        self.entity_id = f"sensor.{self.unique_id}"

    @property
    def name(self):
        """Return the default name for the sensor."""
        return self.entity_description.name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                (DOMAIN, self.unique_id)
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self.dev_eep,
        )

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        
        if msg.org != 0x07 or msg.data == bytes((0, 0, 0xff, 0x1a)):
            return

        if self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN:
            if msg.data[3] >> 4 != 1:
                return
            
            self._attr_native_value = round(999 * msg.data[0] / 255)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_TEMPERATURE:
            if msg.data[3] >> 4 != 1:
                return
            
            self._attr_native_value = round(-40 + 120 * msg.data[1] / 255, 2)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_WIND_SPEED:
            if msg.data[3] >> 4 != 1:
                return
            
            self._attr_native_value = round(70 * msg.data[2] / 255, 2)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_RAIN:
            if msg.data[3] >> 4 != 1:
                return
            
            self._attr_native_value = bool(msg.data[3] & 0x02)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST:
            if msg.data[3] >> 4 != 2:
                return
            
            self._attr_native_value = round(150000 * msg.data[0] / 255)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL:
            if msg.data[3] >> 4 != 2:
                return
            
            self._attr_native_value = round(150000 * msg.data[1] / 255)
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST:
            if msg.data[3] >> 4 != 2:
                return
            
            self._attr_native_value = round(150000 * msg.data[2] / 255)

        self.schedule_update_ha_state()
