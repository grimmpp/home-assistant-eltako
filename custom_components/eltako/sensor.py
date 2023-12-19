"""Support for Eltako sensors."""
from __future__ import annotations

from dataclasses import dataclass

from eltakobus.util import AddressExpression, b2a
from eltakobus.eep import *
from eltakobus.message import ESP2Message, Regular4BSMessage

from decimal import Decimal, InvalidOperation as DecimalInvalidOperation

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
    Platform,
    PERCENTAGE,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_BILLION,
    CONF_LANGUAGE,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import *
from .config_helpers import *
from .gateway import ESP2Gateway
from .const import *
from . import get_gateway_from_hass, get_device_config_for_gateway

DEFAULT_DEVICE_NAME_WINDOW_HANDLE = "Window handle"
DEFAULT_DEVICE_NAME_WEATHER_STATION = "Weather station"
DEFAULT_DEVICE_NAME_ELECTRICITY_METER = "Electricity meter"
DEFAULT_DEVICE_NAME_GAS_METER = "Gas meter"
DEFAULT_DEVICE_NAME_WATER_METER = "Water meter"
DEFAULT_DEVICE_NAME_HYGROSTAT = "Hygrostat"
DEFAULT_DEVICE_NAME_THERMOMETER = "Thermometer"
DEFAULT_DEVICE_NAME_AIR_QUAILTY_SENSOR = "Air Quality Sensor"

SENSOR_TYPE_ELECTRICITY_CUMULATIVE = "electricity_cumulative"
SENSOR_TYPE_ELECTRICITY_CURRENT = "electricity_current"
SENSOR_TYPE_GAS_CUMULATIVE = "gas_cumulative"
SENSOR_TYPE_GAS_CURRENT = "gas_current"
SENSOR_TYPE_WATER_CUMULATIVE = "water_cumulative"
SENSOR_TYPE_WATER_CURRENT = "water_current"
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_TARGET_TEMPERATURE = "target_temperature"
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
    suggested_display_precision=0,
)

SENSOR_DESC_WEATHER_STATION_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_DESC_WEATHER_STATION_WIND_SPEED = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_WIND_SPEED,
    name="Wind speed",
    native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
    icon="mdi:windsock",
    device_class=SensorDeviceClass.WIND_SPEED,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
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
    suggested_display_precision=0,
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL,
    name="Illuminance (central)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunny",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)

SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST,
    name="Illuminance (east)",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:weather-sunny",
    device_class=SensorDeviceClass.ILLUMINANCE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=0,
)

