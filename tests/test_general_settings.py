"""General settings can be edited in the web ui and override configuration.yaml."""
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

import voluptuous as vol

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.config import config_helpers, general_settings
from custom_components.eltako.const import *


class StoreMock:
    def __init__(self, data: dict = None):
        self.data = data
        self.saved = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.saved = data


def hass_with(yaml_settings: dict = None, stored_overrides: dict = None) -> HassDataMock:
    config = {}
    if yaml_settings is not None:
        config[CONF_GERNERAL_SETTINGS] = yaml_settings
    hass = HassDataMock(config=config)
    hass.data[DATA_ELTAKO][DATA_SETTINGS_STORE] = StoreMock(
        {'overrides': stored_overrides} if stored_overrides is not None else None)
    return hass


class TestPrecedence(IsolatedAsyncioTestCase):

    async def test_default_is_used_without_yaml_and_without_override(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertFalse(settings[CONF_LOG_ENOCEAN_TELEGRAMS])
        self.assertEqual(settings[CONF_TELEGRAM_LOG_BUFFER_SIZE], 500)

    async def test_yaml_wins_over_default(self):
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42})
        await general_settings.async_load_overrides(hass)

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertEqual(settings[CONF_TELEGRAM_LOG_BUFFER_SIZE], 42)

    async def test_ui_override_wins_over_yaml(self):
        """This is the opposite of the device configuration - on purpose."""
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42},
                         stored_overrides={CONF_TELEGRAM_LOG_BUFFER_SIZE: 99})
        await general_settings.async_load_overrides(hass)

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertEqual(settings[CONF_TELEGRAM_LOG_BUFFER_SIZE], 99)

    async def test_configuration_without_any_yaml_is_possible(self):
        """The whole point: no yaml needed at all."""
        hass = hass_with(stored_overrides={CONF_LOG_ENOCEAN_TELEGRAMS: True,
                                          CONF_TELEGRAM_LOG_FILENAME: 'telegrams.jsonl',
                                          CONF_ENABLE_FRONTEND: True})
        await general_settings.async_load_overrides(hass)

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertTrue(settings[CONF_LOG_ENOCEAN_TELEGRAMS])
        self.assertEqual(settings[CONF_TELEGRAM_LOG_FILENAME], 'telegrams.jsonl')
        self.assertTrue(config_helpers.is_frontend_enabled(settings))

    async def test_invalid_stored_values_are_ignored(self):
        hass = hass_with(stored_overrides={CONF_TELEGRAM_LOG_FORMAT: 'xml',        # not a valid format
                                          CONF_TELEGRAM_LOG_BUFFER_SIZE: 77})
        overrides = await general_settings.async_load_overrides(hass)

        self.assertNotIn(CONF_TELEGRAM_LOG_FORMAT, overrides)
        self.assertEqual(overrides[CONF_TELEGRAM_LOG_BUFFER_SIZE], 77)

    async def test_unknown_stored_keys_are_ignored(self):
        hass = hass_with(stored_overrides={'made_up_setting': True})

        overrides = await general_settings.async_load_overrides(hass)

        self.assertEqual(overrides, {})


class TestValidation(TestCase):

    def test_boolean_and_number_are_coerced(self):
        self.assertTrue(general_settings.validate_setting(CONF_LOG_ENOCEAN_TELEGRAMS, True))
        self.assertEqual(general_settings.validate_setting(CONF_TELEGRAM_LOG_BUFFER_SIZE, "250"), 250)

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_TELEGRAM_LOG_FORMAT, 'xml')
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_TELEGRAM_LOG_BUFFER_SIZE, -5)
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_TELEGRAM_LOG_MAX_FILE_SIZE_MB, 99999)

    def test_not_editable_settings_are_rejected(self):
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_ENABLE_TEACH_IN_BUTTONS, True)
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting('whatever', 1)

    def test_every_descriptor_is_part_of_the_schema(self):
        for descriptor in general_settings.SETTING_DESCRIPTORS:
            value = general_settings.DEFAULT_GENERAL_SETTINGS.get(descriptor['name'])
            # must not raise
            general_settings.validate_setting(descriptor['name'], value)

    def test_every_editable_setting_has_a_default(self):
        for descriptor in general_settings.SETTING_DESCRIPTORS:
            self.assertIn(descriptor['name'], general_settings.DEFAULT_GENERAL_SETTINGS,
                          msg=descriptor['name'])


class TestSetAndReset(IsolatedAsyncioTestCase):

    async def test_set_stores_and_applies(self):
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42})
        await general_settings.async_load_overrides(hass)

        validated = await general_settings.async_set_overrides(hass, {CONF_TELEGRAM_LOG_BUFFER_SIZE: 123})

        self.assertEqual(validated[CONF_TELEGRAM_LOG_BUFFER_SIZE], 123)
        self.assertEqual(config_helpers.get_general_settings_from_configuration(hass)[CONF_TELEGRAM_LOG_BUFFER_SIZE], 123)
        self.assertEqual(hass.data[DATA_ELTAKO][DATA_SETTINGS_STORE].saved,
                         {'overrides': {CONF_TELEGRAM_LOG_BUFFER_SIZE: 123}})

    async def test_invalid_value_is_not_stored(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)

        with self.assertRaises(vol.Invalid):
            await general_settings.async_set_overrides(hass, {CONF_TELEGRAM_LOG_FORMAT: 'xml'})

        self.assertEqual(general_settings.get_overrides(hass), {})

    async def test_reset_falls_back_to_yaml(self):
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42},
                         stored_overrides={CONF_TELEGRAM_LOG_BUFFER_SIZE: 99})
        await general_settings.async_load_overrides(hass)

        removed = await general_settings.async_reset_overrides(hass, [CONF_TELEGRAM_LOG_BUFFER_SIZE])

        self.assertEqual(removed, [CONF_TELEGRAM_LOG_BUFFER_SIZE])
        self.assertEqual(config_helpers.get_general_settings_from_configuration(hass)[CONF_TELEGRAM_LOG_BUFFER_SIZE], 42)

    async def test_reset_of_unknown_override_is_a_noop(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)

        self.assertEqual(await general_settings.async_reset_overrides(hass, [CONF_TELEGRAM_LOG_BUFFER_SIZE]), [])


