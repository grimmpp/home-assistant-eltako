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

from .device import *
from . import config_helpers
from .gateway import ESP2Gateway
from .const import *
from . import get_gateway_from_hass, get_device_config_for_gateway

EEP_WITH_TEACH_IN_BUTTONS = {
    A5_10_06: b'\x40\x30\x0D\x85'
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an Eltako buttons."""
    gateway: ESP2Gateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)

    entities: list[EltakoEntity] = []
    
    # if not supported by gateway skip creating teach-in button
    if not gateway.general_settings[CONF_ENABLE_TEACH_IN_BUTTONS]:
        LOGGER.debug("[%s] Teach-in buttons are not supported by gateway %s", Platform.BUTTON, gateway.dev_name)
        return
    
    platform = Platform.BUTTON

    # check for temperature controller defined in config as temperature sensor or climate controller
    for platform_id in PLATFORMS:
        if platform_id in config: 
            for entity_config in config[platform_id]:
                if CONF_SENDER in entity_config:
                    try:
                        dev_config = device_conf(entity_config)
                        sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)

                        if dev_config.eep in EEP_WITH_TEACH_IN_BUTTONS.keys():
                            entities.append(TemperatureControllerTeachInButton(gateway, dev_config.id, dev_config.name, dev_config.eep, sender_config.id))
                    except Exception as e:
                        LOGGER.warning("[%s] Could not load configuration", platform)
                        LOGGER.critical(e, exc_info=True)

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)



class TemperatureControllerTeachInButton(EltakoEntity, ButtonEntity):
    """Button which sends teach-in telegram for temperature controller."""

    def __init__(self, gateway: ESP2Gateway, dev_id: AddressExpression, dev_name: str, dev_eep: EEP, sender_id: AddressExpression):
        _dev_name = dev_name
        if _dev_name == "":
            _dev_name = "temperature-controller-teach-in-button"
        super().__init__(gateway, dev_id, _dev_name, dev_eep)
        self.entity_description = ButtonEntityDescription(
            key="teach_in_button",
            name="Send teach-in telegram from "+sender_id.plain_address().hex(),
            icon="mdi:button-cursor",
            device_class=ButtonDeviceClass.UPDATE,
            has_entity_name= True,
        )
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}_{self.entity_description.key}"
        self.entity_id = f"button.{self.unique_id}"
        self.sender_id = sender_id

    async def async_press(self) -> None:
        """
        Handle the button press.
        Send teach-in command for A5-10-06 e.g. FUTH
        """
        controller_address, _ = self.sender_id
        # msg = Regular4BSMessage(address=controller_address, data=b'\x40\x30\x0D\x85', outgoing=True, status=0x80)
        msg = Regular4BSMessage(address=controller_address, data=EEP_WITH_TEACH_IN_BUTTONS[self.dev_eep], outgoing=True, status=0x80)
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