SENSOR_DESC_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_TEMPERATURE,
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_DESC_TARGET_TEMPERATURE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_TARGET_TEMPERATURE,
    name="Target Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    icon="mdi:thermometer",
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_DESC_HUMIDITY = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_HUMIDITY,
    name="Humidity",
    native_unit_of_measurement=PERCENTAGE,
    icon="mdi:water-percent",
    device_class=SensorDeviceClass.HUMIDITY,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako sensor device."""
    gateway: ESP2Gateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.SENSOR
    if platform in config:
        for entity_config in config[platform]:
            try:
                dev_conf = DeviceConf(entity_config, [CONF_METER_TARIFFS])
                dev_name = dev_conf.name
            
                if dev_conf.eep in [A5_13_01]:
                    if dev_name == dev_conf.name:
                        dev_name = DEFAULT_DEVICE_NAME_WEATHER_STATION
                    
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_DAWN))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_TEMPERATURE))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_WIND_SPEED))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_RAIN))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_WEST))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_CENTRAL))
                    entities.append(EltakoWeatherStation(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WEATHER_STATION_ILLUMINANCE_EAST))
                    
                elif dev_conf.eep in [F6_10_00]:
                    if dev_name == "":
                        dev_name = DEFAULT_DEVICE_NAME_WINDOW_HANDLE
                    
                    entities.append(EltakoWindowHandle(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WINDOWHANDLE))
                    
                elif dev_conf.eep in [A5_12_01]:
                    if dev_name == "":
                        dev_name = DEFAULT_DEVICE_NAME_ELECTRICITY_METER
                        
                    for tariff in dev_conf.get(CONF_METER_TARIFFS, []):
                        entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_ELECTRICITY_CUMULATIVE, tariff=(tariff - 1)))
                    entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_ELECTRICITY_CURRENT, tariff=0))

                elif dev_conf.eep in [A5_12_02]:
                    if dev_name == "":
                        dev_name = DEFAULT_DEVICE_NAME_GAS_METER
                        
                    for tariff in dev_conf.get(CONF_METER_TARIFFS, []):
                        entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_GAS_CUMULATIVE, tariff=(tariff - 1)))
                        entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_GAS_CURRENT, tariff=(tariff - 1)))

                elif dev_conf.eep in [A5_12_03]:
                    if dev_name == "":
                        dev_name = DEFAULT_DEVICE_NAME_WATER_METER
                        
                    for tariff in dev_conf.get(CONF_METER_TARIFFS, []):
                        entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WATER_CUMULATIVE, tariff=(tariff - 1)))
                        entities.append(EltakoMeterSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, SENSOR_DESC_WATER_CURRENT, tariff=(tariff - 1)))

                elif dev_conf.eep in [A5_04_02, A5_10_12]:
                    
                    entities.append(EltakoTemperatureSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    entities.append(EltakoHumiditySensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    if dev_conf.eep in [A5_10_12]:
                        entities.append(EltakoTargetTemperatureSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))

                elif dev_conf.eep in [A5_10_06]:
                    entities.append(EltakoTemperatureSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    entities.append(EltakoTargetTemperatureSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                
                elif dev_conf.eep in [A5_09_0C]:
                ### Eltako FLGTF only supports VOCT Total
                    for t in VOC_SubstancesType:
                        if t.index in entity_config[CONF_VOC_TYPE_INDEXES]:
                            entities.append(EltakoAirQualitySensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep, t, entity_config[CONF_LANGUAGE]))

            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)


    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class EltakoSensor(EltakoEntity, RestoreEntity, SensorEntity):
    """Representation of an  Eltako sensor device such as a power meter."""

    def __init__(self, platform: str, gateway: ESP2Gateway, 
                 dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription
    ) -> None:
        """Initialize the Eltako sensor device."""
        self.entity_description = description
        self._attr_state_class = SensorStateClass.MEASUREMENT
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        #self._attr_unique_id = f"{self.identifier}_{description.key}"
        # self.entity_id = f"{platform}.{self.unique_id}_{description.key}"
        self._attr_native_value = None
        
    @property
    def name(self):
        """Return the default name for the sensor."""
        return self.entity_description.name
        
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
    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name:str, dev_eep:EEP, description: EltakoSensorEntityDescription, *, tariff) -> None:
        """Initialize the Eltako meter sensor device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)
        self._tariff = tariff

    @property
    def name(self):
        """Return the default name for the sensor."""
        return f"{self.entity_description.name} (Tariff {self._tariff + 1})"

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor.
        For cumulative values, we alway respect the channel.
        For current values, we respect the channel just for gas and water.
        """
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        if decoded.learn_button != 1:
            return
        
        tariff = decoded.measurement_channel
        cumulative = not decoded.data_type
        value = decoded.meter_reading
        divisor = 10 ** decoded.divisor
        calculatedValue = value / divisor
        
        if cumulative and self._tariff == tariff and (
            self.entity_description.key == SENSOR_TYPE_ELECTRICITY_CUMULATIVE or
            self.entity_description.key == SENSOR_TYPE_GAS_CUMULATIVE or
            self.entity_description.key == SENSOR_TYPE_WATER_CUMULATIVE):
            self._attr_native_value = round(calculatedValue, 2)
            self.schedule_update_ha_state()
        elif (not cumulative) and msg.data[3] != 0x8F and self.entity_description.key == SENSOR_TYPE_ELECTRICITY_CURRENT: # 0x8F means that, it's sending the serial number of the meter
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

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako window handle sensor device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        if decoded.learn_button != 1:
            return
        
        action = (decoded.movement & 0x70) >> 4
        
        if action == 0x07:
            self._attr_native_value = STATE_CLOSED
        elif action in (0x04, 0x06):
            self._attr_native_value = STATE_OPEN
        elif action == 0x05:
            self._attr_native_value = "tilt"
        else:
            return

        self.schedule_update_ha_state()


class EltakoWeatherStation(EltakoSensor):
    """Representation of an Eltako weather station.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-13-01 (Weather station)
    """

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako weather station device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        if decoded.learn_button != 1:
            return
        
        if msg.data == bytes((0, 0, 0xFF, 0x1A)): # I don't really know why this is filtered out
            return

        if self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN:
            if decoded.identifier != 0x01:
                return
            
            self._attr_native_value = decoded.dawn_sensor
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_TEMPERATURE:
            if decoded.identifier != 0x01:
                return
            
            self._attr_native_value = decoded.temperature
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_WIND_SPEED:
            if decoded.identifier != 0x01:
                return
            
            self._attr_native_value = decoded.wind_speed
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_RAIN:
            if decoded.identifier != 0x01:
                return
            
            self._attr_native_value = decoded.rain_indication
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST:
            if decoded.identifier != 0x02:
                return
            
            self._attr_native_value = decoded.sun_west * 1000.0
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL:
            if decoded.identifier != 0x02:
                return
            
            self._attr_native_value = decoded.sun_south * 1000.0
        elif self.entity_description.key == SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST:
            if decoded.identifier != 0x02:
                return
            
            self._attr_native_value = decoded.sun_east * 1000.0

        self.schedule_update_ha_state()


class EltakoTemperatureSensor(EltakoSensor):
    """Representation of an Eltako temperature sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-04-02 (Temperature and Humidity)
    """

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_TEMPERATURE) -> None:
        """Initialize the Eltako temperature sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_THERMOMETER
        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)

    
    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        self._attr_native_value = decoded.current_temperature

        self.schedule_update_ha_state()


