"""The general settings are editable on the Home Assistant integration page.

Everything this integration can be told is configurable in its own web ui - which is fine
until the very setting you are looking for is the one which decides whether that web ui is in
the sidebar at all. The 'Configure' button of the integration page therefore offers the same
settings through a Home Assistant options flow, and the web ui got a switch for its sidebar
entry that can be flipped from either side.

Checked here: the form is built from the same descriptors as the web ui (so a new setting
appears in both), saving stores only what really changed, and showing/hiding the panel is a
re-registration which keeps the url alive.
"""

import asyncio
from unittest import TestCase, mock


from homeassistant.components.frontend import DATA_PANELS, async_register_built_in_panel

from tests.test_enocean_logger import HassDataMock

from custom_components.eltako import config_flow
from custom_components.eltako.config import config_helpers, general_settings
from custom_components.eltako.core import integration
from custom_components.eltako.const import (CONF_CORE_ENTRY, CONF_ENABLE_FRONTEND, CONF_GATEWAY_DESCRIPTION,
                                            CONF_GERNERAL_SETTINGS, CONF_PLUG_AND_PLAY_INTERVAL,
                                            CONF_SHOW_PANEL_IN_SIDEBAR, CONF_TELEGRAM_LOG_BUFFER_SIZE,
                                            CONF_UI_DEVICES, DATA_ELTAKO, DATA_SETTINGS_OVERRIDES,
                                            DATA_SETTINGS_STORE, DATA_YAML_CONFIGURED, DOMAIN, PANEL_ICON,
                                            PANEL_TITLE, PANEL_URL_PATH, SETTING_GROUPS)


def run(coroutine):
    return asyncio.run(coroutine)


### ---------------------------------------------------------------------------
### the sidebar entry
### ---------------------------------------------------------------------------

def hass_with_panel(**settings) -> HassDataMock:
    hass = HassDataMock(config={CONF_GERNERAL_SETTINGS: dict(settings)})
    async_register_built_in_panel(
        hass, component_name='custom', sidebar_title=PANEL_TITLE, sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH, config=integration._custom_panel_config(),
        require_admin=True)
    return hass


def panel_of(hass):
    return hass.data[DATA_PANELS][PANEL_URL_PATH]


class TestTheSidebarEntryCanBeSwitched(TestCase):

    def test_it_is_shown_by_default(self):
        self.assertTrue(config_helpers.is_panel_in_sidebar(
            config_helpers.DEFAULT_GENERAL_SETTINGS))

    def test_hiding_it_keeps_the_panel_registered(self):
        """Hidden means 'not in the navigation', not 'gone' - the url has to keep working."""
        hass = hass_with_panel(**{CONF_SHOW_PANEL_IN_SIDEBAR: False})

        integration.async_apply_panel_visibility(
            hass, config_helpers.get_general_settings_from_configuration(hass))

        self.assertIn(PANEL_URL_PATH, hass.data[DATA_PANELS])
        self.assertFalse(panel_of(hass).show_in_sidebar)

    def test_showing_it_again_brings_it_back(self):
        hass = hass_with_panel(**{CONF_SHOW_PANEL_IN_SIDEBAR: False})
        settings = config_helpers.get_general_settings_from_configuration(hass)
        integration.async_apply_panel_visibility(hass, settings)

        integration.async_apply_panel_visibility(hass, {**settings, CONF_SHOW_PANEL_IN_SIDEBAR: True})

        self.assertTrue(panel_of(hass).show_in_sidebar)
        self.assertEqual(PANEL_TITLE, panel_of(hass).sidebar_title)

    def test_it_stays_the_same_panel(self):
        """A different config would load a second web component instead of updating this one."""
        hass = hass_with_panel()
        before = panel_of(hass).config

        integration.async_apply_panel_visibility(
            hass, {**config_helpers.DEFAULT_GENERAL_SETTINGS, CONF_SHOW_PANEL_IN_SIDEBAR: False})

        self.assertEqual(before, panel_of(hass).config)

    def test_nothing_happens_without_a_registered_panel(self):
        hass = HassDataMock(config={})

        integration.async_apply_panel_visibility(
            hass, config_helpers.get_general_settings_from_configuration(hass))

        self.assertEqual({}, hass.data.get(DATA_PANELS, {}))

    def test_a_switched_off_web_ui_is_left_alone(self):
        hass = hass_with_panel(**{CONF_ENABLE_FRONTEND: False})

        integration.async_apply_panel_visibility(
            hass, config_helpers.get_general_settings_from_configuration(hass))

        self.assertTrue(panel_of(hass).show_in_sidebar)


