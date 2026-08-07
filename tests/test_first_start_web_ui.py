"""The web ui is opened once, right after the integration was installed.

'Add integration' asks for nothing, so the moment it is done the place where everything is
configured is a sidebar entry the user has never seen. core/onboarding.py hands one redirect
out to the first browser which asks for it - the checks here are that it is handed out exactly
once, that it is remembered in the config entry (a restart must not repeat the tour) and that
none of it can break the setup of the integration.
"""

import asyncio
import os
import sys
from unittest import TestCase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.eltako.core import onboarding
from custom_components.eltako.const import (CONF_ENABLE_FRONTEND, CONF_GERNERAL_SETTINGS,
                                            CONF_CORE_ENTRY, CONF_ONBOARDING_SHOWN, DATA_ELTAKO,
                                            DATA_ONBOARDING, ELTAKO_CONFIG,
                                            PANEL_ONBOARDING_JS_URL, PANEL_URL_PATH,
                                            WS_ONBOARDING_CONSUME)


def run(coroutine):
    return asyncio.run(coroutine)


class FakeUrlManager:
    """The frontend's registry of extra javascript modules."""

    def __init__(self):
        self.urls = set()

    def add(self, url):
        self.urls.add(url)

    def remove(self, url):
        self.urls.discard(url)


class FakeEntry:
    def __init__(self, data=None):
        self.entry_id = 'core'
        self.data = dict(data or {CONF_CORE_ENTRY: True})


class FakeConfigEntries:
    def __init__(self, entry):
        self._entry = entry

    def async_get_entry(self, entry_id):
        return self._entry if entry_id == self._entry.entry_id else None

    def async_update_entry(self, entry, data=None, **kwargs):
        if data is not None:
            entry.data = dict(data)
        return True


class FakeHass:
    def __init__(self, entry, general_settings=None):
        self.data = {DATA_ELTAKO: {ELTAKO_CONFIG: {CONF_GERNERAL_SETTINGS: dict(general_settings or {})}},
                     DATA_EXTRA_MODULE_URL: FakeUrlManager()}
        self.config_entries = FakeConfigEntries(entry)

    @property
    def modules(self):
        return self.data[DATA_EXTRA_MODULE_URL].urls

    @property
    def websocket_commands(self):
        return set(self.data.get('websocket_api', {}))


class TestTheRedirectIsPreparedOnce(TestCase):

    def test_a_fresh_installation_gets_the_module_and_the_command(self):
        entry = FakeEntry()
        hass = FakeHass(entry)

        self.assertTrue(run(onboarding.async_setup_onboarding(hass, entry)))

        self.assertTrue(onboarding.is_pending(hass))
        self.assertIn(PANEL_ONBOARDING_JS_URL, hass.modules)
        self.assertIn(WS_ONBOARDING_CONSUME, hass.websocket_commands)

    def test_an_installation_which_saw_it_is_left_alone(self):
        entry = FakeEntry({CONF_CORE_ENTRY: True, CONF_ONBOARDING_SHOWN: True})
        hass = FakeHass(entry)

        self.assertFalse(run(onboarding.async_setup_onboarding(hass, entry)))

        self.assertFalse(onboarding.is_pending(hass))
        self.assertEqual(set(), hass.modules)

    def test_nothing_is_opened_when_the_web_ui_is_switched_off(self):
        entry = FakeEntry()
        hass = FakeHass(entry, {CONF_ENABLE_FRONTEND: False})

        self.assertFalse(run(onboarding.async_setup_onboarding(hass, entry)))

        self.assertEqual(set(), hass.modules)
        # and it is not retried on every restart from now on
        self.assertTrue(entry.data[CONF_ONBOARDING_SHOWN])

    def test_a_runtime_without_the_frontend_hooks_does_not_fail(self):
        """The standalone runtime brings its own navigation - it must not break the setup."""
        entry = FakeEntry()
        hass = FakeHass(entry)
        del hass.data[DATA_EXTRA_MODULE_URL]

        self.assertFalse(run(onboarding.async_setup_onboarding(hass, entry)))
        self.assertFalse(onboarding.is_pending(hass))


class TestOnlyOneBrowserIsRedirected(TestCase):

    def _prepared(self):
        entry = FakeEntry()
        hass = FakeHass(entry)
        run(onboarding.async_setup_onboarding(hass, entry))
        return hass, entry

    def test_the_first_caller_gets_it(self):
        hass, _entry = self._prepared()

        self.assertTrue(run(onboarding.async_consume(hass)))

    def test_every_later_caller_does_not(self):
        hass, _entry = self._prepared()
        run(onboarding.async_consume(hass))

        self.assertFalse(run(onboarding.async_consume(hass)))
        self.assertFalse(run(onboarding.async_consume(hass)))

    def test_the_module_is_unregistered_again(self):
        """It is loaded on every page of Home Assistant - it has to go once it is done."""
        hass, _entry = self._prepared()
        run(onboarding.async_consume(hass))

        self.assertEqual(set(), hass.modules)

    def test_a_restart_does_not_repeat_the_tour(self):
        hass, entry = self._prepared()
        run(onboarding.async_consume(hass))

        self.assertTrue(entry.data[CONF_ONBOARDING_SHOWN])

        restarted = FakeHass(entry)
        self.assertFalse(run(onboarding.async_setup_onboarding(restarted, entry)))

    def test_consuming_without_any_setup_is_a_noop(self):
        entry = FakeEntry()
        hass = FakeHass(entry)

        self.assertFalse(run(onboarding.async_consume(hass)))


class TestTheModuleWhichDoesTheNavigation(TestCase):
    """The javascript is loaded into Home Assistant itself, not into the panel."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'custom_components',
                            'eltako', 'frontend', 'eltako-onboarding.js')
        with open(path, encoding='utf-8') as handle:
            cls.source = handle.read()

    def test_it_is_served_under_the_url_which_is_registered(self):
        self.assertTrue(PANEL_ONBOARDING_JS_URL.endswith('/eltako-onboarding.js'))

    def test_it_calls_the_command_of_the_backend(self):
        self.assertIn(WS_ONBOARDING_CONSUME, self.source)

    def test_it_knows_the_panel_url(self):
        self.assertIn(f'"/{PANEL_URL_PATH}"', self.source)

    def test_it_imports_nothing(self):
        """It runs on every page of Home Assistant, so it stays a single small file."""
        self.assertNotIn('import ', self.source)
