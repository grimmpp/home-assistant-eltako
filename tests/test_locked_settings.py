"""'Web ui enabled' is shown but not switchable from the web ui.

Switching it off there removes the page the switch is on, and there is no way back through the
yaml: an override stored by the web ui wins over `configuration.yaml`, so `enable_frontend: true`
has no effect against it. Recovery would mean deleting `.storage/eltako_general_settings` by hand.

Two paths lead into that trap and both are closed here - writing the override, and *resetting*
it (the default of the setting is False, so dropping the override switches the ui off just the
same). The setting stays fully usable in configuration.yaml.
"""

import asyncio
import os
import re
from unittest import TestCase, mock

from custom_components.eltako import config_helpers, general_settings
from custom_components.eltako.config_helpers import DEFAULT_GENERAL_SETTINGS
from custom_components.eltako.const import (CONF_ENABLE_FRONTEND, DATA_ELTAKO, DATA_SETTINGS_OVERRIDES,
                                            ELTAKO_CONFIG, CONF_GERNERAL_SETTINGS)


def run(coroutine):
    return asyncio.run(coroutine)


class FakeStore:
    def __init__(self):
        self.saved = None

    async def async_save(self, data):
        self.saved = data


class FakeHass:
    """Enough of hass for the override functions: yaml config plus the override dict."""

    def __init__(self, yaml_settings=None, overrides=None):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: {CONF_GERNERAL_SETTINGS: dict(yaml_settings or {})},
                                   DATA_SETTINGS_OVERRIDES: dict(overrides or {})}}

    @property
    def overrides(self):
        return self.data[DATA_ELTAKO][DATA_SETTINGS_OVERRIDES]


class TestTheSettingIsLocked(TestCase):

    def test_the_web_ui_switch_is_marked_locked(self):
        descriptor = next(entry for entry in general_settings.SETTING_DESCRIPTORS
                          if entry['name'] == CONF_ENABLE_FRONTEND)

        self.assertTrue(descriptor.get('locked'))
        self.assertIn(CONF_ENABLE_FRONTEND, general_settings.LOCKED_SETTINGS)

    def test_it_is_still_offered(self):
        """Greyed out, not hidden - the value stays visible, e.g. for a bug report."""
        names = [entry['name'] for entry in general_settings.SETTING_DESCRIPTORS]

        self.assertIn(CONF_ENABLE_FRONTEND, names)

    def test_the_help_text_points_at_the_yaml(self):
        descriptor = next(entry for entry in general_settings.SETTING_DESCRIPTORS
                          if entry['name'] == CONF_ENABLE_FRONTEND)

        self.assertIn('configuration.yaml', descriptor['help'])

    def test_nothing_else_is_locked(self):
        """Locking is a trapdoor fix, not a habit - every other setting stays editable."""
        self.assertEqual({CONF_ENABLE_FRONTEND}, set(general_settings.LOCKED_SETTINGS))


