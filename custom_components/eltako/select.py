"""Support for Eltako light sources."""
from __future__ import annotations

from typing import Any

from eltakobus.util import AddressExpression
from eltakobus.eep import *

from homeassistant.components.select import (
    SelectEntity
)
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er

from . import config_helpers, get_gateway_from_hass, get_device_config_for_gateway
from .config_helpers import DeviceConf
from .device import *
from .gateway import EnOceanGateway
from .const import *


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako select platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    platform = Platform.CLIMATE
    if platform in config:
        for entity_config in config[platform]:
            try:
                dev_config = DeviceConf(entity_config)
                entities.append(ClimatePriority(platform, gateway, dev_config.id, dev_config.name, dev_config.eep))

            except Exception as e:
                LOGGER.warning("[%s %s] Could not load configuration", platform, str(dev_config.id))
                LOGGER.critical(e, exc_info=True)
        
    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class ClimatePriority(EltakoEntity, SelectEntity, RestoreEntity):
    """Defines priority for controlling heating actuators"""

    DEFAULT_PRIO = A5_10_06.ControllerPriority.AUTO.description

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP):
        _dev_name = dev_name

        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep)

        self.name = "Priority"

        self.event_id = config_helpers.get_bus_event_type(self.gateway.dev_id, EVENT_CLIMATE_PRIORITY_SELECTED, self.dev_id)

        self._attr_options = [A5_10_06.ControllerPriority.AUTO.description,
                              A5_10_06.ControllerPriority.HOME_AUTOMATION.description,
                              A5_10_06.ControllerPriority.THERMOSTAT.description,
                              A5_10_06.ControllerPriority.LIMIT.description]
        self._attr_current_option = A5_10_06.ControllerPriority.AUTO.description

    
    def load_value_initially(self, latest_state:State):
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - state: {latest_state.state}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - attributes: {latest_state.attributes}")
        try:
            self._attr_current_option = latest_state.state
            if self._attr_current_option == None:
                self._attr_current_option = self.DEFAULT_PRIO
                
        except Exception as e:
            self._attr_current_option = self.DEFAULT_PRIO
            raise e
        
        self.schedule_update_ha_state()

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] value initially loaded: [state: {self.state}]")


    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] selected option: {option}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] Send event id: '{self.event_id}' data: '{option}'")

        self.hass.bus.fire(self.event_id, { "priority": option })