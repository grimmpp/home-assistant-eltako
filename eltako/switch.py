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
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, LOGGER
from .device import EltakoEntity
from .const import CONF_ID_REGEX

CONF_CHANNEL = "channel"
DEFAULT_NAME = "Eltako Switch"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ID): cv.matches_regex(CONF_ID_REGEX),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_CHANNEL, default=0): cv.positive_int,
    }
)


def generate_unique_id(dev_id: list[int], channel: int) -> str:
    """Generate a valid unique id."""
    return f"{dev_id.plain_address().hex()}-{channel}"


def _migrate_to_new_unique_id(hass: HomeAssistant, dev_id, channel) -> None:
    """Migrate old unique ids to new unique ids."""
    old_unique_id = f"{dev_id.plain_address().hex()}"

    ent_reg = entity_registry.async_get(hass)
    entity_id = ent_reg.async_get_entity_id(Platform.SWITCH, DOMAIN, old_unique_id)

    if entity_id is not None:
        new_unique_id = generate_unique_id(dev_id, channel)
        try:
            ent_reg.async_update_entity(entity_id, new_unique_id=new_unique_id)
        except ValueError:
            LOGGER.warning(
                "Skip migration of id [%s] to [%s] because it already exists",
                old_unique_id,
                new_unique_id,
            )
        else:
            LOGGER.debug(
                "Migrating unique_id from [%s] to [%s]",
                old_unique_id,
                new_unique_id,
            )


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Eltako switch platform."""
    channel = config.get(CONF_CHANNEL)
    dev_id = AddressExpression.parse(config.get(CONF_ID))
    dev_name = config.get(CONF_NAME)

    _migrate_to_new_unique_id(hass, dev_id, channel)
    async_add_entities([EltakoSwitch(dev_id, dev_name, channel)])


class EltakoSwitch(EltakoEntity, SwitchEntity):
    """Representation of an Eltako switch device."""

    def __init__(self, dev_id, dev_name, channel):
        """Initialize the Eltako switch device."""
        super().__init__(dev_id, dev_name)
        self._light = None
        self._on_state = False
        self._on_state2 = False
        self.channel = channel
        self._attr_unique_id = generate_unique_id(dev_id, channel)

    @property
    def is_on(self):
        """Return whether the switch is on or off."""
        return self._on_state

    @property
    def name(self):
        """Return the device name."""
        return self.dev_name

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        optional = [0x03]
        optional.extend(self.dev_id)
        optional.extend([0xFF, 0x00])
        self.send_command(
            data=[0xD2, 0x01, self.channel & 0xFF, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00],
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
            data=[0xD2, 0x01, self.channel & 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
            optional=optional,
            packet_type=0x01,
        )
        self._on_state = False

    def value_changed(self, msg):
        """Update the internal state of the switch."""
        if msg.org == 0x07:
            pass
            # TODO: Implement parsing
            # power meter telegram, turn on if > 10 watts
#            msg.parse_eep(0x12, 0x01)
#            if msg.parsed["DT"]["raw_value"] == 1:
#                raw_val = msg.parsed["MR"]["raw_value"]
#                divisor = msg.parsed["DIV"]["raw_value"]
#                watts = raw_val / (10**divisor)
#                if watts > 1:
#                    self._on_state = True
#                    self.schedule_update_ha_state()
        elif msg.data[0] == 0x05:
            pass
            # TODO: Implement parsing
            # actuator status telegram
#            msg.parse_eep(0x01, 0x01)
#            if msg.parsed["CMD"]["raw_value"] == 4:
#                channel = msg.parsed["IO"]["raw_value"]
#                output = msg.parsed["OV"]["raw_value"]
#                if channel == self.channel:
#                    self._on_state = output > 0
#                    self.schedule_update_ha_state()
