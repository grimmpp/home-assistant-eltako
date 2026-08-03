"""Devices can be declared in configuration.yaml and created through the web ui."""
import unittest
from unittest import TestCase

import voluptuous as vol

from tests.mocks import *

from custom_components.eltako import device_config
from custom_components.eltako.const import *

from homeassistant.const import CONF_DEVICE_CLASS, CONF_ID, CONF_NAME, Platform


class ConfigEntryWithOptions:
    def __init__(self, options: dict = None, entry_id: str = "entry", title: str = "gw"):
        self.options = options or {}
        self.entry_id = entry_id
        self.title = title
        self.data = {}


class TestFormDescriptor(TestCase):

    def test_every_supported_platform_is_offered(self):
        descriptor = device_config.get_form_descriptor()
        platforms = [p['platform'] for p in descriptor['platforms']]

        self.assertEqual(sorted(platforms), sorted(device_config.SUPPORTED_PLATFORMS.keys()))

    def test_address_and_eep_are_always_required(self):
        for platform in device_config.get_form_descriptor()['platforms']:
            required = [f['name'] for f in platform['fields'] if f.get('required')]
            self.assertIn(CONF_ID, required, msg=platform['platform'])
            self.assertIn(CONF_EEP, required, msg=platform['platform'])

    def test_eep_options_come_from_the_schemas(self):
        """The offered EEPs must not drift apart from the supported ones."""
        from custom_components.eltako.schema import LightSchema

        light = [p for p in device_config.get_form_descriptor()['platforms'] if p['platform'] == 'light'][0]
        eep_field = [f for f in light['fields'] if f['name'] == CONF_EEP][0]

        self.assertEqual(sorted(option['value'] for option in eep_field['options']),
                         sorted(LightSchema.CONF_EEP_SUPPORTED))

    def test_every_eep_option_carries_a_label(self):
        """The user should not have to know the EEP numbers by heart."""
        for platform in device_config.get_form_descriptor()['platforms']:
            for field in platform['fields']:
                fields = [field] + list(field.get('fields', []))
                for candidate in fields:
                    if candidate['name'] != CONF_EEP:
                        continue
                    for option in candidate['options']:
                        self.assertIn('value', option)
                        self.assertTrue(option['label'].startswith(option['value']), msg=option)
                        self.assertGreater(len(option['label']), len(option['value']),
                                           msg=f"{option['value']} has no description")

    def test_eep_descriptions(self):
        self.assertIn('Temperature', device_config.describe_eep('A5-04-02'))
        self.assertIn('FLGTF', device_config.describe_eep('A5-04-02'))
        self.assertIn('PREFERRED', device_config.describe_eep('A5-38-08'))
        self.assertEqual(device_config.describe_eep('X9-99-99'), "")

    def test_actuators_require_a_sender(self):
        for platform_name in ['light', 'switch', 'cover', 'climate']:
            platform = [p for p in device_config.get_form_descriptor()['platforms']
                        if p['platform'] == platform_name][0]
            sender = [f for f in platform['fields'] if f['name'] == CONF_SENDER][0]
            self.assertTrue(sender['required'], msg=platform_name)
            self.assertEqual([f['name'] for f in sender['fields']], [CONF_ID, CONF_EEP])


