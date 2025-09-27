"""Legacy support module for backward compatibility."""
from __future__ import annotations

import logging
import warnings

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import (
    async_setup_entry as new_async_setup_entry,
    async_unload_entry as new_async_unload_entry,
    get_gateway_from_hass,
    get_device_config_for_gateway,
    migrate_old_gateway_descriptions,
)

_LOGGER = logging.getLogger(__name__)

# Legacy support - these functions are deprecated and redirect to new implementations
warnings.warn(
    "eltako_integration_init module is deprecated. Import directly from __init__.py",
    DeprecationWarning,
    stacklevel=2
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Legacy setup function."""
    _LOGGER.warning("Using deprecated async_setup from eltako_integration_init")
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Legacy setup entry function - redirects to new implementation."""
    _LOGGER.warning("Using deprecated async_setup_entry from eltako_integration_init")
    return await new_async_setup_entry(hass, config_entry)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Legacy unload entry function - redirects to new implementation."""
    _LOGGER.warning("Using deprecated async_unload_entry from eltako_integration_init")
    return await new_async_unload_entry(hass, config_entry)


# Re-export legacy functions for backward compatibility
__all__ = [
    "async_setup",
    "async_setup_entry",
    "async_unload_entry",
    "get_gateway_from_hass",
    "get_device_config_for_gateway",
    "migrate_old_gateway_descriptions",
]