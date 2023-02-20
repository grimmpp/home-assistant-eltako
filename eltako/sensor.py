"""Support for Eltako sensors."""
from __future__ import annotations

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
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import EltakoEntity

CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_RANGE_FROM = "range_from"
CONF_RANGE_TO = "range_to"

DEFAULT_NAME = "Eltako sensor"

SENSOR_TYPE_HUMIDITY = "humidity"
SENSOR_TYPE_POWER = "powersensor"
SENSOR_TYPE_TEMPERATURE = "temperature"
SENSOR_TYPE_WINDOWHANDLE = "windowhandle"


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
    unique_id=lambda dev_id: f"{dev_id.plain_address.hex()}-{SENSOR_TYPE_TEMPERATURE}",
)

SENSOR_DESC_HUMIDITY = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_HUMIDITY,
    name="Humidity",
    native_unit_of_measurement=PERCENTAGE,
    icon="mdi:water-percent",
    device_class=SensorDeviceClass.HUMIDITY,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address.hex()}-{SENSOR_TYPE_HUMIDITY}",
)

SENSOR_DESC_POWER = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_POWER,
    name="Power",
    native_unit_of_measurement=UnitOfPower.WATT,
    icon="mdi:power-plug",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    unique_id=lambda dev_id: f"{dev_id.plain_address.hex()}-{SENSOR_TYPE_POWER}",
)

SENSOR_DESC_WINDOWHANDLE = EltakoSensorEntityDescription(
    key=SENSOR_TYPE_WINDOWHANDLE,
    name="WindowHandle",
    icon="mdi:window-open-variant",
    unique_id=lambda dev_id: f"{dev_id.plain_address.hex()}-{SENSOR_TYPE_WINDOWHANDLE}",
)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS, default=SENSOR_TYPE_POWER): cv.string,
        vol.Optional(CONF_MAX_TEMP, default=40): vol.Coerce(int),
        vol.Optional(CONF_MIN_TEMP, default=0): vol.Coerce(int),
        vol.Optional(CONF_RANGE_FROM, default=255): cv.positive_int,
        vol.Optional(CONF_RANGE_TO, default=0): cv.positive_int,
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
    sensor_type = config[CONF_DEVICE_CLASS]

    entities: list[EltakoSensor] = []
    if sensor_type == SENSOR_TYPE_TEMPERATURE:
        temp_min = config[CONF_MIN_TEMP]
        temp_max = config[CONF_MAX_TEMP]
        range_from = config[CONF_RANGE_FROM]
        range_to = config[CONF_RANGE_TO]
        entities = [
            EltakoTemperatureSensor(
                dev_id,
                dev_name,
                SENSOR_DESC_TEMPERATURE,
                scale_min=temp_min,
                scale_max=temp_max,
                range_from=range_from,
                range_to=range_to,
            )
        ]

    elif sensor_type == SENSOR_TYPE_HUMIDITY:
        entities = [EltakoHumiditySensor(dev_id, dev_name, SENSOR_DESC_HUMIDITY)]

    elif sensor_type == SENSOR_TYPE_POWER:
        entities = [EltakoPowerSensor(dev_id, dev_name, SENSOR_DESC_POWER)]

    elif sensor_type == SENSOR_TYPE_WINDOWHANDLE:
        entities = [EltakoWindowHandle(dev_id, dev_name, SENSOR_DESC_WINDOWHANDLE)]

    add_entities(entities)


class EltakoSensor(EltakoEntity, RestoreEntity, SensorEntity):
    """Representation of an  Eltako sensor device such as a power meter."""

    def __init__(
        self, dev_id, dev_name, description: EltakoSensorEntityDescription
    ) -> None:
        """Initialize the Eltako sensor device."""
        super().__init__(dev_id, dev_name)
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


class EltakoPowerSensor(EltakoSensor):
    """Representation of an Eltako power sensor.

    EEPs (EnOcean Equipment Profiles):
    - A5-12-01 (Automated Meter Reading, Electricity)
    """

    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        if msg.org != 0xA5:
            return
        # TODO: Implement parsing
#        msg.parse_eep(0x12, 0x01)
#        if msg.parsed["DT"]["raw_value"] == 1:
            # this message reports the current value
#            raw_val = msg.parsed["MR"]["raw_value"]
#            divisor = msg.parsed["DIV"]["raw_value"]
#            self._attr_native_value = raw_val / (10**divisor)
#            self.schedule_update_ha_state()


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
        if msg.org != 0xA5:
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
        if msg.org != 0xA5:
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
        action = (msg.data[1] & 0x70) >> 4

        if action == 0x07:
            self._attr_native_value = STATE_CLOSED
        if action in (0x04, 0x06):
            self._attr_native_value = STATE_OPEN
        if action == 0x05:
            self._attr_native_value = "tilt"

        self.schedule_update_ha_state()
