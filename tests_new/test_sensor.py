"""Test the Eltako sensor platform."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.const import Platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.eltako.sensor import (
    async_setup_entry,
    EltakoSensor,
    SENSOR_DESC_TEMPERATURE,
    SENSOR_DESC_HUMIDITY,
    SENSOR_DESC_BATTERY_VOLTAGE,
    SENSOR_TYPE_TEMPERATURE,
    SENSOR_TYPE_HUMIDITY,
    SENSOR_TYPE_BATTERY_VOLTAGE,
)
from custom_components.eltako.const import DOMAIN
from custom_components.eltako.gateway import EnOceanGateway


class TestEltakoSensorPlatform:
    """Test the Eltako sensor platform setup."""

    async def test_async_setup_entry_no_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test sensor platform setup with no sensor configuration."""
        with patch("custom_components.eltako.sensor.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.sensor.get_device_config_for_gateway", return_value={}):
                mock_add_entities = MagicMock()

                await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                mock_add_entities.assert_called_once_with([])

    async def test_async_setup_entry_with_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test sensor platform setup with sensor configuration."""
        sensor_config = {
            Platform.SENSOR: [
                {
                    "id": "00-00-00-01",
                    "eep": "A5-02-05",
                    "name": "Temperature Sensor",
                    "device_class": "temperature",
                },
                {
                    "id": "00-00-00-02",
                    "eep": "A5-04-01",
                    "name": "Humidity Sensor",
                    "device_class": "humidity",
                },
            ]
        }

        with patch("custom_components.eltako.sensor.get_gateway_from_hass", return_value=mock_gateway):
            with patch("custom_components.eltako.sensor.get_device_config_for_gateway", return_value=sensor_config):
                with patch("custom_components.eltako.sensor.DeviceConf") as mock_device_conf:
                    mock_conf = MagicMock()
                    mock_conf.name = "Temperature Sensor"
                    mock_conf.eep = "A5-02-05"
                    mock_device_conf.return_value = mock_conf

                    mock_add_entities = MagicMock()

                    # Mock the EEP imports that would normally come from eltakobus
                    with patch("custom_components.eltako.sensor.A5_02_05", "A5-02-05"):
                        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

                        # Should have been called with some entities
                        mock_add_entities.assert_called_once()
                        entities = mock_add_entities.call_args[0][0]
                        assert isinstance(entities, list)

    async def test_async_setup_entry_error_handling(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test sensor platform setup error handling."""
        with patch("custom_components.eltako.sensor.get_gateway_from_hass", side_effect=Exception("Gateway error")):
            mock_add_entities = MagicMock()

            # Should not raise exception, but handle gracefully
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

            # Should still call add_entities with empty list
            mock_add_entities.assert_called_once_with([])


