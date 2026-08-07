"""Installing the integration must not require anything to be entered.

'Add integration' creates one entry which carries no gateway at all: it is the integration
itself. That entry is what makes Home Assistant set the component up, which brings the web ui
into the sidebar - and from there gateways and devices are configured graphically. Right after
it was added the detection runs once so a connected gateway shows up on its own; a gateway
which is not detected is added in the web ui (or in `configuration.yaml`).

Everything that iterates the config entries has to survive an entry without a gateway
description, which is why those call sites are checked here as well.
"""

import asyncio
import os
import sys
import unittest
from unittest import TestCase, mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.eltako import config_flow
from custom_components.eltako.core import integration
from custom_components.eltako.const import (CONF_GATEWAY_DESCRIPTION, CONF_CORE_ENTRY, DATA_ELTAKO,
                                            DATA_INITIAL_DETECTION, CORE_TITLE, CORE_UNIQUE_ID,
                                            OLD_CORE_TITLES)


def run(coroutine):
    return asyncio.run(coroutine)


class FakeEntry:
    def __init__(self, data=None, entry_id='entry'):
        self.data = dict(data or {})
        self.entry_id = entry_id
        self.domain = 'eltako'
        self.title = 'test'
        self.unique_id = None
        self.version = 1
        self.state = 'loaded'
        self.options = {}


class FakeHass:
    """Enough of hass to set an entry up: the data dict and the task factory."""

    def __init__(self, data=None):
        self.data = dict(data or {})
        self.tasks = []

    def async_create_task(self, coroutine, name=None):
        # the coroutine is not awaited here - closing it keeps the test free of warnings
        coroutine.close()
        self.tasks.append(name or 'task')
        return None


class TestTheHubEntryNeedsNoGateway(TestCase):

    def test_it_is_set_up_without_any_configuration(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        self.assertTrue(run(integration.async_setup_core_entry(hass, entry)))

    def test_async_setup_entry_routes_the_core_entry(self):
        """Without the branch it would fail on the missing gateway description."""
        hass = FakeHass()
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        with mock.patch.object(integration, 'async_setup_core_entry',
                               return_value=asyncio.sleep(0, result=True)) as setup_core:
            self.assertTrue(run(integration.async_setup_entry(hass, entry)))

        setup_core.assert_called_once()

    def test_unloading_it_does_not_touch_any_platform(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        # no config_entries attribute on purpose: touching the platforms would raise here
        self.assertTrue(run(integration.async_unload_entry(hass, entry)))

    def test_no_device_belongs_to_it(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_CORE_ENTRY: True})
        device_entry = mock.Mock(identifiers={('eltako', 'FF-BB-00-01')})

        self.assertTrue(run(integration.async_remove_config_entry_device(
            hass, entry, device_entry)))


class TestTheDetectionRunsOnceAfterInstalling(TestCase):

    def test_it_starts_when_the_flow_asked_for_it(self):
        hass = FakeHass({DATA_ELTAKO: {DATA_INITIAL_DETECTION: True}})
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        run(integration.async_setup_core_entry(hass, entry))

        self.assertEqual(1, len(hass.tasks), msg='the detection was not started')

    def test_it_does_not_start_again_on_the_next_restart(self):
        """Reading an RS485 bus locks it for minutes - once, not on every start."""
        hass = FakeHass({DATA_ELTAKO: {DATA_INITIAL_DETECTION: True}})
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        run(integration.async_setup_core_entry(hass, entry))
        run(integration.async_setup_core_entry(hass, entry))

        self.assertEqual(1, len(hass.tasks))
        self.assertNotIn(DATA_INITIAL_DETECTION, hass.data[DATA_ELTAKO])

    def test_nothing_runs_without_the_flag(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_CORE_ENTRY: True})

        run(integration.async_setup_core_entry(hass, entry))

        self.assertEqual([], hass.tasks)


class FakeConfigEntries:
    def __init__(self, entries):
        self._entries = entries

    def async_entries(self, domain):
        return list(self._entries)


