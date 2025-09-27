"""Support for Eltako devices."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    DATA_ELTAKO,
    ELTAKO_CONFIG,
    PLATFORMS,
    CONF_GATEWAY_DESCRIPTION,
    CONF_SERIAL_PATH,
    CONF_DEVICE_TYPE,
    CONF_GATEWAY_ADDRESS,
    CONF_GATEWAY_PORT,
    CONF_GATEWAY_AUTO_RECONNECT,
    CONF_BASE_ID,
    CONF_GATEWAY_MESSAGE_DELAY,
    CONF_ENABLE_TEACH_IN_BUTTONS,
    BAUD_RATE_DEVICE_TYPE_MAPPING,
)
from .coordinator import EltakoDataUpdateCoordinator
from .gateway import EnOceanGateway, GatewayDeviceType
from .schema import CONFIG_SCHEMA
from . import config_helpers

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

LOG_PREFIX = "Eltako Integration Setup"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Eltako component from YAML (legacy)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Eltako from a config entry."""
    _LOGGER.info("[%s] Start gateway setup for entry %s", LOG_PREFIX, entry.entry_id)

    # Validate domain
    if entry.domain != DOMAIN:
        _LOGGER.error(
            "[%s] Wrong domain %s (expected: %s)!",
            LOG_PREFIX, entry.domain, DOMAIN
        )
        return False

    # Ensure dependencies are installed
    from .dependency_check import ensure_dependencies_installed
    if not await ensure_dependencies_installed(hass):
        raise ConfigEntryNotReady("Eltako dependencies are not available")

    # Initialize data storage
    hass.data.setdefault(DOMAIN, {})

    try:
        # Read Home Assistant configuration
        config = await config_helpers.async_get_home_assistant_config(hass, CONFIG_SCHEMA)

        # Check gateway ID uniqueness
        if not config_helpers.config_check_gateway(config):
            raise ConfigEntryNotReady("Gateway IDs are not unique")

        # Store config for global access
        eltako_data = hass.data.setdefault(DATA_ELTAKO, {})
        eltako_data[ELTAKO_CONFIG] = config

        # Setup coordinator and gateway
        coordinator = await _setup_coordinator(hass, entry, config)
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("[%s] Successfully set up gateway %s", LOG_PREFIX, entry.title)
        return True

    except Exception as err:
        _LOGGER.error("[%s] Failed to setup entry: %s", LOG_PREFIX, err)
        raise ConfigEntryNotReady(f"Failed to setup Eltako integration: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("[%s] Unloading entry %s", LOG_PREFIX, entry.entry_id)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up data and gateway
    if unload_ok:
        coordinator: EltakoDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        _LOGGER.info("[%s] Successfully unloaded entry %s", LOG_PREFIX, entry.entry_id)

    return unload_ok


async def _setup_coordinator(
    hass: HomeAssistant, entry: ConfigEntry, config: ConfigType
) -> EltakoDataUpdateCoordinator:
    """Set up the Eltako coordinator."""
    # Import external dependencies here after they have been installed
    from eltakobus.util import AddressExpression

    # Extract config entry data
    gateway_description = entry.data.get(CONF_GATEWAY_DESCRIPTION)
    if not gateway_description:
        raise ConfigEntryNotReady("Gateway description not available")

    if not ('(' in gateway_description and ')' in gateway_description):
        raise ConfigEntryNotReady("Gateway base ID not available in description")

    gateway_serial_path = entry.data.get(CONF_SERIAL_PATH)
    if not gateway_serial_path:
        raise ConfigEntryNotReady("Gateway serial path not available")

    # Parse gateway ID from description
    gateway_id = config_helpers.get_id_from_name(gateway_description)

    # Get gateway configuration
    gateway_config = await config_helpers.async_find_gateway_config_by_id(
        gateway_id, hass, CONFIG_SCHEMA
    )
    if not gateway_config:
        raise ConfigEntryNotReady(
            f"No gateway configuration found for ID {gateway_id}"
        )

    # Validate device type
    gateway_device_type = GatewayDeviceType.find(gateway_config[CONF_DEVICE_TYPE])
    if gateway_device_type is None:
        raise ConfigEntryNotReady(
            f"USB device {gateway_config[CONF_DEVICE_TYPE]} is not supported"
        )

    # LAN gateway specific validation
    if gateway_device_type == GatewayDeviceType.LAN:
        if gateway_config.get(CONF_GATEWAY_ADDRESS) is None:
            raise ConfigEntryNotReady(
                f"Missing field '{CONF_GATEWAY_ADDRESS}' for LAN Gateway"
            )

    # Get general settings
    general_settings = config_helpers.get_general_settings_from_configuration(hass)
    general_settings[CONF_ENABLE_TEACH_IN_BUTTONS] = True

    # Extract gateway parameters
    gateway_name = gateway_config.get(CONF_NAME)
    baud_rate = BAUD_RATE_DEVICE_TYPE_MAPPING[gateway_device_type]
    port = gateway_config.get(CONF_GATEWAY_PORT, 5100)
    auto_reconnect = gateway_config.get(CONF_GATEWAY_AUTO_RECONNECT, True)
    gateway_base_id = AddressExpression.parse(gateway_config[CONF_BASE_ID])
    message_delay = gateway_config.get(CONF_GATEWAY_MESSAGE_DELAY)

    _LOGGER.debug(
        "Gateway setup - ID: %s, Type: %s, Path: %s, Baud: %s, Base ID: %s",
        gateway_id, gateway_device_type, gateway_serial_path, baud_rate, gateway_base_id
    )

    # Create gateway
    gateway = EnOceanGateway(
        general_settings,
        hass,
        gateway_id,
        gateway_device_type,
        gateway_serial_path,
        baud_rate,
        port,
        gateway_base_id,
        gateway_name,
        auto_reconnect,
        message_delay,
        entry
    )

    # Setup gateway
    await gateway.async_setup()

    # Create and initialize coordinator
    coordinator = EltakoDataUpdateCoordinator(hass, entry, gateway, config)
    await coordinator.async_config_entry_first_refresh()

    return coordinator


# Legacy support functions (kept for compatibility)
def migrate_old_gateway_descriptions(hass: HomeAssistant) -> None:
    """Migrate old gateway descriptions for compatibility."""
    from .const import GATEWAY_DEFAULT_NAME, OLD_GATEWAY_DEFAULT_NAME

    if DATA_ELTAKO not in hass.data:
        return

    _LOGGER.debug("[%s] Migrating old gateway descriptions", LOG_PREFIX)
    migration_dict: dict = {}

    for key in list(hass.data[DATA_ELTAKO].keys()):
        if GATEWAY_DEFAULT_NAME in key:
            old_key = key.replace(GATEWAY_DEFAULT_NAME, OLD_GATEWAY_DEFAULT_NAME)
            _LOGGER.info(
                "[%s] Backward compatibility: '%s' -> '%s'",
                LOG_PREFIX, key, old_key
            )
            migration_dict[old_key] = hass.data[DATA_ELTAKO][key]

        if OLD_GATEWAY_DEFAULT_NAME in key:
            new_key = key.replace(OLD_GATEWAY_DEFAULT_NAME, GATEWAY_DEFAULT_NAME)
            _LOGGER.info(
                "[%s] Migrating gateway: '%s' -> '%s'",
                LOG_PREFIX, key, new_key
            )
            migration_dict[new_key] = hass.data[DATA_ELTAKO][key]

    # Apply migrations
    for key, value in migration_dict.items():
        hass.data[DATA_ELTAKO][key] = value


def get_gateway_from_hass(hass: HomeAssistant, config_entry: ConfigEntry) -> EnOceanGateway:
    """Get gateway from hass data (legacy support)."""
    migrate_old_gateway_descriptions(hass)

    coordinator: EltakoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    return coordinator.gateway


def get_device_config_for_gateway(
    hass: HomeAssistant, config_entry: ConfigEntry, gateway: EnOceanGateway
) -> ConfigType:
    """Get device config for gateway (legacy support)."""
    return config_helpers.get_device_config(
        hass.data[DATA_ELTAKO][ELTAKO_CONFIG], gateway.dev_id
    )