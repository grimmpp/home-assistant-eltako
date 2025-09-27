"""Test configuration for Eltako integration."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from custom_components.eltako.const import (
    DOMAIN,
    CONF_GATEWAY_DESCRIPTION,
    CONF_SERIAL_PATH,
    CONF_DEVICE_TYPE,
    CONF_BASE_ID,
    CONF_GATEWAY_PORT,
    CONF_GATEWAY_AUTO_RECONNECT,
    CONF_GATEWAY_MESSAGE_DELAY,
)
from custom_components.eltako.gateway import GatewayDeviceType


# Test data constants
TEST_GATEWAY_DESCRIPTION = "Test Gateway (Gateway-0)"
TEST_SERIAL_PATH = "/dev/ttyUSB0"
TEST_BASE_ID = "FF-AA-00-00"
TEST_DEVICE_TYPE = "enocean-usb2"


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Create a mock config entry for testing."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Eltako Test Gateway",
        data={
            CONF_GATEWAY_DESCRIPTION: TEST_GATEWAY_DESCRIPTION,
            CONF_SERIAL_PATH: TEST_SERIAL_PATH,
        },
        options={
            CONF_GATEWAY_AUTO_RECONNECT: True,
            CONF_GATEWAY_MESSAGE_DELAY: 0.0,
        },
        entry_id="test_entry_id",
        unique_id="test_unique_id",
    )


@pytest.fixture
def mock_gateway_config() -> dict:
    """Create a mock gateway configuration."""
    return {
        CONF_NAME: "Test Gateway",
        CONF_DEVICE_TYPE: TEST_DEVICE_TYPE,
        CONF_BASE_ID: TEST_BASE_ID,
        CONF_GATEWAY_PORT: 5100,
        CONF_GATEWAY_AUTO_RECONNECT: True,
        CONF_GATEWAY_MESSAGE_DELAY: 0.0,
    }


@pytest.fixture
def mock_home_assistant_config(mock_gateway_config) -> dict:
    """Create a mock Home Assistant configuration."""
    return {
        "eltako": {
            "gateway": [
                {
                    "id": 0,
                    **mock_gateway_config,
                }
            ],
            "general_settings": {
                "fast_status_change": False,
                "show_dev_id_in_dev_name": True,
            },
        }
    }


@pytest.fixture
def mock_gateway():
    """Create a mock EnOcean gateway."""
    gateway = MagicMock()
    gateway.dev_id = 0
    gateway.dev_name = "Test Gateway"
    gateway.device_type = GatewayDeviceType.EnOceanUSB2
    gateway.serial_path = TEST_SERIAL_PATH
    gateway.base_id = TEST_BASE_ID
    gateway.is_active.return_value = True
    gateway.async_setup = AsyncMock(return_value=True)
    gateway.unload = MagicMock()
    return gateway


@pytest.fixture
def mock_coordinator(mock_gateway):
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.gateway = mock_gateway
    coordinator.data = {
        "gateway_status": {
            "name": "Test Gateway",
            "is_active": True,
        },
        "entities": {},
    }
    coordinator.last_update_success = True
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_shutdown = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_setup_functions():
    """Mock all setup helper functions."""
    with patch.multiple(
        "custom_components.eltako.config_helpers",
        async_get_home_assistant_config=AsyncMock(),
        config_check_gateway=MagicMock(return_value=True),
        get_id_from_name=MagicMock(return_value=0),
        async_find_gateway_config_by_id=AsyncMock(),
        get_general_settings_from_configuration=MagicMock(return_value={}),
    ) as mocks:
        yield mocks


@pytest.fixture
def mock_serial_detection():
    """Mock serial port detection."""
    with patch("custom_components.eltako.gateway.detect") as mock_detect:
        mock_detect.return_value = [TEST_SERIAL_PATH, "/dev/ttyUSB1"]
        yield mock_detect


@pytest.fixture
def mock_path_validation():
    """Mock path validation."""
    with patch("custom_components.eltako.gateway.validate_path") as mock_validate:
        mock_validate.return_value = True
        yield mock_validate


@pytest.fixture
async def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.async_add_executor_job = AsyncMock()
    return hass


# Platform-specific fixtures
@pytest.fixture
def mock_sensor_entity():
    """Create a mock sensor entity."""
    entity = MagicMock()
    entity.unique_id = "test_sensor_unique_id"
    entity.name = "Test Sensor"
    entity.state = "23.5"
    entity.device_class = "temperature"
    entity.unit_of_measurement = "°C"
    return entity


@pytest.fixture
def mock_switch_entity():
    """Create a mock switch entity."""
    entity = MagicMock()
    entity.unique_id = "test_switch_unique_id"
    entity.name = "Test Switch"
    entity.is_on = False
    entity.turn_on = AsyncMock()
    entity.turn_off = AsyncMock()
    return entity


@pytest.fixture
def mock_light_entity():
    """Create a mock light entity."""
    entity = MagicMock()
    entity.unique_id = "test_light_unique_id"
    entity.name = "Test Light"
    entity.is_on = False
    entity.brightness = 255
    entity.turn_on = AsyncMock()
    entity.turn_off = AsyncMock()
    return entity


# Integration-wide mocks
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    yield


@pytest.fixture
def mock_eltako_libraries():
    """Mock external Eltako libraries."""
    with patch.dict("sys.modules", {
        "eltako14bus": MagicMock(),
        "eltako14bus.utils": MagicMock(),
        "eltakobus": MagicMock(),
        "eltakobus.util": MagicMock(),
        "eltakobus.eep": MagicMock(),
        "eltakobus.message": MagicMock(),
        "enocean": MagicMock(),
        "esp2_gateway_adapter": MagicMock(),
    }):
        yield


# Error simulation fixtures
@pytest.fixture
def mock_connection_error():
    """Mock connection error scenarios."""
    error = ConnectionError("Unable to connect to gateway")
    return error


@pytest.fixture
def mock_timeout_error():
    """Mock timeout error scenarios."""
    error = TimeoutError("Gateway connection timeout")
    return error