"""Test the Eltako light platform."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.const import Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)

from custom_components.eltako.light import (
    async_setup_entry,
    AbstractLightEntity,
    EltakoDimmableLight,
    EltakoSwitchableLight,
)
from custom_components.eltako.const import DOMAIN, CONF_SENDER
from custom_components.eltako.gateway import EnOceanGateway


class TestEltakoLightPlatform:
    """Test the Eltako light platform setup."""

    async def test_async_setup_entry_no_lights(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test light platform setup with no light configuration."""
        with patch("custom_components.eltako.light.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.light.get_device_config_for_gateway", return_value={}):
                mock_add_entities = MagicMock()

                await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                mock_add_entities.assert_called_once_with([])

    async def test_async_setup_entry_with_dimmable_lights(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test light platform setup with dimmable light configuration."""
        light_config = {
            Platform.LIGHT: [
                {
                    "id": "00-00-00-01",
                    "eep": "A5-38-08",
                    "name": "Dimmable Light",
                    "sender": {
                        "id": "00-00-B0-01",
                        "eep": "A5-38-08",
                    },
                },
            ]
        }

        with patch("custom_components.eltako.light.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.light.get_device_config_for_gateway", return_value=light_config):
                with patch("custom_components.eltako.light.DeviceConf") as mock_device_conf:
                    with patch("custom_components.eltako.config_helpers.get_device_conf") as mock_sender_conf:
                        mock_conf = MagicMock()
                        mock_conf.id = "00-00-00-01"
                        mock_conf.name = "Dimmable Light"
                        mock_conf.eep = "A5-38-08"
                        mock_device_conf.return_value = mock_conf

                        mock_sender = MagicMock()
                        mock_sender.id = "00-00-B0-01"
                        mock_sender.eep = "A5-38-08"
                        mock_sender_conf.return_value = mock_sender

                        mock_add_entities = MagicMock()

                        with patch("custom_components.eltako.light.A5_38_08", "A5-38-08"):
                            with patch("custom_components.eltako.light.validate_actuators_dev_and_sender_id"):
                                with patch("custom_components.eltako.light.log_entities_to_be_added"):
                                    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                                    mock_add_entities.assert_called_once()
                                    entities = mock_add_entities.call_args[0][0]
                                    assert len(entities) == 1
                                    assert isinstance(entities[0], EltakoDimmableLight)

    async def test_async_setup_entry_with_switchable_lights(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test light platform setup with switchable light configuration."""
        light_config = {
            Platform.LIGHT: [
                {
                    "id": "00-00-00-02",
                    "eep": "M5-38-08",
                    "name": "Switchable Light",
                    "sender": {
                        "id": "00-00-B0-02",
                        "eep": "M5-38-08",
                    },
                },
            ]
        }

        with patch("custom_components.eltako.light.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.light.get_device_config_for_gateway", return_value=light_config):
                with patch("custom_components.eltako.light.DeviceConf") as mock_device_conf:
                    with patch("custom_components.eltako.config_helpers.get_device_conf") as mock_sender_conf:
                        mock_conf = MagicMock()
                        mock_conf.id = "00-00-00-02"
                        mock_conf.name = "Switchable Light"
                        mock_conf.eep = "M5-38-08"
                        mock_device_conf.return_value = mock_conf

                        mock_sender = MagicMock()
                        mock_sender.id = "00-00-B0-02"
                        mock_sender.eep = "M5-38-08"
                        mock_sender_conf.return_value = mock_sender

                        mock_add_entities = MagicMock()

                        with patch("custom_components.eltako.light.M5_38_08", "M5-38-08"):
                            with patch("custom_components.eltako.light.validate_actuators_dev_and_sender_id"):
                                with patch("custom_components.eltako.light.log_entities_to_be_added"):
                                    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                                    mock_add_entities.assert_called_once()
                                    entities = mock_add_entities.call_args[0][0]
                                    assert len(entities) == 1
                                    assert isinstance(entities[0], EltakoSwitchableLight)

    async def test_async_setup_entry_error_handling(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test light platform setup error handling."""
        light_config = {
            Platform.LIGHT: [
                {
                    "id": "invalid-id",
                    "eep": "A5-38-08",
                    "name": "Invalid Light",
                },
            ]
        }

        with patch("custom_components.eltako.light.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.light.get_device_config_for_gateway", return_value=light_config):
                with patch("custom_components.eltako.light.DeviceConf", side_effect=Exception("Invalid config")):
                    mock_add_entities = MagicMock()

                    # Should handle errors gracefully
                    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                    # Should still call add_entities
                    mock_add_entities.assert_called_once()


class TestAbstractLightEntity:
    """Test the AbstractLightEntity base class."""

    def test_load_value_initially_on_state(self, mock_gateway):
        """Test loading initial state when light is on."""
        light = AbstractLightEntity(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Light",
            dev_eep="A5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "on"
        mock_state.attributes = {"brightness": 128}

        with patch.object(light, 'schedule_update_ha_state'):
            light.load_value_initially(mock_state)

            assert light.is_on is True
            assert light.brightness == 128

    def test_load_value_initially_off_state(self, mock_gateway):
        """Test loading initial state when light is off."""
        light = AbstractLightEntity(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Light",
            dev_eep="A5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "off"
        mock_state.attributes = {}

        with patch.object(light, 'schedule_update_ha_state'):
            light.load_value_initially(mock_state)

            assert light.is_on is False

    def test_load_value_initially_unknown_state(self, mock_gateway):
        """Test loading initial state when state is unknown."""
        light = AbstractLightEntity(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Light",
            dev_eep="A5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "unknown"
        mock_state.attributes = {}

        with patch.object(light, 'schedule_update_ha_state'):
            light.load_value_initially(mock_state)

            assert light.is_on is None

    def test_load_value_initially_invalid_state(self, mock_gateway):
        """Test loading initial state with invalid state value."""
        light = AbstractLightEntity(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Light",
            dev_eep="A5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "invalid"
        mock_state.attributes = {}

        with patch.object(light, 'schedule_update_ha_state'):
            light.load_value_initially(mock_state)

            assert light.is_on is None

    def test_load_value_initially_exception_handling(self, mock_gateway):
        """Test exception handling in load_value_initially."""
        light = AbstractLightEntity(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Test Light",
            dev_eep="A5-38-08",
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "on"
        mock_state.attributes = MagicMock()
        mock_state.attributes.get.side_effect = Exception("Attribute error")

        with patch.object(light, 'schedule_update_ha_state'):
            with pytest.raises(Exception):
                light.load_value_initially(mock_state)

            assert light.is_on is None


class TestEltakoDimmableLight:
    """Test the EltakoDimmableLight entity."""

    def test_dimmable_light_init(self, mock_gateway):
        """Test dimmable light initialization."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        assert light.color_mode == ColorMode.BRIGHTNESS
        assert ColorMode.BRIGHTNESS in light.supported_color_modes
        assert light._sender_id == "00-00-B0-01"
        assert light._sender_eep == "A5-38-08"

    def test_dimmable_light_turn_on_with_brightness(self, mock_gateway):
        """Test turning on dimmable light with specific brightness."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                light.turn_on(brightness=128)

                assert light.brightness == 128
                assert light.is_on is True
                mock_send.assert_called_once()

    def test_dimmable_light_turn_on_default_brightness(self, mock_gateway):
        """Test turning on dimmable light with default brightness."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                light.turn_on()

                assert light.brightness == 255
                assert light.is_on is True
                mock_send.assert_called_once()

    def test_dimmable_light_turn_off(self, mock_gateway):
        """Test turning off dimmable light."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        # Set initial state to on
        light._attr_is_on = True
        light._attr_brightness = 255

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                light.turn_off()

                assert light.is_on is False
                mock_send.assert_called_once()

    async def test_dimmable_light_async_turn_on(self, mock_gateway):
        """Test async turn on for dimmable light."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        with patch.object(light, 'turn_on') as mock_turn_on:
            await light.async_turn_on(brightness=200)

            mock_turn_on.assert_called_once_with(brightness=200)

    async def test_dimmable_light_async_turn_off(self, mock_gateway):
        """Test async turn off for dimmable light."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        with patch.object(light, 'turn_off') as mock_turn_off:
            await light.async_turn_off()

            mock_turn_off.assert_called_once()


class TestEltakoSwitchableLight:
    """Test the EltakoSwitchableLight entity."""

    def test_switchable_light_init(self, mock_gateway):
        """Test switchable light initialization."""
        light = EltakoSwitchableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Switchable Light",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-02",
            sender_eep="M5-38-08",
        )

        assert light.color_mode == ColorMode.ONOFF
        assert ColorMode.ONOFF in light.supported_color_modes
        assert light._sender_id == "00-00-B0-02"
        assert light._sender_eep == "M5-38-08"

    def test_switchable_light_turn_on(self, mock_gateway):
        """Test turning on switchable light."""
        light = EltakoSwitchableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Switchable Light",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-02",
            sender_eep="M5-38-08",
        )

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                light.turn_on()

                assert light.is_on is True
                mock_send.assert_called_once()

    def test_switchable_light_turn_off(self, mock_gateway):
        """Test turning off switchable light."""
        light = EltakoSwitchableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Switchable Light",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-02",
            sender_eep="M5-38-08",
        )

        # Set initial state to on
        light._attr_is_on = True

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                light.turn_off()

                assert light.is_on is False
                mock_send.assert_called_once()

    def test_switchable_light_brightness_ignored(self, mock_gateway):
        """Test that brightness is ignored for switchable lights."""
        light = EltakoSwitchableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Switchable Light",
            dev_eep="M5-38-08",
            sender_id="00-00-B0-02",
            sender_eep="M5-38-08",
        )

        with patch.object(light, 'send_message') as mock_send:
            with patch.object(light, 'schedule_update_ha_state'):
                # Brightness should be ignored
                light.turn_on(brightness=128)

                assert light.is_on is True
                # Brightness should not be set for switchable lights
                assert getattr(light, 'brightness', None) is None
                mock_send.assert_called_once()


class TestEltakoLightIntegration:
    """Test light integration with Home Assistant."""

    async def test_light_entity_registry_integration(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test light entity registry integration."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        light.hass = hass
        light.entity_id = "light.dimmable_light"

        # Test unique ID
        assert light.unique_id is not None
        assert "00-00-00-01" in str(light.unique_id)

        # Test device info
        device_info = light.device_info
        assert device_info is not None
        assert isinstance(device_info, dict)

    async def test_light_availability(self, mock_gateway):
        """Test light availability based on gateway status."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        # Mock gateway active state
        mock_gateway.is_active.return_value = True
        assert light.available is True

        mock_gateway.is_active.return_value = False
        assert light.available is False

    async def test_light_state_machine_integration(
        self,
        hass: HomeAssistant,
        mock_gateway,
    ):
        """Test light state machine integration."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        light.hass = hass
        light.entity_id = "light.dimmable_light"

        with patch.object(light, 'async_write_ha_state') as mock_write_state:
            # Test state updates
            light._attr_is_on = True
            light._attr_brightness = 180

            await light.async_update()
            # Update mechanism should work without errors

    async def test_light_coordinator_integration(
        self,
        hass: HomeAssistant,
        mock_coordinator,
        mock_gateway,
    ):
        """Test light integration with data coordinator."""
        light = EltakoDimmableLight(
            platform=Platform.LIGHT,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Dimmable Light",
            dev_eep="A5-38-08",
            sender_id="00-00-B0-01",
            sender_eep="A5-38-08",
        )

        # Test coordinator data updates
        light.coordinator = mock_coordinator
        light.hass = hass

        # Simulate coordinator data update
        if hasattr(light, 'coordinator_context'):
            mock_coordinator.data = {
                "entities": {
                    "00-00-00-01": {"state": "on", "brightness": 200}
                }
            }

            # Should handle coordinator updates
            with patch.object(light, 'async_write_ha_state'):
                await light.async_update()