class EltakoTargetTemperatureSensor(EltakoSensor):
    """Representation of an Eltako target temperature sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-10-06, A5-10-12
    """

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_TARGET_TEMPERATURE) -> None:
        """Initialize the Eltako temperature sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_THERMOMETER
        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)
    
    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        self._attr_native_value = decoded.target_temperature

        self.schedule_update_ha_state()


class EltakoHumiditySensor(EltakoSensor):
    """Representation of an Eltako humidity sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-04-02 (Temperature and Humidity)
    """

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name:str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_HUMIDITY) -> None:
        """Initialize the Eltako temperature sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_HYGROSTAT
        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)
    
    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        self._attr_native_value = decoded.humidity

        self.schedule_update_ha_state()

class EltakoAirQualitySensor(EltakoSensor):
    """Representation of an Eltako air quality sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-09-0C
    """

    def __init__(self, platform: str, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, voc_type:VOC_SubstancesType, language:LANGUAGE_ABBREVIATIONS) -> None:
        """Initialize the Eltako air quality sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_THERMOMETER

        self.voc_type_name = voc_type.name_en
        if language == LANGUAGE_ABBREVIATIONS.LANG_GERMAN:
            self.voc_type_name = voc_type.name_de

        description = EltakoSensorEntityDescription(
            key = "air_quality_sensor_"+self.voc_type_name,
            device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
            # device_class=SensorDeviceClass.AQI,
            name = self.voc_type_name,
            native_unit_of_measurement = voc_type.unit,
            icon="mdi:air-filter",
            state_class=SensorStateClass.MEASUREMENT,
        )

        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)
        self.voc_type = voc_type
        # self._attr_suggested_unit_of_measurement = voc_type.unit

        LOGGER.debug(f"entity_description: {self.entity_description}, voc_type: {voc_type}")
    
    
    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        if decoded.voc_type.index == self.voc_type.index:
            # LOGGER.debug(f"[EltakoAirQualitySensor] received message - concentration: {decoded.concentration}, voc_type: {decoded.voc_type}, voc_unit: {decoded.voc_unit}")
            self._attr_native_value = decoded.concentration

        self.schedule_update_ha_state()
