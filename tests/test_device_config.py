"""Devices can be declared in configuration.yaml and created through the web ui."""
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

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

    def test_area_field_is_a_combo(self):
        """The area is picked from the areas home assistant knows - or typed freely."""
        for platform in device_config.get_form_descriptor()['platforms']:
            area = [f for f in platform['fields'] if f['name'] == CONF_AREA][0]
            self.assertEqual(area['type'], 'combo', msg=platform['platform'])

    def test_area_options_are_injected(self):
        descriptor = device_config.get_form_descriptor()
        device_config._inject_area_options(descriptor, ['Kitchen', 'Living room'])

        for platform in descriptor['platforms']:
            area = [f for f in platform['fields'] if f['name'] == CONF_AREA][0]
            self.assertEqual(area['options'], ['Kitchen', 'Living room'], msg=platform['platform'])

    def test_area_injection_does_not_leak_into_the_module_constant(self):
        """FIELD_AREA is shared between the platforms and between websocket calls."""
        descriptor = device_config.get_form_descriptor()
        device_config._inject_area_options(descriptor, ['Kitchen'])

        self.assertNotIn('options', device_config.FIELD_AREA)
        fresh = device_config.get_form_descriptor()
        for platform in fresh['platforms']:
            area = [f for f in platform['fields'] if f['name'] == CONF_AREA][0]
            self.assertNotIn('options', area, msg=platform['platform'])


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


class HassMockForDevices:
    """Minimal hass which stores the options of one config entry."""

    def __init__(self, gateway_id: int = 1, yaml_devices: dict = None):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: {CONF_GATEWAY: [{
            CONF_ID: gateway_id, CONF_DEVICE_TYPE: 'fam14', CONF_NAME: 'FAM14',
            CONF_DEVICES: yaml_devices or {}}]}}}
        self.config_entries = self

    def async_update_entry(self, entry, options=None, **kwargs):
        entry.options = options


