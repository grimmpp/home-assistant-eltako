import datetime
from homeassistant.components.datetime import (
    DateTimeEntity
)

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)

from homeassistant.const import Platform
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType
from custom_components.eltako.eltako_integration_init import get_gateway_from_hass, get_device_config_for_gateway

from .device import *
from . import config_helpers
from .gateway import EnOceanGateway
from .const import *
from . import get_gateway_from_hass, get_device_config_for_gateway


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako buttons."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.DATE


    # last received message timestamp
    entities.append(GatewayLastReceivedMessage(platform, gateway))

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)

class GatewayLastReceivedMessage(EltakoEntity, DateTimeEntity):
    """Protocols last time when message received"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        super().__init__(platform, gateway, gateway.base_id, gateway.dev_name, None)
        self.entity_description = EntityDescription(
            key="Last Message Received",
            name="Last Message Received",
            icon="mdi:button-cursor",
            device_class=SensorDeviceClass.DATE,
            has_entity_name= True,
        )
        self._attr_unique_id = f"{self.identifier}_{self.entity_description.key}"
        self.gateway.set_last_message_received_handler(self.set_value)

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
    
    def set_value(self, value: datetime) -> None:
        """Update the current value."""

        self.native_value = value
        self.schedule_update_ha_state()