class TestWritingIsRefused(TestCase):

    def setUp(self):
        self.store = FakeStore()
        patcher = mock.patch.object(general_settings, '_store', return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_switching_it_off_does_not_reach_the_store(self):
        hass = FakeHass(overrides={CONF_ENABLE_FRONTEND: True})

        validated = run(general_settings.async_set_overrides(hass, {CONF_ENABLE_FRONTEND: False}))

        self.assertNotIn(CONF_ENABLE_FRONTEND, validated)
        self.assertTrue(hass.overrides[CONF_ENABLE_FRONTEND], msg='the override was changed')

    def test_saving_the_whole_form_still_works(self):
        """The page sends every field back, so the locked one arrives on each save."""
        hass = FakeHass(overrides={CONF_ENABLE_FRONTEND: True})

        validated = run(general_settings.async_set_overrides(hass, {
            CONF_ENABLE_FRONTEND: True, 'show_dev_id_in_dev_name': True}))

        self.assertEqual({'show_dev_id_in_dev_name': True}, validated)
        self.assertTrue(hass.overrides['show_dev_id_in_dev_name'])

    def test_the_other_settings_of_the_same_call_are_stored(self):
        hass = FakeHass()

        run(general_settings.async_set_overrides(hass, {
            CONF_ENABLE_FRONTEND: False, 'fast_status_change': True}))

        self.assertNotIn(CONF_ENABLE_FRONTEND, hass.overrides)
        self.assertTrue(hass.overrides['fast_status_change'])


class TestResettingIsRefused(TestCase):
    """A reset falls back to the yaml - and a yaml which switched the ui off would take it away."""

    def setUp(self):
        self.store = FakeStore()
        patcher = mock.patch.object(general_settings, '_store', return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_web_ui_is_on_without_any_configuration(self):
        """An installation which never wrote a line of yaml has to reach the web ui."""
        self.assertTrue(DEFAULT_GENERAL_SETTINGS[CONF_ENABLE_FRONTEND])
        self.assertTrue(config_helpers.is_frontend_enabled({}),
                        msg='an empty settings dict is an unconfigured installation')

    def test_resetting_it_directly_is_skipped(self):
        hass = FakeHass(overrides={CONF_ENABLE_FRONTEND: True})

        removed = run(general_settings.async_reset_overrides(hass, [CONF_ENABLE_FRONTEND]))

        self.assertEqual([], removed)
        self.assertTrue(hass.overrides[CONF_ENABLE_FRONTEND])

    def test_reset_all_keeps_it(self):
        hass = FakeHass(overrides={CONF_ENABLE_FRONTEND: True, 'fast_status_change': True})

        removed = run(general_settings.async_reset_overrides(
            hass, [CONF_ENABLE_FRONTEND, 'fast_status_change']))

        self.assertEqual(['fast_status_change'], removed)
        self.assertTrue(hass.overrides[CONF_ENABLE_FRONTEND])
        self.assertNotIn('fast_status_change', hass.overrides)


class TestThePrecedenceThatMakesThisNecessary(TestCase):
    """Documents the behaviour the lock protects against."""

    def test_the_yaml_cannot_override_an_override(self):
        hass = FakeHass(yaml_settings={CONF_ENABLE_FRONTEND: True},
                        overrides={CONF_ENABLE_FRONTEND: False})

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertFalse(config_helpers.is_frontend_enabled(settings),
                         msg='if this ever passes, the lock can be dropped')

    def test_without_the_override_the_yaml_decides(self):
        hass = FakeHass(yaml_settings={CONF_ENABLE_FRONTEND: True})

        settings = config_helpers.get_general_settings_from_configuration(hass)

        self.assertTrue(config_helpers.is_frontend_enabled(settings))


class TestTheFieldIsRenderedDisabled(TestCase):

    FRONTEND = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            'custom_components', 'eltako', 'frontend')

    def _read(self, *parts):
        with open(os.path.join(self.FRONTEND, *parts), encoding='utf-8') as handle:
            return handle.read()

    def test_the_form_supports_disabled_fields(self):
        form = self._read('lib', 'form.js')

        self.assertIn('field.disabled', form)
        self.assertIn('field-disabled', form)
        # every input type has to carry the attribute, not just the checkbox
        self.assertGreaterEqual(len(re.findall(r'\$\{disabled\}', form)), 6)

    def test_a_disabled_field_is_greyed_out_instead_of_hidden(self):
        form = self._read('lib', 'form.js')
        rule = re.search(r'\.field-disabled input[^{]*\{([^}]*)\}', form)

        self.assertIsNotNone(rule, msg='no style for a disabled field')
        self.assertIn('opacity', rule.group(1))
        self.assertNotIn('display: none', rule.group(1))

    def test_the_settings_page_passes_the_flag_on(self):
        settings = self._read('pages', 'settings.js')

        self.assertIn('disabled: setting.locked === true', settings)

    def test_the_page_offers_no_reset_for_a_locked_setting(self):
        """It would be refused by the backend - offering it would just confuse.

        Three places have to agree: the per-setting 'reset' button, the list 'reset all' sends,
        and the count shown on that button.
        """
        settings = self._read('pages', 'settings.js')

        # only the .filter() calls - the help text also branches on the origin, and that one
        # should keep describing a locked setting as overridden, because it is
        overridden_filters = re.findall(r'\.filter\(\(setting\) => setting\.origin === "ui"([^)]*)\)',
                                        settings)

        self.assertEqual(3, len(overridden_filters), msg='a place to filter went missing')
        for expression in overridden_filters:
            self.assertIn('!setting.locked', expression)

    def test_the_value_is_still_submitted(self):
        """readFields must keep reading it, otherwise saving would drop the key."""
        form = self._read('lib', 'form.js')

        self.assertIn('querySelectorAll("[data-field]")', form)
        self.assertNotIn(':not([disabled])', form)