class TestDeviceValidation(TestCase):

    def test_valid_binary_sensor(self):
        validated = device_config.validate_device('binary_sensor', {
            CONF_ID: 'FF-AA-80-01', CONF_EEP: 'F6-02-01', CONF_NAME: 'Switch',
        })

        self.assertEqual(validated[CONF_NAME], 'Switch')
        self.assertFalse(validated[CONF_INVERT_SIGNAL])     # default of the schema

    def test_empty_optional_values_are_dropped(self):
        """The web ui sends empty strings for untouched optional fields."""
        validated = device_config.validate_device('binary_sensor', {
            CONF_ID: 'FF-AA-80-01', CONF_EEP: 'F6-02-01', CONF_NAME: '',
            CONF_AREA: '', CONF_DEVICE_CLASS: '',
        })

        self.assertEqual(validated[CONF_NAME], 'Binary sensor')   # default is used
        self.assertNotIn(CONF_DEVICE_CLASS, validated)

    def test_invalid_eep_is_rejected(self):
        with self.assertRaises(vol.Invalid):
            device_config.validate_device('binary_sensor', {CONF_ID: 'FF-AA-80-01', CONF_EEP: 'A5-99-99'})

    def test_invalid_address_is_rejected(self):
        with self.assertRaises(vol.Invalid):
            device_config.validate_device('binary_sensor', {CONF_ID: 'not-an-address', CONF_EEP: 'F6-02-01'})

    def test_actuator_without_sender_is_rejected(self):
        with self.assertRaises(vol.Invalid):
            device_config.validate_device('light', {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08'})

    def test_actuator_with_sender(self):
        validated = device_config.validate_device('light', {
            CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08', CONF_NAME: 'FSR14 - 1',
            CONF_SENDER: {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-38-08'},
        })

        self.assertEqual(validated[CONF_SENDER][CONF_EEP], 'A5-38-08')

    def test_empty_sender_group_is_dropped_and_therefore_rejected(self):
        with self.assertRaises(vol.Invalid):
            device_config.validate_device('light', {
                CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08',
                CONF_SENDER: {CONF_ID: '', CONF_EEP: ''},
            })

    def test_unsupported_platform(self):
        with self.assertRaises(vol.Invalid):
            device_config.validate_device('button', {CONF_ID: 'FF-AA-80-01'})

    def test_address_normalization(self):
        self.assertEqual(device_config.normalize_address('ff-aa-80-01'), 'FF-AA-80-01')
        with self.assertRaises(vol.Invalid):
            device_config.normalize_address('xyz')


class TestUiDeviceStorage(TestCase):

    def test_no_devices_by_default(self):
        self.assertEqual(device_config.get_ui_devices(ConfigEntryWithOptions()), {})
        self.assertEqual(device_config.get_ui_devices(None), {})

    def test_devices_are_read_from_the_options(self):
        entry = ConfigEntryWithOptions({CONF_UI_DEVICES: {
            'binary_sensor': [{CONF_ID: 'FF-AA-80-01', CONF_EEP: 'F6-02-01'}],
            'light': [],
        }})

        devices = device_config.get_ui_devices(entry)

        self.assertEqual(list(devices.keys()), ['binary_sensor'])   # empty platforms are skipped
        self.assertEqual(len(devices['binary_sensor']), 1)

    def test_find_device_is_case_insensitive(self):
        devices = {'binary_sensor': [{CONF_ID: 'FF-AA-80-01'}]}

        self.assertIsNotNone(device_config.find_device(devices, 'binary_sensor', 'ff-aa-80-01'))
        self.assertIsNone(device_config.find_device(devices, 'binary_sensor', 'FF-AA-80-02'))
        self.assertIsNone(device_config.find_device(devices, 'light', 'FF-AA-80-01'))


class TestMergeOfBothSources(TestCase):

    YAML = {
        'binary_sensor': [{CONF_ID: 'FF-AA-80-01', CONF_EEP: 'F6-02-01', CONF_NAME: 'from yaml'}],
        'light': [{CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08'}],
    }

    def test_ui_devices_are_added(self):
        ui = {'binary_sensor': [{CONF_ID: 'FF-BB-11-22', CONF_EEP: 'F6-02-01', CONF_NAME: 'from ui'}],
              'sensor': [{CONF_ID: 'FF-CC-33-44', CONF_EEP: 'A5-04-02'}]}

        merged = device_config.merge_device_config(self.YAML, ui)

        self.assertEqual(len(merged['binary_sensor']), 2)
        self.assertEqual(len(merged['light']), 1)
        self.assertEqual(len(merged['sensor']), 1)

    def test_yaml_wins_on_conflict(self):
        ui = {'binary_sensor': [{CONF_ID: 'ff-aa-80-01', CONF_EEP: 'D5-00-01', CONF_NAME: 'from ui'}]}

        merged = device_config.merge_device_config(self.YAML, ui)

        self.assertEqual(len(merged['binary_sensor']), 1)
        self.assertEqual(merged['binary_sensor'][0][CONF_NAME], 'from yaml')

    def test_merge_without_ui_devices_returns_the_yaml_config(self):
        self.assertEqual(device_config.merge_device_config(self.YAML, {}), self.YAML)

    def test_merge_without_yaml_config(self):
        ui = {'sensor': [{CONF_ID: 'FF-CC-33-44', CONF_EEP: 'A5-04-02'}]}

        self.assertEqual(device_config.merge_device_config({}, ui), ui)

    def test_merge_does_not_modify_the_sources(self):
        ui = {'binary_sensor': [{CONF_ID: 'FF-BB-11-22', CONF_EEP: 'F6-02-01'}]}

        device_config.merge_device_config(self.YAML, ui)

        self.assertEqual(len(self.YAML['binary_sensor']), 1)
        self.assertEqual(len(ui['binary_sensor']), 1)


if __name__ == '__main__':
    unittest.main()