class TestThePanelGoesWithTheLastEntry(TestCase):
    """No entry on the integration page means no entry in the sidebar either.

    An integration without a single config entry is not configured anymore - the panel would
    stay until the next restart and lead into nothing. Adding the integration again has to
    bring it back without a restart, because Home Assistant does not run `async_setup()` a
    second time while the component stays loaded.
    """

    def _hass(self, entries, yaml_configured=False):
        hass = hass_with_panel()
        hass.data[DATA_ELTAKO][DATA_YAML_CONFIGURED] = yaml_configured
        hass.config_entries = FakeConfigEntries(entries)
        return hass

    def test_removing_the_last_entry_removes_it(self):
        entry = FakeEntry()
        hass = self._hass([entry])

        run(integration.async_remove_entry(hass, entry))

        self.assertNotIn(PANEL_URL_PATH, hass.data[DATA_PANELS])

    def test_it_stays_while_another_entry_is_left(self):
        entry, other = FakeEntry(), FakeEntry()
        other.entry_id = 'gateway'
        hass = self._hass([entry, other])

        run(integration.async_remove_entry(hass, entry))

        self.assertIn(PANEL_URL_PATH, hass.data[DATA_PANELS])

    def test_a_yaml_configuration_keeps_it(self):
        """There `eltako:` is what loads the integration - not a config entry."""
        entry = FakeEntry()
        hass = self._hass([entry], yaml_configured=True)

        run(integration.async_remove_entry(hass, entry))

        self.assertIn(PANEL_URL_PATH, hass.data[DATA_PANELS])

    def test_adding_an_entry_brings_it_back(self):
        entry = FakeEntry()
        hass = self._hass([entry])
        run(integration.async_remove_entry(hass, entry))

        run(integration.async_register_panel(
            hass, config_helpers.get_general_settings_from_configuration(hass)))

        self.assertIn(PANEL_URL_PATH, hass.data[DATA_PANELS])
        self.assertTrue(panel_of(hass).show_in_sidebar)

    def test_a_switched_off_web_ui_gets_no_panel(self):
        """Without the frontend nothing serves the panel module - a panel registered anyway
        would sit in the sidebar as a dead link ('Unable to load custom panel')."""
        hass = HassDataMock(config={CONF_GERNERAL_SETTINGS: {CONF_ENABLE_FRONTEND: False}})

        run(integration.async_register_panel(
            hass, config_helpers.get_general_settings_from_configuration(hass)))

        self.assertNotIn(PANEL_URL_PATH, hass.data.get(DATA_PANELS, {}))

    def test_registering_twice_does_not_raise(self):
        """Home Assistant refuses to overwrite a panel - every entry calls this."""
        hass = hass_with_panel()
        settings = config_helpers.get_general_settings_from_configuration(hass)

        run(integration.async_register_panel(hass, settings))
        run(integration.async_register_panel(hass, settings))

        self.assertIn(PANEL_URL_PATH, hass.data[DATA_PANELS])

    def test_deleting_a_gateway_entry_removes_it_from_the_web_ui_too(self):
        """The two halves of a gateway - its stored configuration and its config entry - have
        to go together. Deleting the entry on the Home Assistant integration page used to
        leave the configuration behind, where it was invisible (the web ui lists the running
        gateways) and could not be deleted anymore."""
        entry = FakeEntry()
        entry.data = {CONF_GATEWAY_DESCRIPTION: 'Cellar - fgw14usb (Id: 3)'}
        hass = self._hass([entry])
        removed = []

        async def async_remove_gateway(_hass, gateway_id):
            removed.append(gateway_id)
            return True

        with mock.patch.object(integration.gateway_config, 'async_remove_gateway',
                               async_remove_gateway):
            run(integration.async_remove_entry(hass, entry))

        self.assertEqual([3], removed)

    def test_deleting_the_core_entry_touches_no_gateway(self):
        """It carries no gateway description - there is nothing of its own to remove."""
        entry = FakeEntry()
        hass = self._hass([entry])
        removed = []

        async def async_remove_gateway(_hass, gateway_id):
            removed.append(gateway_id)
            return True

        with mock.patch.object(integration.gateway_config, 'async_remove_gateway',
                               async_remove_gateway):
            run(integration.async_remove_entry(hass, entry))

        self.assertEqual([], removed)

    def test_removing_it_twice_does_not_raise(self):
        entry = FakeEntry()
        hass = self._hass([entry])

        run(integration.async_remove_entry(hass, entry))
        run(integration.async_remove_entry(hass, entry))

        self.assertNotIn(PANEL_URL_PATH, hass.data[DATA_PANELS])


