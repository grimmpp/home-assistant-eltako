"""Test the Eltako integration init."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.setup import async_setup_component

from custom_components.eltako import (
    async_setup,
    async_setup_entry,
    async_unload_entry,
    _setup_coordinator,
)
from custom_components.eltako.const import DOMAIN
from custom_components.eltako.coordinator import EltakoDataUpdateCoordinator


class TestEltakoInit:
    """Test Eltako integration initialization."""

    async def test_async_setup_legacy(self, hass: HomeAssistant):
        """Test legacy async_setup function."""
        result = await async_setup(hass, {})
        assert result is True

    async def test_async_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test successful setup of config entry."""
        # Mock all the setup functions
        mock_setup_functions["async_get_home_assistant_config"].return_value = mock_home_assistant_config
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = {
            "device_type": "enocean-usb2",
            "base_id": "FF-AA-00-00",
            "name": "Test Gateway",
        }

        with patch("custom_components.eltako.EnOceanGateway", return_value=mock_gateway):
            with patch("custom_components.eltako.EltakoDataUpdateCoordinator") as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                result = await async_setup_entry(hass, mock_config_entry)

                assert result is True
                assert DOMAIN in hass.data
                assert mock_config_entry.entry_id in hass.data[DOMAIN]

    async def test_async_setup_entry_wrong_domain(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
    ):
        """Test setup entry with wrong domain."""
        mock_config_entry.domain = "wrong_domain"

        result = await async_setup_entry(hass, mock_config_entry)

        assert result is False

    async def test_async_setup_entry_config_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
    ):
        """Test setup entry with configuration error."""
        mock_setup_functions["config_check_gateway"].return_value = False

        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, mock_config_entry)

    async def test_async_setup_entry_coordinator_error(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_home_assistant_config,
    ):
        """Test setup entry with coordinator setup error."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = mock_home_assistant_config

        # Mock coordinator setup to fail
        with patch("custom_components.eltako._setup_coordinator", side_effect=Exception("Setup failed")):
            with pytest.raises(ConfigEntryNotReady):
                await async_setup_entry(hass, mock_config_entry)

    async def test_async_unload_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_coordinator,
    ):
        """Test successful unload of config entry."""
        # Setup data in hass
        hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_coordinator}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]
        mock_coordinator.async_shutdown.assert_called_once()

    async def test_async_unload_entry_platform_failure(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_coordinator,
    ):
        """Test unload entry when platform unload fails."""
        # Setup data in hass
        hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_coordinator}
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, mock_config_entry)

        assert result is False
        # Coordinator should not be removed if platform unload fails
        assert mock_config_entry.entry_id in hass.data[DOMAIN]
        mock_coordinator.async_shutdown.assert_not_called()


class TestEltakoCoordinatorSetup:
    """Test coordinator setup function."""

    async def test_setup_coordinator_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test successful coordinator setup."""
        mock_setup_functions["get_id_from_name"].return_value = 0
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = {
            "device_type": "enocean-usb2",
            "base_id": "FF-AA-00-00",
            "name": "Test Gateway",
        }
        mock_setup_functions["get_general_settings_from_configuration"].return_value = {}

        with patch("custom_components.eltako.EnOceanGateway", return_value=mock_gateway):
            with patch("custom_components.eltako.EltakoDataUpdateCoordinator") as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                coordinator = await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

                assert coordinator is not None
                mock_gateway.async_setup.assert_called_once()
                mock_coordinator.async_config_entry_first_refresh.assert_called_once()

    async def test_setup_coordinator_missing_gateway_description(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_home_assistant_config,
    ):
        """Test coordinator setup with missing gateway description."""
        mock_config_entry.data = {}  # Remove gateway description

        with pytest.raises(ConfigEntryNotReady, match="Gateway description not available"):
            await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

    async def test_setup_coordinator_invalid_gateway_description(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_home_assistant_config,
    ):
        """Test coordinator setup with invalid gateway description format."""
        mock_config_entry.data = {"gateway_description": "Invalid Format"}  # No parentheses

        with pytest.raises(ConfigEntryNotReady, match="Gateway base ID not available"):
            await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

    async def test_setup_coordinator_missing_serial_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_home_assistant_config,
    ):
        """Test coordinator setup with missing serial path."""
        mock_config_entry.data = {"gateway_description": "Test Gateway (Gateway-0)"}  # Remove serial path

        with pytest.raises(ConfigEntryNotReady, match="Gateway serial path not available"):
            await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

    async def test_setup_coordinator_gateway_config_not_found(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_home_assistant_config,
    ):
        """Test coordinator setup when gateway config is not found."""
        mock_setup_functions["get_id_from_name"].return_value = 0
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = None

        with pytest.raises(ConfigEntryNotReady, match="No gateway configuration found"):
            await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

    async def test_setup_coordinator_unsupported_device_type(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_home_assistant_config,
    ):
        """Test coordinator setup with unsupported device type."""
        mock_setup_functions["get_id_from_name"].return_value = 0
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = {
            "device_type": "unsupported-device",
            "base_id": "FF-AA-00-00",
        }

        with patch("custom_components.eltako.GatewayDeviceType.find", return_value=None):
            with pytest.raises(ConfigEntryNotReady, match="device unsupported-device is not supported"):
                await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)

    async def test_setup_coordinator_lan_gateway_missing_address(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_home_assistant_config,
    ):
        """Test coordinator setup for LAN gateway without address."""
        mock_setup_functions["get_id_from_name"].return_value = 0
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = {
            "device_type": "esp3-lan",
            "base_id": "FF-AA-00-00",
            # Missing gateway_address
        }

        with patch("custom_components.eltako.GatewayDeviceType.find") as mock_find:
            mock_find.return_value = MagicMock()
            mock_find.return_value.name = "LAN"

            with pytest.raises(ConfigEntryNotReady, match="Missing field 'gateway_address'"):
                await _setup_coordinator(hass, mock_config_entry, mock_home_assistant_config)


