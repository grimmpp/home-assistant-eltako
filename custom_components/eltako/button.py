"""Support for Eltako buttons."""
from __future__ import annotations

from eltakobus.util import AddressExpression
from eltakobus.eep import *
from eltakobus.message import Regular4BSMessage

from homeassistant.components.button import (
    ButtonEntity,
    ButtonDeviceClass,
    ButtonEntityDescription
)
from homeassistant.const import Platform
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import entity_registry as er

from .device import *
from . import config_helpers
from .gateway import EnOceanGateway
from .const import *
from . import get_gateway_from_hass, get_device_config_for_gateway

EEP_WITH_TEACH_IN_BUTTONS = {
    A5_10_06: b'\x40\x30\x0D\x85',  # climate
    A5_38_08: b'\xE0\x40\x0D\x80',  # light
    H5_3F_7F: b'\xFF\xF8\x0D\x80',  # cover
    # F6_02_01  # What button to take?
    # F6_02_02
}

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

                            if sender_config.eep in EEP_WITH_TEACH_IN_BUTTONS.keys():
                                entities.append(TeachInButton(platform, gateway, dev_config.id, dev_config.name, dev_config.eep, sender_config.id, sender_config.eep))
                        except Exception as e:
                            LOGGER.warning("[%s] Could not load configuration", platform)
                            LOGGER.critical(e, exc_info=True)

    # add reconnect button for gateway
    entities.append(GatewayReconnectButton(platform, gateway))

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
            name="Send teach-in telegram from "+sender_id.plain_address().hex(),
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
        msg = Regular4BSMessage(address=controller_address, data=EEP_WITH_TEACH_IN_BUTTONS[self.sender_eep], outgoing=True, status=0x80)
        self.send_message(msg)

class GatewayReconnectButton(AbstractButton):
    """Button for reconnecting serial bus"""

    def __init__(self, platform: str, gateway: EnOceanGateway):
        self.entity_description = ButtonEntityDescription(
            key="gateway_" + str(gateway.dev_id) + "Serial Reconnection",
            name="Reconnect Gateway "+str(gateway.dev_id),
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
