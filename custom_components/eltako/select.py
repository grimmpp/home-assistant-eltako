"""Support for Eltako light sources."""
from __future__ import annotations


from eltakobus.util import AddressExpression
from eltakobus.eep import A5_10_06, EEP

from homeassistant.components.select import (
    SelectEntity
)
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .config import config_helpers

from .core.integration import get_gateway_from_hass, get_device_config_for_gateway
from .config.config_helpers import DeviceConf
from .core.entity import (DeviceInfo, EltakoEntity, RestoreEntity, State, log_entities_to_be_added,
                          validate_actuators_dev_and_sender_id)
from .core.gateway import EnOceanGateway, BusBusyError
from .const import CONF_ROOM_THERMOSTAT, DOMAIN, EVENT_CLIMATE_PRIORITY_SELECTED, LOGGER, MANUFACTURER


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako select platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []

    # The configuration of the priority selection is part of the climate section, but the
    # entities themselves belong to the select platform. (Otherwise they would get an entity id
    # of the climate domain which collides with the climate entity of the same device.)
    config_platform = Platform.CLIMATE
    if config_platform in config:
        for entity_config in config[config_platform]:
            try:
                dev_config = DeviceConf(entity_config, [CONF_ROOM_THERMOSTAT])
                thermostat = dev_config.get(CONF_ROOM_THERMOSTAT)

                # Priority selection is only meaningful when a physical thermostat
                # competes with the HA software controller.
                if thermostat:
                    entities.append(ClimatePriority(Platform.SELECT, gateway, dev_config.id, dev_config.name, dev_config.eep))

            except Exception as e:   # noqa: BLE001 - one bad device configuration must not stop the platform
                LOGGER.warning("[%s %s] Could not load configuration", config_platform, str(dev_config.id))
                LOGGER.critical(e, exc_info=True)

    # add for every gateway
    platform = Platform.SELECT
    entities.append(RepeaterMode(platform, gateway))

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

        self.event_id = config_helpers.get_bus_event_type(gateway.base_id, EVENT_CLIMATE_PRIORITY_SELECTED, self.dev_id)

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
            if self._attr_current_option in [None, 'unknown']:
                self._attr_current_option = self.DEFAULT_PRIO

        except Exception as e:
            self._attr_current_option = self.DEFAULT_PRIO
            raise e

        ## send value to initially set value of climate controller
        self.hass.bus.fire(self.event_id, { "priority": self._attr_current_option })

        self.schedule_update_ha_state()

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] value initially loaded: [state: {self.state}]")


    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""

        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] selected option: {option}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] Send event id: '{self.event_id}' data: '{option}'")

        self.hass.bus.fire(self.event_id, { "priority": option })

        self._attr_current_option = option
        self.schedule_update_ha_state()


class RepeaterMode(EltakoEntity, SelectEntity, RestoreEntity):
    """Defines priority for controlling heating actuators"""

    # gateway configuration entity - uses 00-00-00-00 as device id by design
    _attr_is_actuator_entity = False

    DEFAULT_REPEATER_MODE = "None"

    def __init__(self, platform: str, gateway: EnOceanGateway):

        super().__init__(platform, gateway, dev_id=AddressExpression.parse('00-00-00-00'), dev_name="Repeater_Mode", dev_eep=None)

        self.name = "Repeater Mode"

        self._attr_options = ["None", "Level 1", "Level 2"]
        self._attr_current_option = "None"
        self.gateway.add_repeater_mode_change_handler(self.async_receive_bus_update)

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


    def load_value_initially(self, latest_state:State):
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - state: {latest_state.state}")
        LOGGER.debug(f"[{self._attr_ha_platform} {self.dev_id}] latest state - attributes: {latest_state.attributes}")
        try:
            self._attr_current_option = latest_state.state
            if self._attr_current_option in [None, 'unknown']:
                self._attr_current_option = self.DEFAULT_REPEATER_MODE

        except Exception as e:
            self._attr_current_option = self.DEFAULT_REPEATER_MODE
            raise e

        ## send value to initially set value of climate controller
        self.gateway.request_repeater_mode()

        self.schedule_update_ha_state()

        LOGGER.debug(f"[{self._attr_ha_platform} {self.unique_id}] value initially loaded: [state: {self.state}]")


    async def async_receive_bus_update(self, mode:int) -> None:
        option = "None"
        if mode == 1: option = "Level 1"
        if mode == 2: option = "Level 2"

        self._attr_current_option = option
        self.schedule_update_ha_state()


    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""

        LOGGER.debug(f"[{self._attr_ha_platform} {self.unique_id}] selected option: {option}")

        level = 0
        if option == "Level 1": level = 1
        if option == "Level 2": level = 2

        try:
            self.gateway.set_repeater_mode(level)
        except BusBusyError as e:
            # while a scan or a teach-in has the bus, nothing else may talk on it. The option
            # keeps its old value so that it shows what the gateway really does.
            LOGGER.warning(f"[{self._attr_ha_platform} {self.unique_id}] {e}")
            raise HomeAssistantError(str(e)) from e

        self._attr_current_option = option
        self.schedule_update_ha_state()
