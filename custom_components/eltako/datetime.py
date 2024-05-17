import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.sensor import SensorDeviceClass

from homeassistant.const import Platform
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er
from custom_components.eltako.eltako_integration_init import get_gateway_from_hass, get_device_config_for_gateway

from .device import *
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
        self.entity_description = EntityDescription(
            key="Last Message Received",
            name="Last Message Received",
            icon="mdi:button-cursor",
            device_class=SensorDeviceClass.DATE,
        )
        self.gateway.set_last_message_received_handler(self.set_value)

        super().__init__(platform, gateway, gateway.base_id, gateway.dev_name, None)

    def load_value_initially(self, latest_state:State):
        try:
            if 'unknown' == latest_state.state:
                self._attr_native_value = None
            else:
                # e.g.: 2024-02-12T23:32:44+00:00
                self._attr_native_value = datetime.strptime(latest_state.state, '%Y-%m-%dT%H:%M:%S%z:%f')
            
        except Exception as e:
            self._attr_native_value = None
            raise e
        
        self.schedule_update_ha_state()
        LOGGER.debug(f"[datetime {self.dev_id}] value initially loaded: [native_value: {self.native_value}, state: {self.state}]")

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