### ---------------------------------------------------------------------------
### the options flow
### ---------------------------------------------------------------------------

class FakeEntry:
    def __init__(self, options=None):
        self.entry_id = 'core'
        self.domain = DOMAIN
        self.data = {CONF_CORE_ENTRY: True}
        self.options = dict(options or {})


class FakeConfigEntries:
    def __init__(self, entries):
        self._entries = list(entries) if isinstance(entries, (list, tuple)) else [entries]

    def async_get_known_entry(self, entry_id):
        return next(entry for entry in self._entries if entry.entry_id == entry_id)

    def async_entries(self, domain=None):
        return list(self._entries)


class StoreMock:
    def __init__(self):
        self.saved = None

    async def async_load(self):
        return None

    async def async_save(self, data):
        self.saved = data


def options_flow(**yaml_settings):
    hass = HassDataMock(config={CONF_GERNERAL_SETTINGS: dict(yaml_settings)})
    hass.data[DATA_ELTAKO][DATA_SETTINGS_STORE] = StoreMock()
    entry = FakeEntry()
    hass.config_entries = FakeConfigEntries(entry)

    flow = config_flow.EltakoOptionsFlowHandler()
    flow.hass = hass
    flow.handler = entry.entry_id
    flow.flow_id = 'flow'
    return flow, hass


def labels_of(result) -> list[str]:
    return [str(key) for key in result['data_schema'].schema]


class TestEveryGroupIsReachable(TestCase):

    def test_the_menu_offers_all_of_them(self):
        flow, _hass = options_flow()

        result = run(flow.async_step_init())

        self.assertEqual({group_id for group_id, _label, _help in SETTING_GROUPS},
                         set(result['menu_options']))

    def test_each_one_has_a_step(self):
        for group_id, _label, _help in SETTING_GROUPS:
            self.assertTrue(hasattr(config_flow.EltakoOptionsFlowHandler, f'async_step_{group_id}'),
                            msg=group_id)

    def test_every_setting_of_the_web_ui_is_offered_somewhere(self):
        offered = set()
        for group_id, _label, _help in SETTING_GROUPS:
            offered |= {descriptor['name']
                        for descriptor in config_flow._editable_descriptors(group_id)}

        expected = {descriptor['name'] for descriptor in general_settings.SETTING_DESCRIPTORS
                    if not descriptor.get('locked')}
        self.assertEqual(expected, offered)


