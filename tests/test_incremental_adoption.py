"""Devices are added while the bus is being read, not at the end of the scan.

Reading the bus of a FAM14 takes minutes: position by position, then memory row by memory row.
Everything the detection found used to be written at the very end, so a user watched a
progress bar with an empty device list - and a scan which was interrupted (timeout, restart)
left nothing at all behind.

Now every position which answered is adopted as soon as it is unambiguous
(`plug_and_play._adopt_while_scanning`). That is only safe together with the second half:
storing a device rewrites the options of the config entry, and Home Assistant reloads a
gateway whose options changed - which would close the serial port under the running scan. So
the reload is postponed while the bus is busy and carried out when it is free
(`core/integration.async_reload_entry` / `async_flush_pending_reloads`).

Both halves are tested here; the scan itself needs hardware and is not part of it.
"""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase, mock

from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.const import (CONF_GATEWAY_DESCRIPTION, DATA_ELTAKO,
                                            DATA_PENDING_RELOADS)
from custom_components.eltako.core import integration
from custom_components.eltako.tools import plug_and_play


def _report() -> dict:
    """The report async_run fills while it runs."""
    return {'devices_added': [], 'devices_skipped': [], 'warnings': []}


class TestAdoptingWhileTheBusIsRead(IsolatedAsyncioTestCase):

    def _patch_sources(self, candidates: list, skipped: list = None):
        """Everything _async_collect_and_add reads, so only its own logic is under test."""
        return [
            mock.patch.object(plug_and_play, 'merge_candidates',
                              return_value={'candidates': candidates, 'skipped': skipped or []}),
            mock.patch.object(plug_and_play, 'derive_bus_candidates', return_value=[]),
            mock.patch.object(plug_and_play, 'derive_memory_candidates', return_value=[]),
            mock.patch.object(plug_and_play, 'derive_telegram_candidates', return_value=[]),
            mock.patch.object(plug_and_play, '_unknown_devices', return_value=[]),
        ]

    async def _collect(self, hass, report, candidates, added, skipped=None, add_devices=True):
        patches = self._patch_sources(candidates, skipped)
        with mock.patch('custom_components.eltako.config.device_config.get_configured_addresses',
                        return_value={'by_gateway': {}, 'all': set()}), \
             mock.patch('custom_components.eltako.simulation.derive_candidates', return_value=[]), \
             mock.patch.object(plug_and_play, '_async_add_devices',
                               return_value=(added, [])) as add:
            for patch in patches:
                patch.start()
            try:
                count = await plug_and_play._async_collect_and_add(hass, report, add_devices)
            finally:
                for patch in patches:
                    patch.stop()
        return count, add

    async def test_a_pass_adds_what_is_identified_and_says_how_many(self):
        hass, report = HassDataMock(), _report()

        count, _ = await self._collect(hass, report, candidates=[{'x': 1}],
                                       added=[{'address': '00-00-00-01'}])

        self.assertEqual(1, count)
        self.assertEqual(['00-00-00-01'], [d['address'] for d in report['devices_added']])

    async def test_the_devices_of_all_passes_add_up(self):
        """The report is filled while the scan runs - a pass must not drop the earlier ones."""
        hass, report = HassDataMock(), _report()

        await self._collect(hass, report, candidates=[{}], added=[{'address': '00-00-00-01'}])
        await self._collect(hass, report, candidates=[{}], added=[{'address': '00-00-00-02'}])

        self.assertEqual(['00-00-00-01', '00-00-00-02'],
                         [d['address'] for d in report['devices_added']])

    async def test_what_still_needs_a_decision_is_the_state_of_the_last_pass(self):
        """A device which was unclear a minute ago can be identified by now - no sum here."""
        hass, report = HassDataMock(), _report()

        await self._collect(hass, report, candidates=[], added=[],
                            skipped=[{'address': 'A'}, {'address': 'B'}])
        await self._collect(hass, report, candidates=[], added=[], skipped=[{'address': 'B'}])

        self.assertEqual(['B'], [entry['address'] for entry in report['devices_skipped']])

    async def test_a_dry_run_stores_nothing(self):
        hass, report = HassDataMock(), _report()

        count, add = await self._collect(hass, report, candidates=[{'x': 1}], added=[],
                                         add_devices=False)

        self.assertEqual(0, count)
        add.assert_not_called()
        self.assertEqual([{'x': 1}], report['devices_pending'])

    async def test_the_adoption_repeats_until_it_is_cancelled(self):
        hass, report = HassDataMock(), _report()
        passes = []

        async def one_pass(_hass, _report, _add):
            passes.append(1)
            return 1

        with mock.patch.object(plug_and_play, 'ADOPT_INTERVAL', 0.01), \
             mock.patch.object(plug_and_play, '_async_collect_and_add', side_effect=one_pass):
            task = asyncio.ensure_future(plug_and_play._adopt_while_scanning(hass, report, True))
            await asyncio.sleep(0.08)
            task.cancel()
            await task

        self.assertGreater(len(passes), 1, 'the adoption ran only once')
        self.assertTrue(task.done())

    async def test_a_failing_pass_does_not_stop_the_scan(self):
        """The bus scan is the expensive part - a broken adoption must not take it down."""
        hass, report = HassDataMock(), _report()
        calls = []

        async def sometimes_broken(_hass, _report, _add):
            calls.append(1)
            if len(calls) == 1:
                raise ValueError("no registry")
            return 0

        with mock.patch.object(plug_and_play, 'ADOPT_INTERVAL', 0.01), \
             mock.patch.object(plug_and_play, '_async_collect_and_add',
                               side_effect=sometimes_broken):
            task = asyncio.ensure_future(plug_and_play._adopt_while_scanning(hass, report, True))
            await asyncio.sleep(0.08)
            task.cancel()
            await task

        self.assertGreater(len(calls), 1, 'the loop died with the first error')


