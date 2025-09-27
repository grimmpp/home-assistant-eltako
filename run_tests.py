#!/usr/bin/env python
"""Test runner for Eltako integration with mocked Home Assistant dependencies."""
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
import pytest

# Mock Home Assistant modules that might not be available
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
    'enocean',
    'esp2_gateway_adapter',
]

def mock_missing_modules():
    """Mock missing modules for testing."""
    for module_name in MOCK_MODULES:
        if module_name not in sys.modules:
            sys.modules[module_name] = MagicMock()

def main():
    """Run tests with appropriate configuration."""
    # Mock missing modules
    mock_missing_modules()

    # Set up test environment
    test_path = Path(__file__).parent / "tests_new"

    # Configure pytest arguments
    pytest_args = [
        str(test_path),
        "-v",
        "--tb=short",
        "--disable-warnings",
        "--no-cov",  # Disable coverage for now since modules are mocked
        "-x",  # Stop on first failure
    ]

    print("Running Eltako integration tests...")
    print(f"Test path: {test_path}")
    print(f"Pytest args: {' '.join(pytest_args)}")

    # Run pytest
    exit_code = pytest.main(pytest_args)

    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code: {exit_code}")

    return exit_code

if __name__ == "__main__":
    sys.exit(main())