class TestTheConfigFlowAsksForNothing(TestCase):

    def _flow(self, entries=(), available=()):
        flow = config_flow.EltakoFlowHandler()
        flow.hass = mock.Mock(config_entries=FakeConfigEntries(list(entries)),
                              data={DATA_ELTAKO: {}})
        flow._async_get_available_gateways = mock.AsyncMock(return_value=list(available))
        return flow

    def test_the_first_run_asks_nothing_at_all(self):
        """Adding the integration is what loads it - and the web ui is behind that."""
        flow = self._flow()

        with mock.patch.object(config_flow.EltakoFlowHandler, 'async_step_auto',
                               new=mock.AsyncMock(return_value={'type': 'create_entry'})) as auto:
            result = run(flow.async_step_user())

        auto.assert_awaited_once()
        self.assertEqual('create_entry', result['type'])

    def test_the_core_entry_is_created_even_when_there_is_something_to_pick_up(self):
        """Installing is not a choice - a gateway of the yaml is picked up afterwards."""
        flow = self._flow(available=['EnOcean Gateway 1 (fam14)'])

        with mock.patch.object(config_flow.EltakoFlowHandler, 'async_step_auto',
                               new=mock.AsyncMock(return_value={'type': 'create_entry'})) as auto:
            run(flow.async_step_user())

        auto.assert_awaited_once()

    def test_there_is_no_menu_entry_for_the_base_installation(self):
        """It always happens, so offering it as an option would be a question without an answer."""
        flow = self._flow(entries=[FakeEntry({CONF_CORE_ENTRY: True})],
                          available=['EnOcean Gateway 1 (fam14)'])

        result = run(flow.async_step_user())

        self.assertNotIn('auto', result['menu_options'])

    def test_the_manual_way_stays_available(self):
        flow = self._flow(entries=[FakeEntry({CONF_CORE_ENTRY: True})],
                          available=['EnOcean Gateway 1 (fam14)'])

        result = run(flow.async_step_user())

        self.assertEqual(['detect', 'new_gateway'], list(result['menu_options']),
                         msg='a gateway which is not detected has to be addable by hand')

    def test_the_integration_is_only_set_up_once(self):
        """With the core entry in place the menu is about gateways only."""
        flow = self._flow(entries=[FakeEntry({CONF_CORE_ENTRY: True})])

        self.assertTrue(flow._core_entry_exists())

        with mock.patch.object(config_flow.EltakoFlowHandler, 'async_step_new_gateway',
                               new=mock.AsyncMock(return_value={'type': 'form'})) as wizard:
            run(flow.async_step_user())

        wizard.assert_awaited_once()

    def test_a_gateway_entry_is_not_mistaken_for_the_core_entry(self):
        flow = self._flow(entries=[FakeEntry({CONF_GATEWAY_DESCRIPTION: 'EnOcean Gateway 1 (fam14)'})])

        self.assertFalse(flow._core_entry_exists())

    def test_the_entry_it_creates_carries_no_gateway(self):
        flow = self._flow()
        flow.async_set_unique_id = mock.AsyncMock()
        flow._abort_if_unique_id_configured = mock.Mock()
        flow.async_create_entry = mock.Mock(side_effect=lambda **kwargs: kwargs)

        result = run(flow.async_step_auto())

        self.assertEqual(CORE_TITLE, result['title'])
        self.assertEqual({CONF_CORE_ENTRY: True}, result['data'])
        self.assertNotIn(CONF_GATEWAY_DESCRIPTION, result['data'])
        flow.async_set_unique_id.assert_awaited_once_with(CORE_UNIQUE_ID)

    def test_it_requests_the_detection(self):
        flow = self._flow()
        flow.async_set_unique_id = mock.AsyncMock()
        flow._abort_if_unique_id_configured = mock.Mock()
        flow.async_create_entry = mock.Mock(return_value={})

        run(flow.async_step_auto())

        self.assertTrue(flow.hass.data[DATA_ELTAKO][DATA_INITIAL_DETECTION])


class TestTheCoreEntryIsNamedAfterWhatItIs(TestCase):
    """It is the base component - web ui, websocket api, detection - not a piece of hardware.

    It used to be titled like the integration itself, which read as if it were a device sitting
    next to the gateways. What is stored stays untouched: the key in the entry data and its
    unique id would turn the core entry of an upgraded installation into an unrecognised one.
    """

    def test_the_stored_values_did_not_change(self):
        self.assertEqual('hub', CONF_CORE_ENTRY)
        self.assertEqual('eltako_hub', CORE_UNIQUE_ID)

    def test_the_title_says_what_it_is(self):
        self.assertEqual('ELTAKO Core', CORE_TITLE)
        self.assertNotIn(CORE_TITLE, OLD_CORE_TITLES)

    def test_an_installation_with_the_old_title_is_renamed(self):
        entry = FakeEntry({CONF_CORE_ENTRY: True})
        entry.title = OLD_CORE_TITLES[0]
        hass = mock.Mock(data={})

        integration.async_rename_legacy_core_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_called_once_with(entry, title=CORE_TITLE)

    def test_a_title_the_user_picked_is_left_alone(self):
        entry = FakeEntry({CONF_CORE_ENTRY: True})
        entry.title = 'Wohnzimmer'
        hass = mock.Mock(data={})

        integration.async_rename_legacy_core_entry(hass, entry)

        hass.config_entries.async_update_entry.assert_not_called()

    def test_renaming_never_breaks_the_setup(self):
        entry = FakeEntry({CONF_CORE_ENTRY: True})
        entry.title = OLD_CORE_TITLES[0]
        hass = mock.Mock(data={})
        hass.config_entries.async_update_entry.side_effect = ValueError('nope')

        integration.async_rename_legacy_core_entry(hass, entry)      # must not raise


class TestTheShortestYamlIsOneLine(TestCase):
    """`eltako:` and nothing under it has to be a valid configuration.

    Home Assistant sets a custom integration up only for a config entry or for a yaml key -
    copying the files and restarting loads no code at all, so the web ui cannot appear on its
    own. That one line is the file based way to get it, the alternative to adding the
    integration once, and it must not fail validation.
    """

    def test_an_empty_section_is_accepted(self):
        from custom_components.eltako.config.schema import CONFIG_SCHEMA

        self.assertEqual({'eltako': {}}, CONFIG_SCHEMA({'eltako': None}))

    def test_it_reads_as_a_configuration_without_gateways(self):
        from custom_components.eltako.config import config_helpers
        from custom_components.eltako.config.schema import CONFIG_SCHEMA

        async def yaml_config(hass, domain):
            return CONFIG_SCHEMA({'eltako': None})

        config = run(config_helpers.async_get_home_assistant_config(None, CONFIG_SCHEMA, yaml_config))

        self.assertEqual([], config.get('gateway', []))

    def test_the_web_ui_is_on_for_it(self):
        """Nobody writes that line for anything but the web ui."""
        from custom_components.eltako.config import config_helpers
        from custom_components.eltako.config.schema import CONFIG_SCHEMA

        settings = CONFIG_SCHEMA({'eltako': None})['eltako'].get('general_settings', {})

        self.assertTrue(config_helpers.is_frontend_enabled(settings))
        self.assertTrue(config_helpers.is_panel_in_sidebar(settings))


if __name__ == '__main__':
    unittest.main()