class ConfigEntryStub:
    def __init__(self, entry_id: str, gateway_id: int = 1):
        self.entry_id = entry_id
        self.title = f"Gateway {gateway_id}"
        self.data = {CONF_GATEWAY_DESCRIPTION: f"Gateway {gateway_id} (id: {gateway_id})"}
        self.options = {}


class GatewayStub:
    def __init__(self, busy_with: str = None):
        self._busy_with = busy_with

    @property
    def is_bus_busy(self) -> bool:
        return self._busy_with is not None

    @property
    def bus_busy_reason(self):
        return self._busy_with


class ConfigEntriesStub:
    def __init__(self, entries: dict):
        self._entries = entries
        self.reloaded = []

    def async_get_entry(self, entry_id):
        return self._entries.get(entry_id)

    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)


class TestTheReloadWaitsForTheBus(IsolatedAsyncioTestCase):

    def setUp(self):
        self.entry = ConfigEntryStub('entry-1')
        self.hass = HassDataMock()
        self.hass.config_entries = ConfigEntriesStub({'entry-1': self.entry})

    def _gateway(self, busy_with=None):
        return mock.patch.object(integration, 'get_gateway_from_hass',
                                 return_value=GatewayStub(busy_with))

    def _pending(self):
        return self.hass.data[DATA_ELTAKO].get(DATA_PENDING_RELOADS) or set()

    async def test_a_free_gateway_is_reloaded_right_away(self):
        with self._gateway():
            await integration.async_reload_entry(self.hass, self.entry)

        self.assertEqual(['entry-1'], self.hass.config_entries.reloaded)
        self.assertEqual(set(), self._pending())

    async def test_a_gateway_whose_bus_is_being_read_is_not_reloaded(self):
        """The reload would close the serial port under the running scan."""
        with self._gateway('bus scan'):
            await integration.async_reload_entry(self.hass, self.entry)

        self.assertEqual([], self.hass.config_entries.reloaded)
        self.assertEqual({'entry-1'}, self._pending())

    async def test_the_postponed_reload_happens_when_the_bus_is_free(self):
        with self._gateway('bus scan'):
            await integration.async_reload_entry(self.hass, self.entry)
        with self._gateway():
            reloaded = await integration.async_flush_pending_reloads(self.hass)

        self.assertEqual(['entry-1'], reloaded)
        self.assertEqual(['entry-1'], self.hass.config_entries.reloaded)
        self.assertEqual(set(), self._pending())

    async def test_a_bus_which_is_busy_again_keeps_its_pending_reload(self):
        with self._gateway('teaching in the senders'):
            await integration.async_reload_entry(self.hass, self.entry)
            reloaded = await integration.async_flush_pending_reloads(self.hass)

        self.assertEqual([], reloaded)
        self.assertEqual({'entry-1'}, self._pending(), 'the reload must not be lost')

    async def test_a_gateway_which_was_removed_meanwhile_is_dropped(self):
        with self._gateway('bus scan'):
            await integration.async_reload_entry(self.hass, self.entry)
        self.hass.config_entries = ConfigEntriesStub({})

        reloaded = await integration.async_flush_pending_reloads(self.hass)

        self.assertEqual([], reloaded)
        self.assertEqual(set(), self._pending())

    async def test_flushing_without_anything_pending_is_free(self):
        self.assertEqual([], await integration.async_flush_pending_reloads(self.hass))

    async def test_a_failing_reload_does_not_break_the_finished_scan(self):
        async def boom(entry_id):
            raise RuntimeError("entry is not loaded")

        with self._gateway('bus scan'):
            await integration.async_reload_entry(self.hass, self.entry)
        self.hass.config_entries.async_reload = boom
        with self._gateway():
            reloaded = await integration.async_flush_pending_reloads(self.hass)

        self.assertEqual([], reloaded)
        self.assertEqual(set(), self._pending(), 'a broken entry must not be retried forever')


if __name__ == '__main__':
    unittest.main()
