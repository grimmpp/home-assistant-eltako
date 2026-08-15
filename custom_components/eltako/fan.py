"""Support for Eltako ventilation fans."""
from __future__ import annotations

from typing import Any

from eltakobus.eep import (
    A5_38_08,
    CentralCommandDimming,
    CentralCommandSwitching,
    EEP,
    M5_38_08,
)
from eltakobus.message import ESP2Message
from eltakobus.util import AddressExpression

from homeassistant import config_entries
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.const import Platform, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .config import config_helpers
from .config.config_helpers import DeviceConf
from .const import CONF_FAST_STATUS_CHANGE, CONF_SENDER, LOGGER
from .core.entity import (
    EltakoEntity,
    RestoreEntity,
    State,
    log_entities_to_be_added,
    validate_actuators_dev_and_sender_id,
)
from .core.gateway import EnOceanGateway
from .core.integration import get_device_config_for_gateway, get_gateway_from_hass


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Eltako fan platform."""
    gateway: EnOceanGateway = get_gateway_from_hass(hass, config_entry)
    config: ConfigType = get_device_config_for_gateway(hass, config_entry, gateway)
    entities: list[EltakoFan] = []

    platform = Platform.FAN
    for entity_config in config.get(platform, []):
        try:
            dev_conf = DeviceConf(entity_config)
            sender_config = config_helpers.get_device_conf(entity_config, CONF_SENDER)
            entities.append(
                EltakoFan(
                    platform,
                    gateway,
                    dev_conf.id,
                    dev_conf.name,
                    dev_conf.eep,
                    sender_config.id,
                    sender_config.eep,
                    dev_conf.area,
                )
            )
        except Exception as err:  # noqa: BLE001 - one bad device must not stop the platform
            LOGGER.warning("[%s] Could not load configuration", platform)
            LOGGER.critical(err, exc_info=True)

    validate_actuators_dev_and_sender_id(entities)
    log_entities_to_be_added(entities, platform)
    async_add_entities(entities)


class EltakoFan(EltakoEntity, FanEntity, RestoreEntity):
    """Representation of an Eltako ventilation fan."""

    def __init__(
        self,
        platform: str,
        gateway: EnOceanGateway,
        dev_id: AddressExpression,
        dev_name: str,
        dev_eep: EEP,
        sender_id: AddressExpression,
        sender_eep: EEP,
        dev_area: str | None = None,
    ) -> None:
        """Initialize the fan."""
        super().__init__(platform, gateway, dev_id, dev_name, dev_eep, dev_area=dev_area)
        self._sender_id = sender_id
        self._sender_eep = sender_eep

        self._attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if dev_eep == A5_38_08:
            self._attr_supported_features |= FanEntityFeature.SET_SPEED

    def load_value_initially(self, latest_state: State) -> None:
        """Restore the last known fan speed without inventing a state."""
        if latest_state.state == STATE_UNKNOWN:
            self._attr_percentage = None
        elif latest_state.state == "on":
            self._attr_percentage = latest_state.attributes.get("percentage", 100)
        else:
            self._attr_percentage = 0

        self.schedule_update_ha_state()

    def turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on, optionally at a requested percentage."""
        self.set_percentage(100 if percentage is None else percentage)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        self.set_percentage(0)

    def set_percentage(self, percentage: int) -> None:
        """Send the Eltako command for a fan speed."""
        percentage = max(0, min(100, int(percentage)))
        address, _ = self._sender_id

        if self._sender_eep != A5_38_08:
            LOGGER.warning(
                "[%s %s] Sender EEP %s not supported.",
                Platform.FAN,
                self.dev_id,
                self._sender_eep.eep_string,
            )
            return

        if self.dev_eep == A5_38_08:
            # A5-38-08 uses the dimming command for variable fan speed.
            dimming = CentralCommandDimming(
                percentage, 0, 1, 0, 0, int(percentage > 0)
            )
            msg = A5_38_08(command=0x02, dimming=dimming).encode_message(address)
        elif self.dev_eep == M5_38_08:
            # M5-38-08 is a relay, so every non-zero speed means on.
            switching = CentralCommandSwitching(0, 1, 0, 0, int(percentage > 0))
            msg = A5_38_08(command=0x01, switching=switching).encode_message(address)
        else:
            LOGGER.warning("[%s %s] Device EEP %s not supported.", Platform.FAN, self.dev_id, self.dev_eep.eep_string)
            return

        self.send_message(msg)
        if self.general_settings[CONF_FAST_STATUS_CHANGE]:
            self._attr_percentage = percentage
            self.schedule_update_ha_state()

    def value_changed(self, msg: ESP2Message) -> None:
        """Update speed from a fan status telegram."""
        try:
            decoded = self.dev_eep.decode_message(msg)
        except Exception as err:  # noqa: BLE001 - malformed telegrams are ignored
            LOGGER.warning("[%s %s] Could not decode message: %s", Platform.FAN, self.dev_id, err)
            return

        if self.dev_eep == A5_38_08:
            if decoded.command != 0x02 or decoded.dimming.learn_button != 1:
                return
            if decoded.dimming.switching_command == 0:
                self._attr_percentage = 0
            elif decoded.dimming.dimming_range == 0:
                self._attr_percentage = decoded.dimming.dimming_value
            else:
                self._attr_percentage = round(decoded.dimming.dimming_value / 255 * 100)
        elif self.dev_eep == M5_38_08:
            self._attr_percentage = 100 if decoded.state else 0
        else:
            return

        self.schedule_update_ha_state()
