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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako buttons."""
    config: ConfigType = hass.data[DATA_ELTAKO][ELTAKO_CONFIG]
    gateway = hass.data[DATA_ELTAKO][ELTAKO_GATEWAY]

    entities: list[EltakoEntity] = []
    
    # check for temperature controller defined in config as temperature sensor or climate controller
    platform_ids = [Platform.SENSOR, Platform.CLIMATE]
    for platform_id in platform_ids:
        if platform_id in config:
            for entity_config in config[platform_id]:
                dev_id = AddressExpression.parse(entity_config.get(CONF_ID))
                dev_name = entity_config[CONF_NAME]
                eep_string = entity_config.get(CONF_EEP)

                sender_id = None
                if platform_id == Platform.CLIMATE:
                    sender_config = entity_config.get(CONF_SENDER)
                    sender_id = AddressExpression.parse(sender_config.get(CONF_ID))

                try:
                    dev_eep = EEP.find(eep_string)
                except:
                    LOGGER.warning("[Sensor] Could not find EEP %s for device with address %s", eep_string, dev_id.plain_address())
                    continue
                else:
                    if dev_eep in [A5_10_06]:
                        if sender_id == None:
                            sender_id = dev_id
                        entities.append(TemperatureControllerTeachInButton(gateway, dev_id, dev_name, dev_eep, sender_id))

    log_entities_to_be_added(entities, Platform.BUTTON)
    async_add_entities(entities)




class TemperatureControllerTeachInButton(EltakoEntity, ButtonEntity):
    """Button which sends teach-in telegram for temperature controller."""

    def __init__(self, gateway: EltakoGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression):
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = "temperature-controller-teach-in-button"
        super().__init__(gateway, dev_id, _dev_name, dev_eep)
        self.entity_description = ButtonEntityDescription(
            key="teach_in_button",
            name="Send teach-in telegram to "+sender_id.plain_address().hex(),
            icon="mdi:button-cursor",
            device_class=ButtonDeviceClass.UPDATE,
            has_entity_name= True,
        )
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{self.entity_description.key}"
        self.entity_id = f"button.{self.unique_id}"
        self.sender_id = sender_id

    async def async_press(self) -> None:
        """Handle the button press."""
        controller_address, _ = self.sender_id
        # data=b'\x40\x30\x0D\x87'
        data = b'\x40\x90\x0D\x80'
        status = 0
        msg:Regular4BSMessage = Regular4BSMessage(controller_address, status, data, True)
        self.send_message(msg)

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