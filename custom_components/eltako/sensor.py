"""Support for Eltako sensors."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from eltakobus.util import AddressExpression, b2s
from eltakobus.eep import *
from eltakobus.message import ESP2Message

from . import config_helpers


from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
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
    CONF_LANGUAGE,
    UnitOfElectricPotential,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er

from .device import *
from .config_helpers import *
from .gateway import EnOceanGateway
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

SENSOR_TYPE_BATTERY_VOLTAGE = "electricity_voltage"
SENSOR_TYPE_ELECTRICITY_CUMULATIVE = "electricity_cumulative"
SENSOR_TYPE_ELECTRICITY_CURRENT = "electricity_current"
SENSOR_TYPE_GAS_CUMULATIVE = "gas_cumulative"
SENSOR_TYPE_GAS_CURRENT = "gas_current"
SENSOR_TYPE_WATER_CUMULATIVE = "water_cumulative"
SENSOR_TYPE_WATER_CURRENT = "water_current"
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_TARGET_TEMPERATURE = "target_temperature"
SENSOR_TYPE_HUMIDITY = "humidity"
SENSOR_TYPE_VOLTAGE = "voltage"
SENSOR_TYPE_PIR = "pir"
SENSOR_TYPE_WINDOWHANDLE = "windowhandle"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_DAWN = "weather_station_illuminance_dawn"
SENSOR_TYPE_WEATHER_STATION_TEMPERATURE = "weather_station_temperature"
SENSOR_TYPE_WEATHER_STATION_WIND_SPEED = "weather_station_wind_speed"
SENSOR_TYPE_WEATHER_STATION_RAIN = "weather_station_rain"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_WEST = "weather_station_illuminance_west"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_CENTRAL = "weather_station_illuminance_central"
SENSOR_TYPE_WEATHER_STATION_ILLUMINANCE_EAST = "weather_station_illuminance_east"
SENSOR_TYPE_ILLUMINANCE = "illuminance"


@dataclass
class EltakoSensorEntityDescription(SensorEntityDescription):
    """Describes Eltako sensor entity."""

SENSOR_DESC_BATTERY_VOLTAGE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_BATTERY_VOLTAGE,
    name="Battery Voltage",
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    icon="mdi:lightning-bolt",
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
)

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
    device_class='window',
    native_unit_of_measurement=None,
    suggested_display_precision=None,
    suggested_unit_of_measurement=None,
    state_class=None
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

SENSOR_DESC_ILLUMINATION = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_ILLUMINANCE,
    name="Illuminance",
    native_unit_of_measurement=LIGHT_LUX,
    icon="mdi:sun-wireless-outline",
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

SENSOR_DESC_VOLTAGE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_VOLTAGE,
    name="voltage",
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    icon="mdi:sine-wave",
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_DESC_PIR = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_PIR,
    name="pir",
    native_unit_of_measurement=None,
    icon="mdi:home-outline",
    device_class=None,
    state_class=SensorStateClass.MEASUREMENT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako sensor device."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
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

                elif dev_conf.eep in [A5_04_01, A5_04_02, A5_04_03, A5_10_12]:
                    
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

                elif dev_conf.eep in [A5_07_01]:
                    entities.append(EltakoPirSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    entities.append(EltakoVoltageSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))

                elif dev_conf.eep in [A5_08_01]:
                    entities.append(EltakoTemperatureSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    entities.append(EltakoIlluminationSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    entities.append(EltakoBatteryVoltageSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    # _pir_status => as binary sensor

                elif dev_conf.eep in [A5_06_01]:
                    entities.append(EltakoIlluminationSensor(platform, gateway, dev_conf.id, dev_name, dev_conf.eep))
                    #TODO: add twilight
                    #TODO: add daylight
                    # both are currently combined in illumination

            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", platform)
                LOGGER.critical(e, exc_info=True)

    # add labels for buttons
    if Platform.BINARY_SENSOR in config:
        for entity_config in config[Platform.BINARY_SENSOR]:
            try:
                dev_conf = DeviceConf(entity_config)
                if dev_conf.eep in [F6_02_01, F6_02_02]:
                    def convert_event(event):
                        # if hasattr(event, 'data') and isinstance(event.data, dict) and 'pressed_buttons' in event.data:
                        return config_helpers.button_abbreviation_to_str(event.data['pressed_buttons'])

                    event_id = config_helpers.get_bus_event_type(gateway.dev_id, EVENT_BUTTON_PRESSED, dev_conf.id)
                    entities.append(EventListenerInfoField(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, event_id, "Pushed Buttons", convert_event, "mdi:gesture-tap-button"))

                    entities.append(StaticInfoField(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, "Event Id", event_id, "mdi:form-textbox"))
            
            except Exception as e:
                LOGGER.warning("[%s] Could not load configuration", Platform.BINARY_SENSOR)
                LOGGER.critical(e, exc_info=True)

    # add id field for every device
    for pl in PLATFORMS:
        if pl in config:
            for entity_config in config[pl]:
                try:
                    dev_conf = DeviceConf(entity_config)
                    entities.append(StaticInfoField(platform, gateway, dev_conf.id, dev_conf.name, dev_conf.eep, "Id", b2s(dev_conf.id[0]), "mdi:identifier"))
                
                except Exception as e:
                    LOGGER.warning("[%s] Could not load configuration", Platform.BINARY_SENSOR)
                    LOGGER.critical(e, exc_info=True)


    # add gateway information
    entities.append(GatewayInfoField(platform, gateway, "Id", str(gateway.dev_id), "mdi:identifier"))
    entities.append(GatewayInfoField(platform, gateway, "Base Id", b2s(gateway.base_id[0]), "mdi:identifier"))
    entities.append(GatewayInfoField(platform, gateway, "Serial Path", gateway.serial_path, "mdi:usb"))
    entities.append(GatewayInfoField(platform, gateway, "USB Protocol", gateway.native_protocol, "mdi:usb"))
    entities.append(GatewayLastReceivedMessage(platform, gateway))
    entities.append(GatewayReceivedMessagesInActiveSession(platform, gateway))

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class EltakoSensor(EltakoEntity, RestoreEntity, SensorEntity):
    """Representation of an  Eltako sensor device such as a power meter."""

    def __init__(self, platform: str, gateway: EnOceanGateway, 
                 dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription
    ) -> None:
        """Initialize the Eltako sensor device."""
        self.entity_description = description
        self._attr_state_class = description.state_class
        
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep)
        self._attr_native_value = None
        
    @property
    def name(self):
        """Return the default name for the sensor."""
        return self.entity_description.name

    def load_value_initially(self, latest_state:State):
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] eneity unique_id: {self.unique_id}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - state: {latest_state.state}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - attributes: {latest_state.attributes}")
        try:
            if 'unknown' == latest_state.state:
                self._attr_is_on = None
            else:
                if latest_state.attributes.get('state_class', None) == 'measurement':
                    if latest_state.state.count('.') + latest_state.state.count(',') == 1:
                        self._attr_native_value = float(latest_state.state)
                    elif latest_state.state.count('.') == 0 and latest_state.state.count(',') == 0:
                        self._attr_native_value = int(latest_state.state)
                    else:
                        self._attr_native_value = None

                elif latest_state.attributes.get('state_class', None) == 'total_increasing':
                    self._attr_native_value = int(latest_state.state)

                elif latest_state.attributes.get('device_class', None) == 'device_class':
                    # e.g.: 2024-02-12T23:32:44+00:00
                    self._attr_native_value = datetime.strptime(latest_state.state, '%Y-%m-%dT%H:%M:%S%z:%f')
            
        except Exception as e:
            if hasattr(self, '_attr_is_on'):
                self._attr_is_on = None
            elif hasattr(self, '_attr_native_value'):
                self._attr_native_value = None
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id} ({type(self).__name__})] value initially loaded: [native_value: {self.native_value}, state: {self.state}]")        

class EltakoPirSensor(EltakoSensor):
    """Occupancy Sensor"""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name:str, dev_eep:EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_PIR) -> None:
        """Initialize the Eltako meter sensor device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded:A5_07_01 = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Motion Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.pir_status

        self.schedule_update_ha_state()


