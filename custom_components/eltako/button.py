"""Support for Eltako buttons."""
from __future__ import annotations

from eltakobus.util import AddressExpression
from eltakobus.eep import EEP
from eltakobus.message import Regular4BSMessage

from homeassistant.components.button import (
    ButtonEntity,
    ButtonDeviceClass,
    ButtonEntityDescription
)
from homeassistant.const import Platform
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from .core.entity import EltakoEntity, State, log_entities_to_be_added, validate_actuators_dev_and_sender_id
from .config import config_helpers
from .core.gateway import EnOceanGateway
from .const import (CONF_ENABLE_TEACH_IN_BUTTONS, CONF_SENDER, DOMAIN, GatewayDeviceType, LOGGER,
                    MANUFACTURER, PLATFORMS)
from .core.integration import get_gateway_from_hass, get_device_config_for_gateway
from .catalog.teach_in import get_teach_in_payload, supports_teach_in_button

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako buttons."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []

    platform = Platform.BUTTON

    # if not supported by gateway skip creating teach-in button
    if not gateway.general_settings[CONF_ENABLE_TEACH_IN_BUTTONS]:
        LOGGER.debug("[%s] Teach-in buttons are not supported by gateway %s", Platform.BUTTON, gateway.dev_name)

    else:
        # check for temperature controller defined in config as temperature sensor or climate controller
        for platform_id in PLATFORMS:
            if platform_id in config:
                for entity_config in config[platform_id]:
                    if CONF_SENDER in entity_config:
                        try:
                            dev_config = config_helpers.DeviceConf(entity_config)
                            sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                            if supports_teach_in_button(sender_config.eep):
                                entities.append(TeachInButton(platform, gateway, dev_config.id, dev_config.name, dev_config.eep, sender_config.id, sender_config.eep))
                        except Exception as e:   # noqa: BLE001 - one bad device configuration must not stop the platform
                            LOGGER.warning("[%s] Could not load configuration", platform)
                            LOGGER.critical(e, exc_info=True)

    # add reconnect button for gateway
    entities.append(GatewayReconnectButton(platform, gateway))

    if gateway.dev_type == GatewayDeviceType.EltakoFAM14:
        entities.append(GatewayReadAllDevicesButton(platform, gateway))

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class AbstractButton(EltakoEntity, ButtonEntity):

    def load_value_initially(self, latest_state:State):
        pass


class TeachInButton(AbstractButton):
    """Button which sends teach-in telegram."""

    def __init__(self, platform: str, gateway: EnOceanGateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression, sender_eep: EEP):
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = "teach-in-button"
        self.entity_description = ButtonEntityDescription(
            key="teach_in_button",
            name="Teach-In Button",
            icon="mdi:button-pointer",
            device_class=ButtonDeviceClass.UPDATE,
        )
        self.sender_id = sender_id
        self.sender_eep = sender_eep

        super().__init__(platform, gateway, dev_id, _dev_name, dev_eep)

    async def async_press(self) -> None:
        """
        Handle the button press.
        Send teach-in command
        """

        controller_address, _ = self.sender_id
        msg = Regular4BSMessage(address=controller_address, data=get_teach_in_payload(self.sender_eep), outgoing=True, status=0x80)
        self.send_message(msg)

class GatewayReconnectButton(AbstractButton):
    """Button for reconnecting serial bus"""

    _attr_is_actuator_entity = False

    def __init__(self, platform: str, gateway: EnOceanGateway):
        self.entity_description = ButtonEntityDescription(
            key="gateway_" + str(gateway.dev_id) + "_serial_reconnection",
            name="Reconnect Gateway",
            icon="mdi:button-pointer",
            device_class=ButtonDeviceClass.UPDATE,
        )

        super().__init__(platform, gateway, gateway.base_id, gateway.dev_name, None)

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

    async def async_press(self) -> None:
        """Reconnect serial bus"""
        self.gateway.reconnect()


class GatewayReadAllDevicesButton(AbstractButton):
    """Button for reconnecting serial bus"""

    _attr_is_actuator_entity = False

    def __init__(self, platform: str, gateway: EnOceanGateway):
        self.entity_description = ButtonEntityDescription(
            key="gateway_" + str(gateway.dev_id) + "read_memory_of_bus_devices",
            name="Read memory of bus devices",
            icon="mdi:button-pointer",
            device_class=ButtonDeviceClass.IDENTIFY,
        )

        super().__init__(platform, gateway, gateway.base_id, gateway.dev_name, None)

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

    async def async_press(self) -> None:
        """Read the memories of every device on the bus."""
        # only one operation at a time may talk on the bus - saying so is better than a button
        # which looks like it did something
        if self.gateway.is_bus_busy:
            raise HomeAssistantError(f"The bus is busy with '{self.gateway.bus_busy_reason}' - "
                                     f"while that runs no other telegram may go over it.")
        await self.gateway.read_memory_of_all_bus_members()
