"""Test the Eltako switch platform."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.const import Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from custom_components.eltako.switch import (
    async_setup_entry,
    EltakoSwitch,
)
from custom_components.eltako.const import DOMAIN, CONF_SENDER
from custom_components.eltako.gateway import EnOceanGateway


class TestEltakoSwitchPlatform:
    """Test the Eltako switch platform setup."""

    async def test_async_setup_entry_no_switches(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test switch platform setup with no switch configuration."""
        with patch("custom_components.eltako.switch.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.switch.get_device_config_for_gateway", return_value={}):
                mock_add_entities = MagicMock()

                await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                mock_add_entities.assert_called_once_with([])

    async def test_async_setup_entry_with_switches(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test switch platform setup with switch configuration."""
        switch_config = {
            Platform.SWITCH: [
                {
                    "id": "00-00-00-01",
                    "eep": "M5-38-08",
                    "name": "Test Switch",
                    "sender": {
                        "id": "00-00-B0-01",
                        "eep": "M5-38-08",
                    },
                },
                {
                    "id": "00-00-00-02",
                    "eep": "D5-00-01",
                    "name": "Another Switch",
                    "sender": {
                        "id": "00-00-B0-02",
                        "eep": "D5-00-01",
                    },
                },
            ]
        }

        with patch("custom_components.eltako.switch.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.switch.get_device_config_for_gateway", return_value=switch_config):
                with patch("custom_components.eltako.switch.DeviceConf") as mock_device_conf:
                    with patch("custom_components.eltako.config_helpers.get_device_conf") as mock_sender_conf:
                        # Mock first switch config
                        mock_conf1 = MagicMock()
                        mock_conf1.id = "00-00-00-01"
                        mock_conf1.name = "Test Switch"
                        mock_conf1.eep = "M5-38-08"

                        # Mock second switch config
                        mock_conf2 = MagicMock()
                        mock_conf2.id = "00-00-00-02"
                        mock_conf2.name = "Another Switch"
                        mock_conf2.eep = "D5-00-01"

                        mock_device_conf.side_effect = [mock_conf1, mock_conf2]

                        # Mock sender configs
                        mock_sender1 = MagicMock()
                        mock_sender1.id = "00-00-B0-01"
                        mock_sender1.eep = "M5-38-08"

                        mock_sender2 = MagicMock()
                        mock_sender2.id = "00-00-B0-02"
                        mock_sender2.eep = "D5-00-01"

                        mock_sender_conf.side_effect = [mock_sender1, mock_sender2]

                        mock_add_entities = MagicMock()

                        with patch("custom_components.eltako.switch.validate_actuators_dev_and_sender_id"):
                            with patch("custom_components.eltako.switch.log_entities_to_be_added"):
                                await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                                mock_add_entities.assert_called_once()
                                entities = mock_add_entities.call_args[0][0]
                                assert len(entities) == 2
                                assert all(isinstance(e, EltakoSwitch) for e in entities)

    async def test_async_setup_entry_error_handling(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test switch platform setup error handling."""
        switch_config = {
            Platform.SWITCH: [
                {
                    "id": "invalid-id",
                    "eep": "M5-38-08",
                    "name": "Invalid Switch",
                },
            ]
        }

        with patch("custom_components.eltako.switch.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.switch.get_device_config_for_gateway", return_value=switch_config):
                with patch("custom_components.eltako.switch.DeviceConf", side_effect=Exception("Invalid config")):
                    mock_add_entities = MagicMock()

                    # Should handle errors gracefully
                    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                    # Should still call add_entities
                    mock_add_entities.assert_called_once()

    async def test_async_setup_entry_missing_sender_config(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test switch platform setup with missing sender configuration."""
        switch_config = {
            Platform.SWITCH: [
                {
                    "id": "00-00-00-01",
                    "eep": "M5-38-08",
                    "name": "Test Switch",
                    # Missing sender config
                },
            ]
        }

        with patch("custom_components.eltako.switch.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.switch.get_device_config_for_gateway", return_value=switch_config):
                with patch("custom_components.eltako.switch.DeviceConf") as mock_device_conf:
                    with patch("custom_components.eltako.config_helpers.get_device_conf", side_effect=Exception("No sender")):
                        mock_conf = MagicMock()
                        mock_conf.id = "00-00-00-01"
                        mock_conf.name = "Test Switch"
                        mock_conf.eep = "M5-38-08"
                        mock_device_conf.return_value = mock_conf

                        mock_add_entities = MagicMock()

                        # Should handle missing sender gracefully
                        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                        mock_add_entities.assert_called_once()


class TestEltakoSwitch:
    """Test the EltakoSwitch entity."""

    def test_switch_init(self, mock_gateway):
        """Test switch initialization."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        assert switch._sender_id == "00-00-B0-01"
        assert switch._sender_eep == "M5-38-08"
        assert switch.name == "Test Switch"
        assert switch.dev_id == "00-00-00-01"

    def test_load_value_initially_on_state(self, mock_gateway):
        """Test loading initial state when switch is on."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "on"

        with patch.object(switch, 'schedule_update_ha_state'):
            switch.load_value_initially(mock_state)

            assert switch.is_on is True

    def test_load_value_initially_off_state(self, mock_gateway):
        """Test loading initial state when switch is off."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "off"

        with patch.object(switch, 'schedule_update_ha_state'):
            switch.load_value_initially(mock_state)

            assert switch.is_on is False

    def test_load_value_initially_unknown_state(self, mock_gateway):
        """Test loading initial state when state is unknown."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "unknown"

        with patch.object(switch, 'schedule_update_ha_state'):
            switch.load_value_initially(mock_state)

            assert switch.is_on is None

    def test_load_value_initially_invalid_state(self, mock_gateway):
        """Test loading initial state with invalid state value."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "invalid"

        with patch.object(switch, 'schedule_update_ha_state'):
            switch.load_value_initially(mock_state)

            assert switch.is_on is None

    def test_load_value_initially_exception_handling(self, mock_gateway):
        """Test exception handling in load_value_initially."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = MagicMock()
        mock_state.state.__eq__ = MagicMock(side_effect=Exception("State error"))

        with patch.object(switch, 'schedule_update_ha_state'):
            with pytest.raises(Exception):
                switch.load_value_initially(mock_state)

            assert switch.is_on is None

    def test_switch_turn_on(self, mock_gateway):
        """Test turning on the switch."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        with patch.object(switch, 'send_message') as mock_send:
            with patch.object(switch, 'schedule_update_ha_state'):
                switch.turn_on()

                assert switch.is_on is True
                mock_send.assert_called_once()

    def test_switch_turn_off(self, mock_gateway):
        """Test turning off the switch."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        # Set initial state to on
        switch._attr_is_on = True

        with patch.object(switch, 'send_message') as mock_send:
            with patch.object(switch, 'schedule_update_ha_state'):
                switch.turn_off()

                assert switch.is_on is False
                mock_send.assert_called_once()

    async def test_switch_async_turn_on(self, mock_gateway):
        """Test async turn on for switch."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        with patch.object(switch, 'turn_on') as mock_turn_on:
            await switch.async_turn_on()

            mock_turn_on.assert_called_once()

    async def test_switch_async_turn_off(self, mock_gateway):
        """Test async turn off for switch."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        with patch.object(switch, 'turn_off') as mock_turn_off:
            await switch.async_turn_off()

            mock_turn_off.assert_called_once()

    def test_switch_unique_id(self, mock_gateway):
        """Test switch unique ID generation."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        # Unique ID should be based on gateway and device ID
        assert switch.unique_id is not None
        assert "00-00-00-01" in str(switch.unique_id)

    def test_switch_device_info(self, mock_gateway):
        """Test switch device info."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        device_info = switch.device_info
        assert device_info is not None
        assert isinstance(device_info, dict)

    async def test_switch_availability(self, mock_gateway):
        """Test switch availability based on gateway status."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        # Mock gateway active state
        mock_gateway.is_active.return_value = True
        assert switch.available is True

        mock_gateway.is_active.return_value = False
        assert switch.available is False

    async def test_switch_message_handling(self, mock_gateway):
        """Test switch message handling from gateway."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        # Test message received callback if it exists
        if hasattr(switch, 'value_received'):
            with patch.object(switch, 'schedule_update_ha_state') as mock_update:
                switch.value_received(mock_gateway, "00-00-00-01", True)

                assert switch.is_on is True
                mock_update.assert_called_once()


class TestEltakoSwitchIntegration:
    """Test switch integration with Home Assistant."""

    async def test_switch_entity_registry_integration(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test switch entity registry integration."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        switch.hass = hass
        switch.entity_id = "switch.test_switch"

        # Test unique ID
        assert switch.unique_id is not None
        assert "00-00-00-01" in str(switch.unique_id)

        # Test device info
        device_info = switch.device_info
        assert device_info is not None
        assert isinstance(device_info, dict)

    async def test_switch_state_machine_integration(
        self,
        hass: HomeAssistant,
        mock_gateway,
    ):
        """Test switch state machine integration."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        switch.hass = hass
        switch.entity_id = "switch.test_switch"

        with patch.object(switch, 'async_write_ha_state') as mock_write_state:
            # Test state updates
            switch._attr_is_on = True

            await switch.async_update()
            # Update mechanism should work without errors

    async def test_switch_coordinator_integration(
        self,
        hass: HomeAssistant,
        mock_coordinator,
        mock_gateway,
    ):
        """Test switch integration with data coordinator."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        # Test coordinator data updates
        switch.coordinator = mock_coordinator
        switch.hass = hass

        # Simulate coordinator data update
        if hasattr(switch, 'coordinator_context'):
            mock_coordinator.data = {
                "entities": {
                    "00-00-00-01": {"state": "on"}
                }
            }

            # Should handle coordinator updates
            with patch.object(switch, 'async_write_ha_state'):
                await switch.async_update()

    async def test_switch_service_calls(
        self,
        hass: HomeAssistant,
        mock_gateway,
    ):
        """Test switch service calls from Home Assistant."""
        switch = EltakoSwitch(
            platform=Platform.SWITCH,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Switch",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="M5-38-08",
        )

        switch.hass = hass
        switch.entity_id = "switch.test_switch"

        # Test turn_on service
        with patch.object(switch, 'send_message') as mock_send:
            with patch.object(switch, 'schedule_update_ha_state'):
                await hass.services.async_call(
                    "switch",
                    "turn_on",
                    {"entity_id": "switch.test_switch"},
                    blocking=True,
                )

        # Test turn_off service
        with patch.object(switch, 'send_message') as mock_send:
            with patch.object(switch, 'schedule_update_ha_state'):
                await hass.services.async_call(
                    "switch",
                    "turn_off",
                    {"entity_id": "switch.test_switch"},
                    blocking=True,
                )