class EltakoVoltageSensor(EltakoSensor):
    """Voltage Sensor"""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name:str, dev_eep:EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_VOLTAGE) -> None:
        """Initialize the Eltako meter sensor device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded:A5_07_01 = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Voltage Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.support_voltage

        self.schedule_update_ha_state()


class EltakoMeterSensor(EltakoSensor):
    """Representation of an Eltako electricity sensor.

    EEPs (EnOcean Equipment Profiles):
    - A5-12-01 (Automated Meter Reading, Electricity)
    - A5-12-02 (Automated Meter Reading, Gas)
    - A5-12-03 (Automated Meter Reading, Water)
    """
    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name:str, dev_eep:EEP, description: EltakoSensorEntityDescription, *, tariff) -> None:
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
            LOGGER.warning("[Meter Sensor %s] Could not decode message: %s", self.dev_id, str(e))
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

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako window handle sensor device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded:F6_10_00 = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Window Handle Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        if decoded.handle_position == WindowHandlePosition.CLOSED:
            self._attr_native_value = STATE_CLOSED
        elif decoded.handle_position == WindowHandlePosition.OPEN:
            self._attr_native_value = STATE_OPEN
        elif decoded.handle_position == WindowHandlePosition.TILT:
            self._attr_native_value = "tilt"
        else:
            return

        self.schedule_update_ha_state()


class EltakoWeatherStation(EltakoSensor):
    """Representation of an Eltako weather station.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-13-01 (Weather station)
    """

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription) -> None:
        """Initialize the Eltako weather station device."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Weather Station %s] Could not decode message: %s", self.dev_id, str(e))
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

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_TEMPERATURE) -> None:
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
            LOGGER.warning("[Temperature Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.current_temperature

        self.schedule_update_ha_state()

class EltakoIlluminationSensor(EltakoSensor):
    """Brightness sensor"""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_ILLUMINATION) -> None:
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
            LOGGER.warning("[Illumination Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.illumination

        self.schedule_update_ha_state()


class EltakoBatteryVoltageSensor(EltakoSensor):
    """Representation of an Eltako battery sensor."""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_BATTERY_VOLTAGE) -> None:
        """Initialize the Eltako temperature sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = "Battery Sensor"
        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)

    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Battery Voltage Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.supply_voltage

        self.schedule_update_ha_state()


class EltakoTargetTemperatureSensor(EltakoSensor):
    """Representation of an Eltako target temperature sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-10-06, A5-10-12
    """

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_TARGET_TEMPERATURE) -> None:
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
            LOGGER.warning("[Target Temperature Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = round(2 * decoded.target_temperature, 0) / 2

        self.schedule_update_ha_state()


class EltakoHumiditySensor(EltakoSensor):
    """Representation of an Eltako humidity sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-04-02 (Temperature and Humidity)
    """

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name:str, dev_eep: EEP, description: EltakoSensorEntityDescription=SENSOR_DESC_HUMIDITY) -> None:
        """Initialize the Eltako humidity sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_HYGROSTAT
        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep, description)
    
    def value_changed(self, msg: ESP2Message):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Humidity Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        self._attr_native_value = decoded.humidity

        self.schedule_update_ha_state()

