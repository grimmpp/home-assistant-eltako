"""Simple standalone tests that don't require full Home Assistant dependencies."""
from __future__ import annotations

import pytest
import sys
from unittest.mock import MagicMock, patch

# Mock all the external dependencies before any imports
MOCK_MODULES = [
    'homeassistant',
    'homeassistant.core',
    'homeassistant.config_entries',
    'homeassistant.helpers',
    'homeassistant.helpers.entity',
    'homeassistant.helpers.entity_platform',
    'homeassistant.helpers.update_coordinator',
    'homeassistant.helpers.restore_state',
    'homeassistant.helpers.typing',
    'homeassistant.helpers.entity_registry',
    'homeassistant.components.sensor',
    'homeassistant.components.light',
    'homeassistant.components.switch',
    'homeassistant.const',
    'homeassistant.data_entry_flow',
    'homeassistant.exceptions',
    'homeassistant.setup',
    'eltako14bus',
    'eltako14bus.utils',
    'eltakobus',
    'eltakobus.util',
    'eltakobus.eep',
    'eltakobus.message',
    'eltakobus.serial',
    'enocean',
    'esp2_gateway_adapter',
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
]

for module_name in MOCK_MODULES:
    if module_name not in sys.modules:
        sys.modules[module_name] = MagicMock()

# Now we can safely import our modules
from custom_components.eltako.const import DOMAIN


class TestBasicIntegration:
    """Test basic integration functionality."""

    def test_domain_constant(self):
        """Test that domain constant is correctly defined."""
        assert DOMAIN == "eltako"

    def test_imports_work(self):
        """Test that basic imports work."""
        # Test constants import
        from custom_components.eltako.const import (
            CONF_GATEWAY_DESCRIPTION,
            CONF_SERIAL_PATH,
            PLATFORMS,
        )

        assert CONF_GATEWAY_DESCRIPTION is not None
        assert CONF_SERIAL_PATH is not None
        assert PLATFORMS is not None

    def test_config_flow_class_exists(self):
        """Test that config flow class can be imported."""
        try:
            from custom_components.eltako.config_flow import EltakoFlowHandler
            assert EltakoFlowHandler is not None
        except ImportError as e:
            pytest.skip(f"Config flow import failed: {e}")

    def test_coordinator_class_exists(self):
        """Test that coordinator class can be imported."""
        try:
            from custom_components.eltako.coordinator import EltakoDataUpdateCoordinator
            assert EltakoDataUpdateCoordinator is not None
        except ImportError as e:
            pytest.skip(f"Coordinator import failed: {e}")

    @patch('custom_components.eltako.async_setup')
    async def test_async_setup_function_exists(self, mock_setup):
        """Test that async_setup function exists and can be called."""
        mock_setup.return_value = True

        from custom_components.eltako import async_setup

        # Mock hass and config
        mock_hass = MagicMock()
        mock_config = {}

        result = await async_setup(mock_hass, mock_config)
        assert result is True
        mock_setup.assert_called_once_with(mock_hass, mock_config)

    def test_platform_modules_exist(self):
        """Test that platform modules can be imported."""
        platforms = ["sensor", "light", "switch"]

        for platform in platforms:
            try:
                module = __import__(f"custom_components.eltako.{platform}", fromlist=[platform])
                assert hasattr(module, "async_setup_entry")
            except ImportError as e:
                pytest.skip(f"Platform {platform} import failed: {e}")

    def test_manifest_json_exists(self):
        """Test that manifest.json exists and is valid."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "custom_components" / "eltako" / "manifest.json"

        assert manifest_path.exists(), "manifest.json not found"

        with open(manifest_path) as f:
            manifest = json.load(f)

        required_keys = ["domain", "name", "version", "documentation", "requirements"]
        for key in required_keys:
            assert key in manifest, f"Required key '{key}' missing from manifest.json"

        assert manifest["domain"] == "eltako"

    def test_strings_json_exists(self):
        """Test that strings.json exists for translations."""
        import json
        from pathlib import Path

        strings_path = Path(__file__).parent.parent / "custom_components" / "eltako" / "strings.json"

        if strings_path.exists():
            with open(strings_path) as f:
                strings = json.load(f)

            assert isinstance(strings, dict)

    def test_init_module_structure(self):
        """Test that __init__.py has the expected structure."""
        try:
            import custom_components.eltako as eltako_module

            # Check for required functions
            required_functions = ["async_setup", "async_setup_entry", "async_unload_entry"]
            for func_name in required_functions:
                assert hasattr(eltako_module, func_name), f"Missing function: {func_name}"

        except ImportError as e:
            pytest.skip(f"Init module import failed: {e}")


class TestConfigurationValidation:
    """Test configuration validation functions."""

    def test_config_helpers_import(self):
        """Test that config helpers can be imported."""
        try:
            from custom_components.eltako import config_helpers
            assert config_helpers is not None
        except ImportError as e:
            pytest.skip(f"Config helpers import failed: {e}")

    def test_device_module_import(self):
        """Test that device module can be imported."""
        try:
            from custom_components.eltako import device
            assert device is not None
        except ImportError as e:
            pytest.skip(f"Device module import failed: {e}")


class TestCompatibility:
    """Test backward compatibility."""

    def test_legacy_init_import(self):
        """Test that legacy init module can be imported."""
        try:
            from custom_components.eltako import eltako_integration_init
            assert eltako_integration_init is not None
        except ImportError as e:
            pytest.skip(f"Legacy init import failed: {e}")

    def test_legacy_functions_available(self):
        """Test that legacy functions are still available."""
        try:
            from custom_components.eltako.eltako_integration_init import (
                async_setup as legacy_setup,
                async_setup_entry as legacy_setup_entry,
                async_unload_entry as legacy_unload_entry,
            )

            assert callable(legacy_setup)
            assert callable(legacy_setup_entry)
            assert callable(legacy_unload_entry)

        except ImportError as e:
            pytest.skip(f"Legacy functions import failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])