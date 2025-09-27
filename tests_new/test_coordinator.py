"""Test the Eltako coordinator."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.eltako.coordinator import EltakoDataUpdateCoordinator
from custom_components.eltako.const import DOMAIN, DATA_ENTITIES


class TestEltakoDataUpdateCoordinator:
    """Test the Eltako data update coordinator."""

    def test_coordinator_init(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test coordinator initialization."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        assert coordinator.gateway == mock_gateway
        assert coordinator.config == mock_home_assistant_config
        assert coordinator.entry == mock_config_entry
        assert coordinator.name == DOMAIN
        assert coordinator.update_interval == timedelta(seconds=30)
        assert coordinator._entities == {}

    async def test_coordinator_update_data_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test successful data update."""
        mock_gateway.is_active.return_value = True

        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        data = await coordinator._async_update_data()

        assert "gateway_status" in data
        assert "entities" in data
        assert "last_update" in data
        assert data["gateway_status"]["is_active"] is True

    async def test_coordinator_update_data_gateway_inactive(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test data update with inactive gateway."""
        mock_gateway.is_active.return_value = False

        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        with pytest.raises(UpdateFailed, match="Gateway is not active"):
            await coordinator._async_update_data()

    async def test_coordinator_update_data_exception(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test data update with exception."""
        mock_gateway.is_active.side_effect = Exception("Connection error")

        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        with pytest.raises(UpdateFailed, match="Error communicating with gateway"):
            await coordinator._async_update_data()

    async def test_get_gateway_status(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test gateway status retrieval."""
        mock_gateway.dev_name = "Test Gateway"
        mock_gateway.device_type.value = "enocean-usb2"
        mock_gateway.base_id = "FF-AA-00-00"
        mock_gateway.serial_path = "/dev/ttyUSB0"
        mock_gateway.is_active.return_value = True
        mock_gateway.reconnect_count = 5

        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        status = await coordinator._get_gateway_status()

        assert status["name"] == "Test Gateway"
        assert status["device_type"] == "enocean-usb2"
        assert status["base_id"] == "FF-AA-00-00"
        assert status["serial_path"] == "/dev/ttyUSB0"
        assert status["is_active"] is True
        assert status["reconnect_count"] == 5

    def test_register_entity(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test entity registration."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_entity = MagicMock()
        entity_id = "test_entity_id"

        coordinator.register_entity(entity_id, mock_entity)

        assert coordinator._entities[entity_id] == mock_entity

    def test_unregister_entity(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test entity unregistration."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_entity = MagicMock()
        entity_id = "test_entity_id"
        coordinator._entities[entity_id] = mock_entity

        coordinator.unregister_entity(entity_id)

        assert entity_id not in coordinator._entities

    async def test_async_request_refresh_entity(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test requesting refresh for specific entity."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )
        coordinator.async_request_refresh = AsyncMock()

        mock_entity = MagicMock()
        entity_id = "test_entity_id"
        coordinator._entities[entity_id] = mock_entity

        await coordinator.async_request_refresh_entity(entity_id)

        coordinator.async_request_refresh.assert_called_once()

    async def test_async_request_refresh_entity_not_found(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test requesting refresh for non-existent entity."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )
        coordinator.async_request_refresh = AsyncMock()

        await coordinator.async_request_refresh_entity("non_existent_entity")

        coordinator.async_request_refresh.assert_not_called()

    async def test_async_shutdown(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test coordinator shutdown."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        # Add some entities
        coordinator._entities["entity1"] = MagicMock()
        coordinator._entities["entity2"] = MagicMock()

        # Setup hass data
        hass.data[DOMAIN] = {DATA_ENTITIES: {}}

        await coordinator.async_shutdown()

        assert len(coordinator._entities) == 0
        mock_gateway.unload.assert_called_once()
        assert DATA_ENTITIES not in hass.data.get(DOMAIN, {})

    async def test_async_shutdown_gateway_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test coordinator shutdown with gateway error."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_gateway.unload.side_effect = Exception("Shutdown error")

        # Should not raise exception
        await coordinator.async_shutdown()
        assert len(coordinator._entities) == 0

    def test_gateway_data_property(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test gateway_data property."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        # No data initially
        assert coordinator.gateway_data == {}

        # Set some data
        coordinator.data = {
            "gateway_status": {"name": "Test Gateway"},
            "entities": {},
        }

        assert coordinator.gateway_data == {"name": "Test Gateway"}

    def test_entities_data_property(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test entities_data property."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        # No data initially
        assert coordinator.entities_data == {}

        # Set some data
        test_entities = {"entity1": {"state": "on"}}
        coordinator.data = {
            "gateway_status": {},
            "entities": test_entities,
        }

        assert coordinator.entities_data == test_entities

    def test_get_entity_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test get_entity_data method."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        test_data = {"state": "on", "brightness": 255}
        coordinator.data = {
            "entities": {"test_entity": test_data}
        }

        assert coordinator.get_entity_data("test_entity") == test_data
        assert coordinator.get_entity_data("non_existent") is None

    async def test_async_update_entity_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test updating entity data."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_entity = MagicMock()
        mock_entity.async_write_ha_state = MagicMock()
        entity_id = "test_entity"

        coordinator._entities[entity_id] = mock_entity
        coordinator.data = {"entities": {}}

        new_data = {"state": "off"}
        await coordinator.async_update_entity_data(entity_id, new_data)

        assert coordinator.data["entities"][entity_id] == new_data
        mock_entity.async_write_ha_state.assert_called_once()

    async def test_async_update_entity_data_no_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test updating entity data when coordinator has no data."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )
        coordinator.async_refresh = AsyncMock()

        mock_entity = MagicMock()
        entity_id = "test_entity"
        coordinator._entities[entity_id] = mock_entity

        await coordinator.async_update_entity_data(entity_id, {"state": "on"})

        coordinator.async_refresh.assert_called_once()

    def test_is_gateway_available(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test gateway availability check."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_gateway.is_active.return_value = True

        # No successful update yet
        assert coordinator.is_gateway_available() is False

        # Simulate successful update
        coordinator.last_update_success = True
        assert coordinator.is_gateway_available() is True

        # Gateway becomes inactive
        mock_gateway.is_active.return_value = False
        assert coordinator.is_gateway_available() is False

    async def test_async_config_entry_first_refresh_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test successful first refresh."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_gateway.is_active.return_value = True

        # Should not raise exception
        await coordinator.async_config_entry_first_refresh()

    async def test_async_config_entry_first_refresh_failure(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test first refresh failure handling."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_gateway.is_active.side_effect = Exception("Connection failed")

        # Should not raise exception (logs warning and continues)
        await coordinator.async_config_entry_first_refresh()

    def test_add_entities_to_coordinator(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test adding multiple entities to coordinator."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        entities = []
        for i in range(3):
            entity = MagicMock()
            entity.unique_id = f"entity_{i}"
            entities.append(entity)

        coordinator.add_entities_to_coordinator(entities)

        assert len(coordinator._entities) == 3
        for i in range(3):
            assert f"entity_{i}" in coordinator._entities

    async def test_async_set_gateway_option_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test setting gateway option successfully."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )
        coordinator.async_request_refresh = AsyncMock()

        mock_gateway.set_auto_reconnect = MagicMock()

        await coordinator.async_set_gateway_option("auto_reconnect", True)

        mock_gateway.set_auto_reconnect.assert_called_once_with(True)
        coordinator.async_request_refresh.assert_called_once()

    async def test_async_set_gateway_option_async_setter(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test setting gateway option with async setter."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )
        coordinator.async_request_refresh = AsyncMock()

        mock_gateway.set_message_delay = AsyncMock()

        await coordinator.async_set_gateway_option("message_delay", 0.5)

        mock_gateway.set_message_delay.assert_called_once_with(0.5)
        coordinator.async_request_refresh.assert_called_once()

    async def test_async_set_gateway_option_not_supported(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test setting unsupported gateway option."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        # Should not raise exception, just log warning
        await coordinator.async_set_gateway_option("unsupported_option", "value")

    async def test_async_set_gateway_option_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test error handling when setting gateway option."""
        coordinator = EltakoDataUpdateCoordinator(
            hass, mock_config_entry, mock_gateway, mock_home_assistant_config
        )

        mock_gateway.set_auto_reconnect = MagicMock(side_effect=Exception("Setter error"))

        with pytest.raises(UpdateFailed, match="Failed to set gateway option"):
            await coordinator.async_set_gateway_option("auto_reconnect", True)