class EltakoAirQualitySensor(EltakoSensor):
    """Representation of an Eltako air quality sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-09-0C
    """

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, voc_type:VOC_SubstancesType, language:LANGUAGE_ABBREVIATION) -> None:
        """Initialize the Eltako air quality sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_THERMOMETER

        self.voc_type_name = voc_type.name_en
        if language == LANGUAGE_ABBREVIATION.LANG_GERMAN:
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
            LOGGER.warning("[Air Quality Sensor %s] Could not decode message: %s", self.dev_id, str(e))
            return
        
        if decoded.voc_type.index == self.voc_type.index:
            # LOGGER.debug(f"[EltakoAirQualitySensor] received message - concentration: {decoded.concentration}, voc_type: {decoded.voc_type}, voc_unit: {decoded.voc_unit}")
            self._attr_native_value = decoded.concentration

        self.schedule_update_ha_state()

class GatewayLastReceivedMessage(EltakoSensor):
    """Protocols last time when message received"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        super().__init__(platform, gateway,
                         dev_id=gateway.base_id, 
                         dev_name="Last Message Received", 
                         dev_eep=None,
                         description=EltakoSensorEntityDescription(
                            key="Last Message Received",
                            name="Last Message Received",
                            icon="mdi:message-check-outline",
                            device_class=SensorDeviceClass.TIMESTAMP,
                            has_entity_name= True,
                        )
        )
        self._attr_name = "Last Message Received"
        self.gateway.set_last_message_received_handler(self.async_value_changed)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway.serial_path)},
            name= self.gateway.dev_name,
            manufacturer=MANUFACTURER,
            model=self.gateway.model,
            via_device=(DOMAIN, self.gateway.serial_path)
        )
    
    async def async_value_changed(self, value: datetime) -> None:
        try:
            self.value_changed(value)
        except AttributeError as e:
            # Home Assistant not ready yet
            pass  

    def value_changed(self, value: datetime) -> None:
        """Update the current value."""
        # LOGGER.debug("[%s] Last message received", Platform.SENSOR)

        if isinstance(value, datetime):
            self.native_value = value
            self.schedule_update_ha_state()