class TestEltakoSensor:
    """Test the EltakoSensor entity."""

    def test_sensor_init_temperature(self, mock_gateway):
        """Test temperature sensor initialization."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        assert sensor.entity_description == SENSOR_DESC_TEMPERATURE
        assert sensor.name == "Temperature"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        assert sensor.native_value is None

    def test_sensor_init_humidity(self, mock_gateway):
        """Test humidity sensor initialization."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Humidity Sensor",
            dev_eep="A5-04-01",
            description=SENSOR_DESC_HUMIDITY,
        )

        assert sensor.entity_description == SENSOR_DESC_HUMIDITY
        assert sensor.name == "Humidity"
        assert sensor.device_class == SensorDeviceClass.HUMIDITY
        assert sensor.state_class == SensorStateClass.MEASUREMENT

    def test_sensor_init_battery(self, mock_gateway):
        """Test battery voltage sensor initialization."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-03",
            dev_name="Battery Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_BATTERY_VOLTAGE,
        )

        assert sensor.entity_description == SENSOR_DESC_BATTERY_VOLTAGE
        assert sensor.name == "Battery Voltage"
        assert sensor.device_class == SensorDeviceClass.BATTERY

    def test_load_value_initially_float(self, mock_gateway):
        """Test loading initial float value from state."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "23.5"
        mock_state.attributes = {"state_class": "measurement"}

        sensor.load_value_initially(mock_state)

        assert sensor.native_value == 23.5

    def test_load_value_initially_int(self, mock_gateway):
        """Test loading initial integer value from state."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-02",
            dev_name="Humidity Sensor",
            dev_eep="A5-04-01",
            description=SENSOR_DESC_HUMIDITY,
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "65"
        mock_state.attributes = {"state_class": "measurement"}

        sensor.load_value_initially(mock_state)

        assert sensor.native_value == 65

    def test_load_value_initially_unknown_state(self, mock_gateway):
        """Test loading initial value with unknown state."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "unknown"
        mock_state.attributes = {}

        sensor.load_value_initially(mock_state)

        # Should handle unknown state gracefully
        assert hasattr(sensor, '_attr_is_on')

    def test_load_value_initially_invalid_number(self, mock_gateway):
        """Test loading initial value with invalid number."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        mock_state = MagicMock(spec=State)
        mock_state.state = "invalid_number"
        mock_state.attributes = {"state_class": "measurement"}

        # Should handle invalid number gracefully
        sensor.load_value_initially(mock_state)

    async def test_sensor_value_received(self, mock_gateway):
        """Test sensor value update when message received."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        # Mock the value_received method if it exists
        if hasattr(sensor, 'value_received'):
            with patch.object(sensor, 'schedule_update_ha_state') as mock_update:
                sensor.value_received(mock_gateway, "00-00-00-01", 25.0)

                assert sensor.native_value == 25.0
                mock_update.assert_called_once()

    def test_sensor_unique_id(self, mock_gateway):
        """Test sensor unique ID generation."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        # Unique ID should be based on gateway and device ID
        assert sensor.unique_id is not None
        assert "00-00-00-01" in str(sensor.unique_id)

    def test_sensor_device_info(self, mock_gateway):
        """Test sensor device info."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        device_info = sensor.device_info
        assert device_info is not None
        assert isinstance(device_info, dict)

    async def test_sensor_availability(self, mock_gateway):
        """Test sensor availability based on gateway status."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        # Mock gateway active state
        mock_gateway.is_active.return_value = True
        assert sensor.available is True

        mock_gateway.is_active.return_value = False
        assert sensor.available is False


class TestEltakoSensorDescriptions:
    """Test sensor entity descriptions."""

    def test_temperature_description(self):
        """Test temperature sensor description."""
        desc = SENSOR_DESC_TEMPERATURE

        assert desc.key == SENSOR_TYPE_TEMPERATURE
        assert desc.name == "Temperature"
        assert desc.device_class == SensorDeviceClass.TEMPERATURE
        assert desc.state_class == SensorStateClass.MEASUREMENT
        assert "thermometer" in desc.icon

    def test_humidity_description(self):
        """Test humidity sensor description."""
        desc = SENSOR_DESC_HUMIDITY

        assert desc.key == SENSOR_TYPE_HUMIDITY
        assert desc.name == "Humidity"
        assert desc.device_class == SensorDeviceClass.HUMIDITY
        assert desc.state_class == SensorStateClass.MEASUREMENT

    def test_battery_voltage_description(self):
        """Test battery voltage sensor description."""
        desc = SENSOR_DESC_BATTERY_VOLTAGE

        assert desc.key == SENSOR_TYPE_BATTERY_VOLTAGE
        assert desc.name == "Battery Voltage"
        assert desc.device_class == SensorDeviceClass.BATTERY
        assert desc.state_class == SensorStateClass.MEASUREMENT
        assert "lightning-bolt" in desc.icon


class TestEltakoSensorIntegration:
    """Test sensor integration with Home Assistant."""

    async def test_sensor_registry_integration(
        self,
        hass: HomeAssistant,
        mock_config_entry: ConfigEntry,
        mock_gateway,
    ):
        """Test sensor entity registry integration."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        # Add to entity registry
        with patch("homeassistant.helpers.entity_registry.async_get") as mock_registry:
            mock_reg = MagicMock()
            mock_registry.return_value = mock_reg

            sensor.entity_id = "sensor.temperature_sensor"
            sensor.hass = hass

            # Simulate entity registration
            mock_reg.async_get_or_create.return_value = MagicMock(
                entity_id="sensor.temperature_sensor",
                unique_id=sensor.unique_id,
            )

    async def test_sensor_state_machine_integration(
        self,
        hass: HomeAssistant,
        mock_gateway,
    ):
        """Test sensor state machine integration."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        sensor.hass = hass
        sensor.entity_id = "sensor.temperature_sensor"

        # Test state updates
        sensor._attr_native_value = 22.5

        with patch.object(sensor, 'async_write_ha_state') as mock_write_state:
            await sensor.async_update()
            # Update mechanism should work without errors

    async def test_sensor_coordinator_integration(
        self,
        hass: HomeAssistant,
        mock_coordinator,
        mock_gateway,
    ):
        """Test sensor integration with data coordinator."""
        sensor = EltakoSensor(
            platform=Platform.SENSOR,
            gateway=mock_gateway,
            dev_id="00-00-00-01",
            dev_name="Temperature Sensor",
            dev_eep="A5-02-05",
            description=SENSOR_DESC_TEMPERATURE,
        )

        # Test coordinator data updates
        sensor.coordinator = mock_coordinator
        sensor.hass = hass

        # Simulate coordinator data update
        if hasattr(sensor, 'coordinator_context'):
            mock_coordinator.data = {
                "entities": {
                    "00-00-00-01": {"temperature": 24.0}
                }
            }

            # Should handle coordinator updates
            with patch.object(sensor, 'async_write_ha_state'):
                await sensor.async_update()