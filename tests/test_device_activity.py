"""Long term activity of EnOcean addresses (persisted across restarts)."""
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

from datetime import datetime, timedelta, timezone

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock


def iso_days_ago(days: float) -> str:
    """Timestamps relative to now, so that the tests are independent of the current date."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds')

from custom_components.eltako.observation import device_activity
from custom_components.eltako.const import *
from custom_components.eltako.observation.device_activity import DeviceActivityTracker
from custom_components.eltako.observation.enocean_logger import resolve_addresses

from eltakobus.message import EltakoWrapped4BS, RPSMessage
from eltakobus.util import AddressExpression


class StoreMock:
    """Replacement for homeassistant.helpers.storage.Store."""

    def __init__(self, data: dict = None):
        self.data = data
        self.saved = None
        self.save_calls = 0

    async def async_load(self):
        return self.data

    def async_delay_save(self, data_func, delay=0):
        self.saved = data_func()
        self.save_calls += 1


class TrackerFixture(IsolatedAsyncioTestCase):

    async def create_tracker(self, stored: dict = None) -> DeviceActivityTracker:
        hass = HassDataMock()
        tracker = DeviceActivityTracker.__new__(DeviceActivityTracker)
        tracker.hass = hass
        tracker._store = StoreMock(stored)
        tracker._activity = {}
        tracker._session_started = "2026-01-01T00:00:00+00:00"
        tracker._unsubscribe = None
        tracker._loaded = False
        # async_load without the home assistant event bus and websocket registration
        loaded = await tracker._store.async_load()
        if loaded and isinstance(loaded.get('activity'), dict):
            tracker._activity = tracker._prune(loaded['activity'])
        tracker._loaded = True
        for entry in tracker._activity.values():
            entry['seen_in_session'] = False
        return tracker


class TestRecording(TrackerFixture):

    async def test_first_telegram_creates_an_entry(self):
        tracker = await self.create_tracker()

        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'Regular4BSMessage', data='00-7D-7D-0A')

        activity = tracker.get_activity('FF-AA-DD-81')
        self.assertEqual(activity['count'], 1)
        self.assertEqual(activity['count_incoming'], 1)
        self.assertEqual(activity['count_outgoing'], 0)
        self.assertEqual(activity['sessions'], 1)
        self.assertTrue(activity['seen_in_this_session'])
        self.assertEqual(activity['last_data'], '00-7D-7D-0A')
        self.assertEqual(activity['msg_types'], {'Regular4BSMessage': 1})
        self.assertIsNotNone(activity['first_seen'])

    async def test_counting_and_directions(self):
        tracker = await self.create_tracker()

        for _ in range(3):
            tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'RPSMessage')
        tracker.record('FF-AA-DD-81', TelegramDirection.OUTGOING.value, 'RPSMessage')

        activity = tracker.get_activity('FF-AA-DD-81')
        self.assertEqual(activity['count'], 4)
        self.assertEqual(activity['count_incoming'], 3)
        self.assertEqual(activity['count_outgoing'], 1)
        self.assertEqual(activity['sessions'], 1)       # still the same session

    async def test_unknown_address_returns_none(self):
        tracker = await self.create_tracker()

        self.assertIsNone(tracker.get_activity('FF-FF-FF-FF'))
        self.assertIsNone(tracker.get_activity(None))

    async def test_lookup_is_case_insensitive(self):
        tracker = await self.create_tracker()
        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'RPSMessage')

        self.assertIsNotNone(tracker.get_activity('ff-aa-dd-81'))

    async def test_recording_without_address_is_ignored(self):
        tracker = await self.create_tracker()

        tracker.record(None, TelegramDirection.INCOMING.value, 'EltakoPoll')

        self.assertEqual(tracker.get_all(), [])

    async def test_decode_errors_are_counted(self):
        tracker = await self.create_tracker()

        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'RPSMessage', decoded_ok=False)

        self.assertEqual(tracker.get_activity('FF-AA-DD-81')['decode_errors'], 1)

    async def test_every_telegram_schedules_a_debounced_save(self):
        tracker = await self.create_tracker()

        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'RPSMessage')

        self.assertEqual(tracker._store.save_calls, 1)
        self.assertIn('FF-AA-DD-81', tracker._store.saved['activity'])
        # the transient session flag must not be persisted
        self.assertNotIn('seen_in_session', tracker._store.saved['activity']['FF-AA-DD-81'])


class TestPersistence(TrackerFixture):

    @property
    def STORED(self) -> dict:
        return {'activity': {
            'FF-AA-DD-81': {'first_seen': iso_days_ago(10), 'last_seen': iso_days_ago(1),
                            'count': 100, 'count_incoming': 100, 'count_outgoing': 0, 'sessions': 3,
                            'msg_types': {'Regular4BSMessage': 100}},
        }}

    async def test_stored_activity_is_loaded(self):
        tracker = await self.create_tracker(self.STORED)

        activity = tracker.get_activity('FF-AA-DD-81')
        self.assertEqual(activity['count'], 100)
        self.assertEqual(activity['sessions'], 3)
        self.assertFalse(activity['seen_in_this_session'])      # not seen after the restart

    async def test_session_counter_increases_once_per_session(self):
        tracker = await self.create_tracker(self.STORED)

        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'Regular4BSMessage')
        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'Regular4BSMessage')

        activity = tracker.get_activity('FF-AA-DD-81')
        self.assertEqual(activity['sessions'], 4)               # 3 + this session
        self.assertEqual(activity['count'], 102)
        self.assertTrue(activity['seen_in_this_session'])

    async def test_very_old_entries_are_dropped(self):
        stored = {'activity': {
            'FF-00-00-01': {'last_seen': iso_days_ago(device_activity.MAX_AGE_DAYS + 10), 'count': 5},
            'FF-00-00-02': {'last_seen': iso_days_ago(1), 'count': 5},
        }}

        tracker = await self.create_tracker(stored)

        # the entry of 2020 is older than MAX_AGE_DAYS
        self.assertIsNone(tracker.get_activity('FF-00-00-01'))

    async def test_number_of_addresses_is_limited(self):
        stored = {'activity': {
            f"FF-00-{index // 256:02X}-{index % 256:02X}": {
                'last_seen': iso_days_ago(index / 1000.0), 'count': 1}
            for index in range(device_activity.MAX_ADDRESSES + 50)
        }}

        tracker = await self.create_tracker(stored)

        self.assertEqual(len(tracker.get_all()), device_activity.MAX_ADDRESSES)

    async def test_broken_entries_do_not_break_loading(self):
        tracker = await self.create_tracker({'activity': {'FF-00-00-01': "not a dict",
                                                          'FF-00-00-02': {'last_seen': 'garbage', 'count': 1}}})

        self.assertIsNone(tracker.get_activity('FF-00-00-01'))
        self.assertIsNotNone(tracker.get_activity('FF-00-00-02'))   # unparsable date is kept

    async def test_clear(self):
        tracker = await self.create_tracker(self.STORED)

        tracker.clear()

        self.assertEqual(tracker.get_all(), [])


class TestDerivedValues(TrackerFixture):

    async def test_telegrams_per_day(self):
        tracker = await self.create_tracker({'activity': {'FF-AA-DD-81': {
            'first_seen': iso_days_ago(3), 'last_seen': iso_days_ago(1), 'count': 300}}})

        # 300 telegrams within 2 days
        self.assertEqual(tracker.get_activity('FF-AA-DD-81')['telegrams_per_day'], 150.0)

    async def test_telegrams_per_day_needs_some_history(self):
        tracker = await self.create_tracker({'activity': {'FF-AA-DD-81': {
            'first_seen': iso_days_ago(0.0007), 'last_seen': iso_days_ago(0.0), 'count': 5}}})

        self.assertIsNone(tracker.get_activity('FF-AA-DD-81')['telegrams_per_day'])

    async def test_silent_since_is_calculated(self):
        tracker = await self.create_tracker()
        tracker.record('FF-AA-DD-81', TelegramDirection.INCOMING.value, 'RPSMessage')

        silent = tracker.get_activity('FF-AA-DD-81')['silent_since_seconds']

        self.assertIsNotNone(silent)
        self.assertLess(silent, 5)


class TestSharedAddressResolution(TestCase):
    """Logger and tracker must derive the same address from a telegram."""

    def test_external_address(self):
        gateway = GatewayMock(base_id=AddressExpression.parse('FF-AA-80-00'))

        address, local = resolve_addresses(gateway, RPSMessage(address=b'\x12\x34\x56\x78', status=0x30, data=b'\x10'))

        self.assertEqual(address, '12-34-56-78')
        self.assertIsNone(local)

    def test_local_bus_address_gets_the_base_id_added(self):
        gateway = GatewayMock(base_id=AddressExpression.parse('FF-AA-80-00'))

        address, local = resolve_addresses(gateway, EltakoWrapped4BS(address=b'\x00\x00\x00\x01', status=0x00,
                                                                    data=b'\x01\x02\x03\x04'))

        self.assertEqual(address, 'FF-AA-80-01')
        self.assertEqual(local, '00-00-00-01')

    def test_bus_messages_have_no_enocean_address(self):
        from eltakobus.message import EltakoDiscoveryRequest

        address, local = resolve_addresses(GatewayMock(), EltakoDiscoveryRequest(8))

        self.assertIsNone(address)
        self.assertIsNone(local)


if __name__ == '__main__':
    unittest.main()
