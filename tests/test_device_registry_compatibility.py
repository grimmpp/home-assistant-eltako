import unittest

from custom_components.eltako.core.entity import get_device_by_identifier


class _ScopedRegistry:
    def __init__(self):
        self.calls = []

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        self.calls.append((identifier, config_entry_id))
        return "scoped-device"

    def async_get_device(self, identifiers):
        raise AssertionError("the unscoped lookup must not be used")


class _LegacyRegistry:
    def __init__(self):
        self.calls = []

    def async_get_device(self, identifiers):
        self.calls.append(identifiers)
        return "legacy-device"


class TestDeviceRegistryCompatibility(unittest.TestCase):
    def test_uses_config_entry_scoped_lookup(self):
        registry = _ScopedRegistry()

        result = get_device_by_identifier(registry, ("eltako", "gateway"), "entry-1")

        self.assertEqual(result, "scoped-device")
        self.assertEqual(registry.calls, [(('eltako', 'gateway'), 'entry-1')])

    def test_falls_back_for_older_home_assistant(self):
        registry = _LegacyRegistry()
        identifier = ("eltako", "gateway")

        result = get_device_by_identifier(registry, identifier, "entry-1")

        self.assertEqual(result, "legacy-device")
        self.assertEqual(registry.calls, [{identifier}])

