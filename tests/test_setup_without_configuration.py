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

from custom_components.eltako import config_flow, eltako_integration_init
from custom_components.eltako.const import (CONF_GATEWAY_DESCRIPTION, CONF_HUB, DATA_ELTAKO,
                                            DATA_INITIAL_DETECTION, HUB_TITLE, HUB_UNIQUE_ID)


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
        entry = FakeEntry({CONF_HUB: True})

        self.assertTrue(run(eltako_integration_init.async_setup_hub_entry(hass, entry)))

    def test_async_setup_entry_routes_the_hub_entry(self):
        """Without the branch it would fail on the missing gateway description."""
        hass = FakeHass()
        entry = FakeEntry({CONF_HUB: True})

        with mock.patch.object(eltako_integration_init, 'async_setup_hub_entry',
                               return_value=asyncio.sleep(0, result=True)) as setup_hub:
            self.assertTrue(run(eltako_integration_init.async_setup_entry(hass, entry)))

        setup_hub.assert_called_once()

    def test_unloading_it_does_not_touch_any_platform(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_HUB: True})

        # no config_entries attribute on purpose: touching the platforms would raise here
        self.assertTrue(run(eltako_integration_init.async_unload_entry(hass, entry)))

    def test_no_device_belongs_to_it(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_HUB: True})
        device_entry = mock.Mock(identifiers={('eltako', 'FF-BB-00-01')})

        self.assertTrue(run(eltako_integration_init.async_remove_config_entry_device(
            hass, entry, device_entry)))


class TestTheDetectionRunsOnceAfterInstalling(TestCase):

    def test_it_starts_when_the_flow_asked_for_it(self):
        hass = FakeHass({DATA_ELTAKO: {DATA_INITIAL_DETECTION: True}})
        entry = FakeEntry({CONF_HUB: True})

        run(eltako_integration_init.async_setup_hub_entry(hass, entry))

        self.assertEqual(1, len(hass.tasks), msg='the detection was not started')

    def test_it_does_not_start_again_on_the_next_restart(self):
        """Reading an RS485 bus locks it for minutes - once, not on every start."""
        hass = FakeHass({DATA_ELTAKO: {DATA_INITIAL_DETECTION: True}})
        entry = FakeEntry({CONF_HUB: True})

        run(eltako_integration_init.async_setup_hub_entry(hass, entry))
        run(eltako_integration_init.async_setup_hub_entry(hass, entry))

        self.assertEqual(1, len(hass.tasks))
        self.assertNotIn(DATA_INITIAL_DETECTION, hass.data[DATA_ELTAKO])

    def test_nothing_runs_without_the_flag(self):
        hass = FakeHass()
        entry = FakeEntry({CONF_HUB: True})

        run(eltako_integration_init.async_setup_hub_entry(hass, entry))

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

    def test_the_automatic_way_is_offered_first(self):
        result = run(self._flow().async_step_user())

        self.assertEqual('menu', result['type'])
        self.assertEqual('auto', list(result['menu_options'])[0])

    def test_a_gateway_of_the_configuration_can_still_be_picked_up(self):
        result = run(self._flow(available=['EnOcean Gateway 1 (fam14)']).async_step_user())

        self.assertEqual(['auto', 'detect', 'new_gateway'], list(result['menu_options']))

    def test_the_manual_way_stays_available(self):
        result = run(self._flow().async_step_user())

        self.assertIn('new_gateway', result['menu_options'],
                      msg='a gateway which is not detected has to be addable by hand')

    def test_the_integration_is_only_set_up_once(self):
        """With the hub in place the menu is about gateways only."""
        flow = self._flow(entries=[FakeEntry({CONF_HUB: True})])

        self.assertTrue(flow._hub_exists())

        with mock.patch.object(config_flow.EltakoFlowHandler, 'async_step_new_gateway',
                               new=mock.AsyncMock(return_value={'type': 'form'})) as wizard:
            run(flow.async_step_user())

        wizard.assert_awaited_once()

    def test_a_gateway_entry_is_not_mistaken_for_the_hub(self):
        flow = self._flow(entries=[FakeEntry({CONF_GATEWAY_DESCRIPTION: 'EnOcean Gateway 1 (fam14)'})])

        self.assertFalse(flow._hub_exists())

    def test_the_entry_it_creates_carries_no_gateway(self):
        flow = self._flow()
        flow.async_set_unique_id = mock.AsyncMock()
        flow._abort_if_unique_id_configured = mock.Mock()
        flow.async_create_entry = mock.Mock(side_effect=lambda **kwargs: kwargs)

        result = run(flow.async_step_auto())

        self.assertEqual(HUB_TITLE, result['title'])
        self.assertEqual({CONF_HUB: True}, result['data'])
        self.assertNotIn(CONF_GATEWAY_DESCRIPTION, result['data'])
        flow.async_set_unique_id.assert_awaited_once_with(HUB_UNIQUE_ID)

    def test_it_requests_the_detection(self):
        flow = self._flow()
        flow.async_set_unique_id = mock.AsyncMock()
        flow._abort_if_unique_id_configured = mock.Mock()
        flow.async_create_entry = mock.Mock(return_value={})

        run(flow.async_step_auto())

        self.assertTrue(flow.hass.data[DATA_ELTAKO][DATA_INITIAL_DETECTION])


if __name__ == '__main__':
    unittest.main()