class TestTheFormMatchesTheWebUi(TestCase):

    def test_the_fields_are_named_like_in_the_web_ui(self):
        flow, _hass = options_flow()

        result = run(flow.async_step_web_ui())

        self.assertIn('Show in sidebar', labels_of(result))

    def test_locked_settings_are_not_offered(self):
        """'Web ui enabled' cannot be switched off here - see LOCKED_SETTINGS."""
        flow, _hass = options_flow()

        result = run(flow.async_step_web_ui())

        self.assertNotIn('Web ui enabled', labels_of(result))
        self.assertNotIn(CONF_ENABLE_FRONTEND,
                         [descriptor['name'] for descriptor in config_flow._editable_descriptors('web_ui')])

    def test_the_current_values_are_prefilled(self):
        flow, _hass = options_flow(**{CONF_TELEGRAM_LOG_BUFFER_SIZE: 42})

        result = run(flow.async_step_telegram_log())

        default = next(key.default() for key in result['data_schema'].schema
                       if str(key) == 'Live buffer size')
        self.assertEqual(42, default)

    def test_the_help_of_every_setting_is_shown(self):
        flow, _hass = options_flow()

        result = run(flow.async_step_plug_and_play())

        self.assertIn('Plug & play enabled', result['description_placeholders']['help'])


class TestSaving(TestCase):

    def test_a_changed_value_becomes_an_override(self):
        flow, hass = options_flow()

        with mock.patch.object(general_settings, 'async_apply_settings',
                               return_value=asyncio.sleep(0, result={})) as applied:
            result = run(flow.async_step_web_ui({'Show in sidebar': False,
                                                 'Test page enabled': True}))

        self.assertEqual('create_entry', result['type'])
        self.assertEqual({CONF_SHOW_PANEL_IN_SIDEBAR: False},
                         hass.data[DATA_ELTAKO][DATA_SETTINGS_OVERRIDES])
        applied.assert_called_once()

    def test_unchanged_values_are_not_stored(self):
        """Otherwise saving one form would detach the whole group from configuration.yaml."""
        flow, hass = options_flow(**{CONF_TELEGRAM_LOG_BUFFER_SIZE: 42})
        current = config_helpers.get_general_settings_from_configuration(hass)

        with mock.patch.object(general_settings, 'async_apply_settings',
                               return_value=asyncio.sleep(0, result={})) as applied:
            run(flow.async_step_telegram_log({
                descriptor['label']: current[descriptor['name']]
                for descriptor in config_flow._editable_descriptors('telegram_log')}))

        self.assertEqual({}, hass.data[DATA_ELTAKO].get(DATA_SETTINGS_OVERRIDES, {}))
        applied.assert_not_called()

    def test_the_entry_options_are_not_touched(self):
        """The settings live in their own store - the options of the entry hold the devices."""
        flow, hass = options_flow()
        flow.config_entry.options = {CONF_UI_DEVICES: {'light': []}}

        with mock.patch.object(general_settings, 'async_apply_settings',
                               return_value=asyncio.sleep(0, result={})):
            result = run(flow.async_step_general({'Fast status change': True}))

        self.assertEqual({CONF_UI_DEVICES: {'light': []}}, result['data'])

    def test_an_impossible_value_is_reported_on_the_field(self):
        flow, hass = options_flow()

        result = run(flow.async_step_plug_and_play({'Check every (minutes)': 999999}))

        self.assertEqual('form', result['type'])
        self.assertEqual({'Check every (minutes)': 'invalid_setting'}, result['errors'])
        self.assertEqual({}, hass.data[DATA_ELTAKO].get(DATA_SETTINGS_OVERRIDES, {}))

    def test_a_number_arriving_as_a_float_is_accepted(self):
        """The number selector of Home Assistant hands integers over as floats."""
        flow, hass = options_flow()

        with mock.patch.object(general_settings, 'async_apply_settings',
                               return_value=asyncio.sleep(0, result={})):
            run(flow.async_step_plug_and_play({'Check every (minutes)': 60.0}))

        self.assertEqual({CONF_PLUG_AND_PLAY_INTERVAL: 60},
                         hass.data[DATA_ELTAKO][DATA_SETTINGS_OVERRIDES])