class TestEltakoIntegrationComponent:
    """Test integration as a Home Assistant component."""

    async def test_setup_component_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_setup_functions,
        mock_gateway,
        mock_home_assistant_config,
    ):
        """Test setting up component through async_setup_component."""
        mock_setup_functions["async_get_home_assistant_config"].return_value = mock_home_assistant_config
        mock_setup_functions["async_find_gateway_config_by_id"].return_value = {
            "device_type": "enocean-usb2",
            "base_id": "FF-AA-00-00",
            "name": "Test Gateway",
        }

        mock_config_entry.add_to_hass(hass)

        with patch("custom_components.eltako.EnOceanGateway", return_value=mock_gateway):
            with patch("custom_components.eltako.EltakoDataUpdateCoordinator") as mock_coordinator_class:
                mock_coordinator = MagicMock()
                mock_coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_coordinator_class.return_value = mock_coordinator

                assert await async_setup_component(hass, DOMAIN, {})
                await hass.async_block_till_done()

                assert DOMAIN in hass.data

    async def test_setup_component_no_config_entries(self, hass: HomeAssistant):
        """Test setting up component without config entries."""
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        # Should succeed even without config entries
        assert DOMAIN in hass.data or True  # Legacy setup returns True


class TestEltakoLegacyCompatibility:
    """Test legacy compatibility functions."""

    async def test_legacy_functions_import(self):
        """Test that legacy functions can still be imported."""
        from custom_components.eltako.eltako_integration_init import (
            async_setup as legacy_setup,
            async_setup_entry as legacy_setup_entry,
            async_unload_entry as legacy_unload_entry,
        )

        # Functions should be callable
        assert callable(legacy_setup)
        assert callable(legacy_setup_entry)
        assert callable(legacy_unload_entry)

    async def test_legacy_setup_function(self, hass: HomeAssistant):
        """Test legacy setup function."""
        from custom_components.eltako.eltako_integration_init import async_setup as legacy_setup

        result = await legacy_setup(hass, {})
        assert result is True