class TestUiDeviceCrud(IsolatedAsyncioTestCase):
    """A device created in the web ui can be created, changed and removed again."""

    LIGHT = {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08', CONF_NAME: 'Lamp',
             CONF_SENDER: {CONF_ID: '00-00-B0-01', CONF_EEP: 'A5-38-08'}}

    def setUp(self):
        self.hass = HassMockForDevices()
        self.entry = ConfigEntryWithOptions()
        self.entry.data = {CONF_GATEWAY_DESCRIPTION: 'FAM14 - fam14 (Id: 1)'}

    def _stored(self, platform: str) -> list:
        return (self.entry.options.get(CONF_UI_DEVICES) or {}).get(platform, [])

    async def test_create_change_and_remove(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))
        self.assertEqual(self._stored('light')[0][CONF_NAME], 'Lamp')

        await device_config.async_update_ui_device(
            self.hass, self.entry, 'light', '00-00-00-01',
            {**self.LIGHT, CONF_NAME: 'Kitchen ceiling', CONF_AREA: 'Kitchen'})

        self.assertEqual(len(self._stored('light')), 1)
        self.assertEqual(self._stored('light')[0][CONF_NAME], 'Kitchen ceiling')
        self.assertEqual(self._stored('light')[0][CONF_AREA], 'Kitchen')

        await device_config.async_remove_ui_device(self.hass, self.entry, 'light', '00-00-00-01')
        self.assertEqual(self._stored('light'), [])

    async def test_the_eep_and_the_sender_can_be_changed(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))

        await device_config.async_update_ui_device(
            self.hass, self.entry, 'light', '00-00-00-01',
            {**self.LIGHT, CONF_EEP: 'A5-38-08',
             CONF_SENDER: {CONF_ID: '00-00-B0-09', CONF_EEP: 'A5-38-08'}})

        stored = self._stored('light')[0]
        self.assertEqual(stored[CONF_EEP], 'A5-38-08')
        self.assertEqual(stored[CONF_SENDER][CONF_ID], '00-00-B0-09')

    async def test_the_address_can_be_corrected(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))

        await device_config.async_update_ui_device(
            self.hass, self.entry, 'light', '00-00-00-01',
            {**self.LIGHT, CONF_ID: '00-00-00-07'})

        self.assertEqual([device[CONF_ID] for device in self._stored('light')], ['00-00-00-07'])

    async def test_a_lower_case_address_finds_the_device(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))

        await device_config.async_update_ui_device(
            self.hass, self.entry, 'light', '00-00-00-01', {**self.LIGHT, CONF_NAME: 'x'})

        self.assertEqual(self._stored('light')[0][CONF_NAME], 'x')

    async def test_invalid_values_are_rejected_and_nothing_is_changed(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))

        with self.assertRaises(vol.Invalid):
            await device_config.async_update_ui_device(
                self.hass, self.entry, 'light', '00-00-00-01', {**self.LIGHT, CONF_EEP: 'F6-02-01'})

        self.assertEqual(self._stored('light')[0][CONF_EEP], 'M5-38-08')

    async def test_updating_an_unknown_device_is_rejected(self):
        with self.assertRaises(vol.Invalid) as context:
            await device_config.async_update_ui_device(
                self.hass, self.entry, 'light', '00-00-00-09', dict(self.LIGHT))

        self.assertIn('not configured', str(context.exception))

    async def test_a_setting_the_form_cannot_show_survives_an_edit(self):
        """The schemas support more than the form offers - editing must not drop the rest."""
        await device_config.async_add_ui_device(self.hass, self.entry, 'sensor', {
            CONF_ID: 'FF-AA-80-02', CONF_EEP: 'A5-09-0C', CONF_NAME: 'Air',
            CONF_VOC_TYPE_INDEXES: [1, 2], 'language': 'de'})

        # the ui only sends the fields it rendered (no voc_type_indexes, no language)
        await device_config.async_update_ui_device(self.hass, self.entry, 'sensor', 'FF-AA-80-02', {
            CONF_ID: 'FF-AA-80-02', CONF_EEP: 'A5-09-0C', CONF_NAME: 'Air quality'})

        stored = self._stored('sensor')[0]
        self.assertEqual(stored[CONF_NAME], 'Air quality')
        self.assertEqual(stored[CONF_VOC_TYPE_INDEXES], [1, 2])
        self.assertEqual(stored['language'], 'de')

    async def test_a_field_of_the_form_can_be_cleared(self):
        """A field which the form does offer is always taken from the ui - also when empty."""
        await device_config.async_add_ui_device(self.hass, self.entry, 'binary_sensor', {
            CONF_ID: 'FF-AA-80-03', CONF_EEP: 'F6-02-01', CONF_NAME: 'Button',
            CONF_AREA: 'Kitchen'})

        await device_config.async_update_ui_device(
            self.hass, self.entry, 'binary_sensor', 'FF-AA-80-03',
            {CONF_ID: 'FF-AA-80-03', CONF_EEP: 'F6-02-01', CONF_NAME: 'Button'})

        self.assertNotIn(CONF_AREA, self._stored('binary_sensor')[0])

    async def test_the_form_field_names_come_from_the_descriptor(self):
        names = device_config.get_form_field_names('cover')

        self.assertIn(CONF_TIME_CLOSES, names)
        self.assertIn(CONF_SENDER, names)
        self.assertEqual(device_config.get_form_field_names('nonsense'), set())

    async def test_several_devices_are_stored_with_one_write(self):
        """Every write of the options reloads the gateway - a detection must not reload it
        once per device it found."""
        writes = []
        original = device_config.async_save_ui_devices

        async def counting(hass, config_entry, devices):
            writes.append(len(devices.get('light', [])))
            await original(hass, config_entry, devices)

        device_config.async_save_ui_devices = counting
        try:
            result = await device_config.async_add_ui_devices(self.hass, self.entry, [
                ('light', {CONF_ID: f'00-00-00-0{index}', CONF_EEP: 'M5-38-08',
                           CONF_NAME: f'ch{index}',
                           CONF_SENDER: {CONF_ID: f'00-00-B0-0{index}', CONF_EEP: 'A5-38-08'}})
                for index in range(1, 5)])
        finally:
            device_config.async_save_ui_devices = original

        self.assertEqual(len(result['added']), 4)
        self.assertEqual(writes, [4])            # one single write
        self.assertEqual(len(self._stored('light')), 4)

    async def test_one_invalid_device_does_not_stop_the_others(self):
        result = await device_config.async_add_ui_devices(self.hass, self.entry, [
            ('light', dict(self.LIGHT)),
            ('light', {CONF_ID: 'nonsense', CONF_EEP: 'M5-38-08'}),
            ('binary_sensor', {CONF_ID: 'FF-AA-80-07', CONF_EEP: 'F6-02-01'})])

        self.assertEqual({platform for platform, _device in result['added']},
                         {'light', 'binary_sensor'})
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['errors'][0][1], 'nonsense')

    async def test_devices_which_exist_are_counted_not_reported_as_error(self):
        await device_config.async_add_ui_device(self.hass, self.entry, 'light', dict(self.LIGHT))

        result = await device_config.async_add_ui_devices(
            self.hass, self.entry, [('light', dict(self.LIGHT))])

        self.assertEqual(result['added'], [])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['existing'], [('light', '00-00-00-01')])

    async def test_the_same_address_twice_in_one_batch_is_added_once(self):
        result = await device_config.async_add_ui_devices(self.hass, self.entry, [
            ('light', dict(self.LIGHT)), ('light', dict(self.LIGHT))])

        self.assertEqual(len(result['added']), 1)
        self.assertEqual(len(result['existing']), 1)
        self.assertEqual(len(self._stored('light')), 1)

    async def test_nothing_to_add(self):
        result = await device_config.async_add_ui_devices(self.hass, self.entry, [])

        self.assertEqual(result, {'added': [], 'existing': [], 'errors': []})
        self.assertEqual(self.entry.options, {})

    async def test_a_device_of_the_yaml_cannot_be_shadowed(self):
        hass = HassMockForDevices(yaml_devices={
            'binary_sensor': [{CONF_ID: 'FF-AA-80-01', CONF_EEP: 'F6-02-01'}]})

        with self.assertRaises(vol.Invalid) as context:
            await device_config.async_add_ui_device(
                hass, self.entry, 'binary_sensor',
                {CONF_ID: 'FF-AA-80-01', CONF_EEP: 'D5-00-01'})

        self.assertIn('configuration.yaml', str(context.exception))


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
