"""DataUpdateCoordinator for Eltako integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, DATA_ENTITIES

if TYPE_CHECKING:
    from .gateway import EnOceanGateway

_LOGGER = logging.getLogger(__name__)


class EltakoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the Eltako gateway."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        gateway: EnOceanGateway,
        config: ConfigType,
    ) -> None:
        """Initialize."""
        self.gateway = gateway
        self.config = config
        self.entry = entry
        self._entities: dict[str, Any] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            # For Eltako, the gateway manages its own data updates via events
            # We primarily use this for connection status and health checks
            data = {
                "gateway_status": await self._get_gateway_status(),
                "entities": self._entities,
                "last_update": self.last_update_success,
            }

            # Ensure gateway is connected
            if not self.gateway.is_active():
                _LOGGER.warning("Gateway %s is not active", self.gateway.dev_name)
                raise UpdateFailed("Gateway is not active")

            return data

        except Exception as err:
            _LOGGER.error("Error communicating with gateway %s: %s", self.gateway.dev_name, err)
            raise UpdateFailed(f"Error communicating with gateway: {err}") from err

    async def _get_gateway_status(self) -> dict[str, Any]:
        """Get gateway status information."""
        return {
            "name": self.gateway.dev_name,
            "device_type": self.gateway.device_type.value if self.gateway.device_type else None,
            "base_id": str(self.gateway.base_id) if self.gateway.base_id else None,
            "serial_path": self.gateway.serial_path,
            "is_active": self.gateway.is_active(),
            "reconnect_count": getattr(self.gateway, 'reconnect_count', 0),
        }

    def register_entity(self, entity_id: str, entity: Any) -> None:
        """Register an entity with the coordinator."""
        self._entities[entity_id] = entity
        _LOGGER.debug("Registered entity %s with coordinator", entity_id)

    def unregister_entity(self, entity_id: str) -> None:
        """Unregister an entity from the coordinator."""
        self._entities.pop(entity_id, None)
        _LOGGER.debug("Unregistered entity %s from coordinator", entity_id)

    async def async_request_refresh_entity(self, entity_id: str) -> None:
        """Request a refresh for a specific entity."""
        if entity_id in self._entities:
            await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator and clean up resources."""
        _LOGGER.debug("Shutting down coordinator for gateway %s", self.gateway.dev_name)

        # Clean up entities
        self._entities.clear()

        # Shutdown gateway
        if hasattr(self.gateway, 'unload'):
            try:
                self.gateway.unload()
            except Exception as err:
                _LOGGER.warning("Error during gateway shutdown: %s", err)

        # Clean up data storage
        if DATA_ENTITIES in self.hass.data.get(DOMAIN, {}):
            self.hass.data[DOMAIN].pop(DATA_ENTITIES, None)

    @property
    def gateway_data(self) -> dict[str, Any]:
        """Return gateway-specific data."""
        if not self.data:
            return {}
        return self.data.get("gateway_status", {})

    @property
    def entities_data(self) -> dict[str, Any]:
        """Return entities data."""
        if not self.data:
            return {}
        return self.data.get("entities", {})

    def get_entity_data(self, entity_id: str) -> Any | None:
        """Get data for a specific entity."""
        return self.entities_data.get(entity_id)

    async def async_update_entity_data(self, entity_id: str, data: Any) -> None:
        """Update data for a specific entity."""
        if entity_id in self._entities:
            # Update entity data in coordinator
            if not self.data:
                await self.async_refresh()

            if self.data and "entities" in self.data:
                self.data["entities"][entity_id] = data

            # Notify entity of update
            entity = self._entities.get(entity_id)
            if entity and hasattr(entity, 'async_write_ha_state'):
                entity.async_write_ha_state()

    def is_gateway_available(self) -> bool:
        """Check if the gateway is available."""
        return (
            self.last_update_success is not None
            and self.gateway.is_active()
        )

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh and handle setup errors."""
        try:
            await super().async_config_entry_first_refresh()
        except Exception as err:
            _LOGGER.error(
                "Error during first refresh for gateway %s: %s",
                self.gateway.dev_name,
                err
            )
            # For Eltako, we might want to continue even if initial refresh fails
            # as the gateway operates event-driven
            _LOGGER.warning(
                "Continuing setup for gateway %s despite initial refresh failure",
                self.gateway.dev_name
            )

    def add_entities_to_coordinator(self, entities: list[Any]) -> None:
        """Add multiple entities to the coordinator."""
        for entity in entities:
            if hasattr(entity, 'unique_id'):
                self.register_entity(entity.unique_id, entity)

    async def async_set_gateway_option(self, option: str, value: Any) -> None:
        """Set a gateway-specific option."""
        try:
            if hasattr(self.gateway, f'set_{option}'):
                setter = getattr(self.gateway, f'set_{option}')
                if asyncio.iscoroutinefunction(setter):
                    await setter(value)
                else:
                    setter(value)
                await self.async_request_refresh()
                _LOGGER.debug("Set gateway option %s to %s", option, value)
            else:
                _LOGGER.warning("Gateway option %s not supported", option)
        except Exception as err:
            _LOGGER.error("Error setting gateway option %s: %s", option, err)
            raise UpdateFailed(f"Failed to set gateway option {option}: {err}") from err