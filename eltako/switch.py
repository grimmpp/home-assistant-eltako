"""Support for Eltako switches."""
from __future__ import annotations

from typing import Any

from eltakobus.util import combine_hex
from eltakobus.util import AddressExpression
import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, LOGGER
from .device import EltakoEntity
from .const import CONF_ID_REGEX, CONF_EEP, DOMAIN, MANUFACTURER

CONF_EEP_SUPPORTED = ["M5-38-08"]
DEFAULT_NAME = "Switch"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
        vol.Required(CONF_EEP): vol.In(CONF_EEP_SUPPORTED),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Eltako switch platform."""
    dev_id = AddressExpression.parse(config.get(CONF_ID))
    dev_name = config.get(CONF_NAME)
    dev_eep = config.get(CONF_EEP)

    async_add_entities([EltakoSwitch(dev_id, dev_name, dev_eep)])


class EltakoSwitch(EltakoEntity, SwitchEntity):
    """Representation of an Eltako switch device."""

    def __init__(self, dev_id, dev_name, dev_eep):
        """Initialize the Eltako switch device."""
        super().__init__(dev_id, dev_name)
        self._dev_eep = dev_eep
        self._on_state = False
        self._attr_unique_id = f"{DOMAIN}_{dev_id.plain_address().hex()}"
        self.entity_id = f"switch.{self.unique_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id.plain_address().hex())},
            manufacturer=MANUFACTURER,
            name=dev_name,
            model=dev_eep,
        )

    @property
    def is_on(self):
        """Return whether the switch is on or off."""
        return self._on_state

    @property
    def name(self):
        """Return the device name."""
        return None

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        optional = [0x03]
        optional.extend(self.dev_id)
        optional.extend([0xFF, 0x00])
        self.send_command(
            data=[0xD2, 0x01, 0xFF, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00],
            optional=optional,
            packet_type=0x01,
        )
        self._on_state = True

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        optional = [0x03]
        optional.extend(self.dev_id)
        optional.extend([0xFF, 0x00])
        self.send_command(
            data=[0xD2, 0x01, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
            optional=optional,
            packet_type=0x01,
        )
        self._on_state = False

    def value_changed(self, msg):
        """Update the internal state of the switch."""
        if self._dev_eep in ["M5-38-08"]:
            if msg.org != 0x05:
                return
                
            if msg.data[0] == 0x70:
                self._on_state = True
            elif msg.data[0] == 0x50:
                self._on_state = False
            self.schedule_update_ha_state()