class GatewayReceivedMessagesInActiveSession(EltakoSensor):
    """Protocols amount of messages per session"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        super().__init__(platform, gateway,
                         dev_id=gateway.base_id, 
                         dev_name="Received Messages per Session", 
                         dev_eep=None,
                         description=EltakoSensorEntityDescription(
                            key="Received Messages per Session",
                            name="Received Messages per Session",
                            state_class=SensorStateClass.TOTAL_INCREASING,
                            # device_class=SensorDeviceClass.VOLUME,
                            # native_unit_of_measurement="Messages", # => raises error message
                            unit_of_measurement="Messages",
                            suggested_unit_of_measurement="Messages",
                            icon="mdi:chart-line",
                        )
        )
        self._attr_name="Received Messages per Session"
        self.gateway.set_received_message_count_handler(self.async_value_changed)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway.serial_path)},
            name= self.gateway.dev_name,
            manufacturer=MANUFACTURER,
            model=self.gateway.model,
            via_device=(DOMAIN, self.gateway.serial_path)
        )
    
    async def async_value_changed(self, value: int) -> None:
        try:
            self.value_changed(value)
        except AttributeError as e:
            # Home Assistant not ready yet
            pass  

    def value_changed(self, value: int) -> None:
        """Update the current value."""
        # LOGGER.debug("[%s] received amount of messages: %s", Platform.SENSOR, str(value))

        self.native_value = value
        self.schedule_update_ha_state()


class StaticInfoField(EltakoSensor):
    """Key value fields for gateway information"""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, key:str, value:str, icon:str=None):
        super().__init__(platform, gateway,
                         dev_id=dev_id, 
                         dev_name=dev_name, 
                         dev_eep=dev_eep,
                         description=EltakoSensorEntityDescription(
                            key=key,
                            name=key,
                            icon=icon,
                            has_entity_name= True,
                        )
        )
        self._attr_name = key
        self._attr_native_value = value

    def value_changed(self, value) -> None:
        pass

class GatewayInfoField(StaticInfoField):
    """Key value fields for gateway information"""

    def __init__(self, platform: str, gateway: EnOceanGateway, key:str, value:str, icon:str=None):
        super().__init__(platform, 
                         gateway,
                         dev_id=gateway.base_id, 
                         dev_name=key, 
                         dev_eep=None,
                         key=key,
                         value=value,
                         icon=icon
                         )
        
    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.gateway.serial_path)},
            name= self.gateway.dev_name,
            manufacturer=MANUFACTURER,
            model=self.gateway.model,
            via_device=(DOMAIN, self.gateway.serial_path)
        )
        
class EventListenerInfoField(EltakoSensor):
    """Key value fields for gateway information"""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, event_id: str, key:str, convert_event_function, icon:str=None):
        super().__init__(platform, gateway,
                         dev_id=dev_id, 
                         dev_name=dev_name, 
                         dev_eep=dev_eep,
                         description=EltakoSensorEntityDescription(
                            key=key,
                            name=key,
                            icon=icon,
                            has_entity_name= True,
                        )
        )
        self.convert_event_function = convert_event_function
        self._attr_name = key
        self._attr_native_value = ''
        self.listen_to_addresses.clear()

        LOGGER.debug(f"[{platform}] [{EventListenerInfoField.__name__}] [{b2s(dev_id[0])}] [{key}] Register event: {event_id}")
        self.hass.bus.async_listen(event_id, self.value_changed)

    
    def value_changed(self, event) -> None:
        LOGGER.debug(f"Received event: {event}")
        self.native_value = self.convert_event_function(event)

        self.schedule_update_ha_state()
            