"""Entity values must be written to `_attr_*`, never to the read-only property itself.

Home Assistant entities expose their value as a **property without setter**
(`native_value`, `is_on`, `hvac_mode`, ...) which reads the `_attr_*` attribute. Assigning to
the property raises `AttributeError: property '...' has no setter` at runtime - and if that
happens inside an event listener the value silently never updates.

This was a real bug in five places (four in sensor.py, one in datetime.py); two of them were
additionally hidden by an `except AttributeError: pass`. A static test finds the next one
before it reaches a device.

Only **entity** classes are checked. `state`, `available` or `options` are ordinary attribute
names; a plain model class (a simulated device, a descriptor) may write them and does not
inherit any property. `_entity_classes()` therefore resolves who derives from an entity base
first, transitively and across modules.
"""
import ast
import os
import unittest
from unittest import TestCase

INTEGRATION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               'custom_components', 'eltako')

# read-only properties of the Home Assistant entity classes this integration builds on.
# Writing them means writing the `_attr_` variant.
READ_ONLY_PROPERTIES = {
    'native_value', 'native_unit_of_measurement', 'state', 'is_on', 'available',
    'hvac_mode', 'hvac_action', 'current_temperature', 'target_temperature',
    'brightness', 'color_mode', 'is_closed', 'is_opening', 'is_closing',
    'current_cover_position', 'current_cover_tilt_position',
    'current_option', 'options', 'unique_id', 'device_class', 'state_class',
}


def python_files() -> list[str]:
    files = []
    for root, _dirs, names in os.walk(INTEGRATION_DIR):
        if 'frontend' in root or '__pycache__' in root:
            continue
        files.extend(os.path.join(root, name) for name in names if name.endswith('.py'))
    return sorted(files)


def _base_names(node: ast.ClassDef) -> set[str]:
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _entity_classes(trees: dict) -> set[str]:
    """Every class of the integration which (transitively) derives from an entity base.

    A base whose name ends in 'Entity' is one - that is how Home Assistant names them
    (SensorEntity, RestoreEntity, ...) and how this integration names its own (EltakoEntity).
    """
    classes = [node for tree in trees.values() for node in ast.walk(tree)
               if isinstance(node, ast.ClassDef)]
    entities = {node.name for node in classes
                if any(name.endswith('Entity') for name in _base_names(node))}
    entities |= {node.name for node in classes if node.name.endswith('Entity')}

    growing = True
    while growing:
        growing = False
        for node in classes:
            if node.name not in entities and _base_names(node) & entities:
                entities.add(node.name)
                growing = True
    return entities


class TestNoWriteToReadOnlyProperty(TestCase):

    def test_no_assignment_to_a_read_only_entity_property(self):
        trees = {}
        for path in python_files():
            with open(path, encoding='utf-8') as handle:
                trees[path] = ast.parse(handle.read(), filename=path)

        entities = _entity_classes(trees)
        offenders = []
        for path, tree in trees.items():
            for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
                if class_node.name not in entities:
                    continue
                for node in ast.walk(class_node):
                    if not isinstance(node, (ast.Assign, ast.AugAssign)):
                        continue
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if (isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == 'self'
                                and target.attr in READ_ONLY_PROPERTIES):
                            offenders.append(
                                f"{os.path.relpath(path, INTEGRATION_DIR)}:{node.lineno} "
                                f"self.{target.attr} = ...  -> use self._attr_{target.attr}")

        self.assertEqual(sorted(set(offenders)), [],
                         msg="Assignment to a read-only entity property:\n  "
                             + "\n  ".join(sorted(set(offenders))))

    def test_it_looks_at_entity_classes_only(self):
        """Guard for the scoping: a plain model class may own an attribute called `state`."""
        trees = {'x.py': ast.parse('class SimulatedDevice:\n'
                                   '    def f(self):\n'
                                   '        self.state = 1\n'
                                   'class MySensor(SensorEntity):\n'
                                   '    pass\n'
                                   'class Derived(MySensor):\n'
                                   '    pass\n')}

        entities = _entity_classes(trees)

        self.assertNotIn('SimulatedDevice', entities)
        self.assertIn('MySensor', entities)
        self.assertIn('Derived', entities, msg='inheritance must be followed transitively')

    def test_the_detector_would_catch_the_original_bug(self):
        """Guard for the test itself: the pattern which was broken must be detected."""
        tree = ast.parse("class X(SensorEntity):\n"
                         "    def f(self, event):\n"
                         "        self.native_value = 1\n")
        self.assertIn('X', _entity_classes({'x.py': tree}))

        found = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Attribute)
                 and node.targets[0].attr in READ_ONLY_PROPERTIES]

        self.assertEqual(len(found), 1)


class TestEventListenerAppliesTheValue(TestCase):
    """The listener of EventListenerInfoField must really update the sensor value."""

    def test_value_changed_sets_the_attribute(self):
        from unittest import mock

        from tests.mocks import GatewayMock
        from custom_components.eltako.sensor import EventListenerInfoField
        from eltakobus.util import AddressExpression
        from homeassistant.const import Platform
        from homeassistant.helpers.entity import Entity

        Entity.schedule_update_ha_state = mock.Mock(return_value=None)

        field = EventListenerInfoField(
            Platform.SENSOR, GatewayMock(dev_id=1), AddressExpression.parse('00-00-00-00'),
            'Gateway', None, event_id='some_event', key='Repeater mode',
            convert_event_function=lambda event: f"level {event['level']}")

        field.value_changed({'level': 2})

        self.assertEqual(field.native_value, 'level 2')


if __name__ == '__main__':
    unittest.main()
