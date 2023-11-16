"""Support for Eltako buttons."""
from __future__ import annotations

from enum import Enum

from collections.abc import Callable
from dataclasses import dataclass

from eltakobus.util import AddressExpression
from eltakobus.eep import *
from eltakobus.message import ESP2Message, Regular4BSMessage

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.button import (
    ButtonEntity,
    ButtonDeviceClass,
    ButtonEntityDescription
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
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .device import *
from .gateway import EltakoGateway
from .const import CONF_ID_REGEX, CONF_EEP, CONF_METER_TARIFFS, DOMAIN, MANUFACTURER, DATA_ELTAKO, ELTAKO_CONFIG, ELTAKO_GATEWAY, LOGGER

DEFAULT_DEVICE_NAME_AIR_QUAILTY_SENSOR = "Air Quality Sensor"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako buttons."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoEntity] = []
    
    platform_id = Platform.AIR_QUALITY
    if platform_id in config:
        for entity_config in config[platform_id]:
            dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
            dev_name = entity_config[CONF_NAME]
            eep_string = entity_config.get(CONF_EEP)

            sender_config = entity_config.get(CONF_SENDER)
            sender_id = AddressExpression.parse(sender_config.get(CONF_ID))

            try:
                dev_eep = EEP.find(eep_string)
            except:
                LOGGER.warning("[Sensor] Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                continue
            else:
                if dev_eep in [A5_09_0C]:
                    for t in VOC_SubstancesType:
                        entities.append(EltakoAirQualitySensor(gateway, dev_id, dev_name, dev_eep, t))

    log_entities_to_be_added(entities, platform_id)
    async_add_entities(entities)





class EltakoAirQualitySensor(EltakoSensor):
    """Representation of an Eltako air quality sensor.
    
    EEPs (EnOcean Equipment Profiles):
    - A5-09-0C
    """

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, voc_type:VOC_SubstancesType) -> None:
        """Initialize the Eltako air quality sensor."""
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = DEFAULT_DEVICE_NAME_AIR_QUAILTY_SENSOR

        description = SensorEntityDescription(
            key = "air_quality_sensor_"+voc_type.name,
            device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
            # device_class=SensorDeviceClass.AQI,
            name = voc_type.name,
            native_unit_of_measurement = voc_type.unit,
            icon="mdi:lightning-bolt",
            state_class=SensorStateClass.MEASUREMENT,
        )

        super().__init__(gateway, dev_id, _dev_name, dev_eep, description)
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
                (DOMAIN, self.dev_id.plain_address().hex())
            },
            name=self.dev_name,
            manufacturer=MANUFACTURER,
            model=self.dev_eep.eep_string,
            via_device=(DOMAIN, self.gateway.unique_id),
        )
    
    def value_changed(self, msg):
        """Update the internal state of the sensor."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as e:
            LOGGER.warning("[Sensor] Could not decode message: %s", str(e))
            return
        
        LOGGER.debug(f"[EltakoAirQualitySensor] received message - concentration: {decoded.concentration}, voc_type: {decoded.voc_type}, voc_unit: {decoded.voc_unit}")
        self._attr_native_value = decoded.concentration

        self.schedule_update_ha_state()