class TestFormDescriptor(IsolatedAsyncioTestCase):

    async def test_origin_is_reported_per_setting(self):
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42},
                         stored_overrides={CONF_LOG_ENOCEAN_TELEGRAMS: True})
        await general_settings.async_load_overrides(hass)

        form = general_settings.get_form_descriptor(hass)
        by_name = {setting['name']: setting for setting in form['settings']}

        self.assertEqual(by_name[CONF_LOG_ENOCEAN_TELEGRAMS]['origin'], 'ui')
        self.assertTrue(by_name[CONF_LOG_ENOCEAN_TELEGRAMS]['value'])
        self.assertEqual(by_name[CONF_TELEGRAM_LOG_BUFFER_SIZE]['origin'], 'yaml')
        self.assertEqual(by_name[CONF_FAST_STATUS_CHANGE]['origin'], 'default')
        self.assertTrue(form['has_yaml_section'])

    async def test_fallback_shows_what_happens_on_reset(self):
        hass = hass_with(yaml_settings={CONF_TELEGRAM_LOG_BUFFER_SIZE: 42},
                         stored_overrides={CONF_TELEGRAM_LOG_BUFFER_SIZE: 99})
        await general_settings.async_load_overrides(hass)

        by_name = {s['name']: s for s in general_settings.get_form_descriptor(hass)['settings']}

        self.assertEqual(by_name[CONF_TELEGRAM_LOG_BUFFER_SIZE]['value'], 99)
        self.assertEqual(by_name[CONF_TELEGRAM_LOG_BUFFER_SIZE]['fallback'], 42)
        self.assertEqual(by_name[CONF_TELEGRAM_LOG_BUFFER_SIZE]['fallback_origin'], 'yaml')

    async def test_form_without_yaml_section(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)

        form = general_settings.get_form_descriptor(hass)

        self.assertFalse(form['has_yaml_section'])
        self.assertIn(CONF_ENABLE_TEACH_IN_BUTTONS, form['read_only'])
        for setting in form['settings']:
            self.assertEqual(setting['origin'], 'default')
            self.assertIn('label', setting)
            self.assertIn('type', setting)


if __name__ == '__main__':
    unittest.main()


class TestGroupsAndLogLevels(IsolatedAsyncioTestCase):
    """The settings are structured in groups and every telegram category has a log level."""

    async def test_every_setting_belongs_to_a_known_group(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)

        form = general_settings.get_form_descriptor(hass)
        group_ids = {group['id'] for group in form['groups']}

        self.assertTrue(group_ids)
        for setting in form['settings']:
            self.assertIn(setting.get('group'), group_ids, msg=setting['name'])

    async def test_all_groups_are_used(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)
        form = general_settings.get_form_descriptor(hass)

        used = {setting['group'] for setting in form['settings']}

        for group in form['groups']:
            self.assertIn(group['id'], used, msg=f"group '{group['id']}' has no setting")

    async def test_log_level_settings_exist_for_every_category(self):
        from custom_components.eltako.observation.enocean_logger import LOG_LEVEL_SETTINGS

        hass = hass_with()
        await general_settings.async_load_overrides(hass)
        by_name = {s['name']: s for s in general_settings.get_form_descriptor(hass)['settings']}

        for category, setting_name in LOG_LEVEL_SETTINGS.items():
            self.assertIn(setting_name, by_name, msg=category)
            self.assertEqual(by_name[setting_name]['group'], 'log_levels')
            self.assertEqual(by_name[setting_name]['options'], [l.value for l in TelegramLogLevel])

    def test_log_levels_are_validated(self):
        self.assertEqual(general_settings.validate_setting(CONF_LOG_LEVEL_INCOMING, 'info'), 'info')
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_LOG_LEVEL_INCOMING, 'verbose')

    async def test_log_levels_are_off_by_default(self):
        hass = hass_with()
        await general_settings.async_load_overrides(hass)
        settings = config_helpers.get_general_settings_from_configuration(hass)

        for setting_name in [CONF_LOG_LEVEL_INCOMING, CONF_LOG_LEVEL_OUTGOING, CONF_LOG_LEVEL_POLLING,
                             CONF_LOG_LEVEL_BUS_MESSAGES, CONF_LOG_LEVEL_UNKNOWN_DEVICES,
                             CONF_LOG_LEVEL_DECODE_ERRORS]:
            self.assertEqual(settings[setting_name], TelegramLogLevel.OFF.value, msg=setting_name)
