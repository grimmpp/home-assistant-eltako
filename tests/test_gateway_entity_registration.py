"""Regression tests for two bugs which only showed up on a real installation.

1. The local variable `gateway_config` in async_setup_entry shadowed the module
   of the same name, so persisting the base id a gateway reported about itself
   failed with "'dict' object has no attribute 'async_update_gateway_base_id'"
   - gateways created in the web ui kept base id 00-00-00-00 after a restart.
2. The message counter sensor of a gateway declared
   `suggested_unit_of_measurement="Messages"`. Home Assistant validates that
   value and rejected the whole entity with "suggest an incorrect unit of
   measurement".
"""

import ast
import inspect
import os
import unittest

from homeassistant.components.sensor import SensorEntityDescription

import custom_components.eltako.eltako_integration_init as integration_init
from custom_components.eltako import gateway_config
from custom_components.eltako.sensor import GatewayReceivedMessagesInActiveSession

# units Home Assistant accepts for a sensor without a device class
VALID_UNIT_TYPES = (str, type(None))


class TestSetupEntryDoesNotShadowModules(unittest.TestCase):
    """async_setup_entry must not assign to a name it imported as a module."""

    def test_no_imported_module_is_shadowed_by_a_local_variable(self):
        source = inspect.getsource(integration_init)
        tree = ast.parse(source)

        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                imported_modules.update(alias.asname or alias.name for alias in node.names)

        offenders = []
        for function in [node for node in ast.walk(tree)
                         if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))]:
            for node in ast.walk(function):
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                    targets = [node.target]
                for target in targets:
                    if isinstance(target, ast.Name) and target.id in imported_modules:
                        offenders.append(f"{function.name}:{target.lineno} assigns to the "
                                         f"imported module '{target.id}'")

        self.assertEqual(offenders, [],
                         "Local variables shadow imported modules:\n  " + "\n  ".join(offenders))

    def test_base_id_is_persisted_through_the_gateway_config_module(self):
        # the callback must reach the module function, not a local dict
        self.assertTrue(hasattr(gateway_config, 'async_update_gateway_base_id'))
        source = inspect.getsource(integration_init.async_setup_entry)
        self.assertIn("gateway_config.async_update_gateway_base_id", source)


class TestGatewaySensorUnits(unittest.TestCase):
    """Entity descriptions must only use units Home Assistant accepts."""

    def test_message_counter_has_no_suggested_unit(self):
        from tests.mocks import GatewayMock

        sensor = GatewayReceivedMessagesInActiveSession('sensor', GatewayMock())
        description = sensor.entity_description

        # A free text unit is only accepted as native_unit_of_measurement.
        # suggested_unit_of_measurement is validated against the units of the
        # device class and made Home Assistant reject the entity.
        self.assertIsNone(description.suggested_unit_of_measurement)
        self.assertIsNone(description.device_class)
        self.assertEqual(description.native_unit_of_measurement, "messages")

    def test_all_sensor_descriptions_use_plain_units(self):
        """suggested_unit_of_measurement is only valid together with a device class
        whose unit list contains it - the integration does not use that anywhere."""
        import custom_components.eltako.sensor as sensor_module

        offenders = []
        for name, value in vars(sensor_module).items():
            if not isinstance(value, SensorEntityDescription):
                continue
            suggested = getattr(value, 'suggested_unit_of_measurement', None)
            if suggested is not None and value.device_class is None:
                offenders.append(f"{name}: suggested unit '{suggested}' without a device class")
            self.assertIsInstance(value.native_unit_of_measurement, VALID_UNIT_TYPES, name)
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == '__main__':
    unittest.main()
