"""The user always knows what runs in the background.

Reading an RS485 bus takes minutes, locks that bus (the devices on it do not react meanwhile)
and makes every other bus operation fail. Whoever started it sees a progress card on their own
page - but after a page switch, a browser reload or on a second tab there was nothing to see:
buttons which did nothing, and no way to tell a slow operation from a broken one.

`core/websocket.get_activity` is the one answer to "what is running right now" which every
page of the web ui polls (`eltako/activity`). This pins what it reports:

* a plug & play run and every gateway whose bus is taken (scan, teach-in, base id request)
* what each job blocks, so the web ui can disable exactly those buttons
* how far a bus scan is, so waiting has a number
* and that a quiet system answers "nothing runs" instead of an error
"""
import unittest
from unittest import mock, TestCase

from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.const import DATA_BUS_MEMBERS, DATA_ELTAKO, DATA_PLUG_AND_PLAY
from custom_components.eltako.core import websocket
from custom_components.eltako.observation import bus_members


class GatewayStub:
    """Only what get_activity looks at - it must not touch the hardware or the bus."""

    def __init__(self, dev_id: int, name: str, busy_with: str = None):
        self.dev_id = dev_id
        self.dev_name = name
        self._busy_with = busy_with

    @property
    def is_bus_busy(self) -> bool:
        return self._busy_with is not None

    @property
    def bus_busy_reason(self):
        return self._busy_with


class BrokenGatewayStub(GatewayStub):
    """A gateway which is not initialized yet - asking it raises."""

    @property
    def is_bus_busy(self) -> bool:
        raise AttributeError("no bus yet")


class TestActivity(TestCase):

    def setUp(self):
        self.hass = HassDataMock()
        self.hass.data[DATA_ELTAKO][DATA_PLUG_AND_PLAY] = {'running': False}
        self.hass.data[DATA_ELTAKO][DATA_BUS_MEMBERS] = None
        bus_members.SCAN_PROGRESS.clear()
        self.addCleanup(bus_members.SCAN_PROGRESS.clear)

    def _gateways(self, *gateways):
        """get_gateways() checks the type, so the stubs are handed in directly."""
        return mock.patch.object(websocket, 'get_gateways', return_value=list(gateways))

    def test_nothing_runs(self):
        with self._gateways():
            activity = websocket.get_activity(self.hass)
        self.assertEqual({'busy': False, 'jobs': []}, activity)

    def test_a_detection_is_reported_with_its_step(self):
        self.hass.data[DATA_ELTAKO][DATA_PLUG_AND_PLAY] = {
            'running': True, 'step': "Reading the bus", 'stage': 'bus',
            'started_at': '2026-08-10T10:00:00+00:00'}
        with self._gateways():
            activity = websocket.get_activity(self.hass)

        self.assertTrue(activity['busy'])
        self.assertEqual(1, len(activity['jobs']))
        job = activity['jobs'][0]
        self.assertEqual('detection', job['kind'])
        self.assertEqual("Reading the bus", job['step'])
        self.assertEqual('2026-08-10T10:00:00+00:00', job['started_at'])
        # a second detection is refused, and a detection reads the buses itself
        self.assertEqual(['detection', 'bus'], job['blocks'])

    def test_a_busy_bus_is_reported_with_its_reason_and_its_gateway(self):
        with self._gateways(GatewayStub(1, 'FAM14', 'bus scan'), GatewayStub(2, 'FAM-USB')):
            activity = websocket.get_activity(self.hass)

        self.assertTrue(activity['busy'])
        self.assertEqual(1, len(activity['jobs']), 'only the busy gateway is a job')
        job = activity['jobs'][0]
        self.assertEqual('bus', job['kind'])
        self.assertEqual(1, job['gateway_id'])
        self.assertEqual('FAM14', job['gateway_name'])
        self.assertEqual('bus scan', job['reason'])
        # both tokens: "no bus operation at all" and "nothing on this gateway"
        self.assertEqual(['bus', 'gateway:1'], job['blocks'])

    def test_the_progress_of_a_running_scan_is_part_of_the_answer(self):
        bus_members.SCAN_PROGRESS[1] = {
            'gateway_id': 1, 'positions_total': 14, 'positions_done': 3, 'percent': 24,
            'started_at': '2026-08-10T10:00:00+00:00'}
        with self._gateways(GatewayStub(1, 'FAM14', 'bus scan')):
            job = websocket.get_activity(self.hass)['jobs'][0]

        self.assertEqual(24, job['progress']['percent'])
        # without a progress entry there is no start time of the job either
        self.assertEqual('2026-08-10T10:00:00+00:00', job['started_at'])

    def test_a_teach_in_blocks_the_bus_just_like_a_scan(self):
        with self._gateways(GatewayStub(1, 'FAM14', 'teaching in the senders')):
            job = websocket.get_activity(self.hass)['jobs'][0]
        self.assertEqual('teaching in the senders', job['reason'])
        self.assertIn('bus', job['blocks'])

    def test_a_detection_which_reads_a_bus_is_reported_as_both(self):
        self.hass.data[DATA_ELTAKO][DATA_PLUG_AND_PLAY] = {'running': True, 'stage': 'bus'}
        with self._gateways(GatewayStub(1, 'FAM14', 'bus scan')):
            jobs = websocket.get_activity(self.hass)['jobs']
        self.assertEqual(['detection', 'bus'], [job['kind'] for job in jobs])

    def test_a_gateway_which_is_not_initialized_is_skipped_not_an_error(self):
        with self._gateways(BrokenGatewayStub(1, 'FAM14'), GatewayStub(2, 'FGW14', 'bus scan')):
            jobs = websocket.get_activity(self.hass)['jobs']
        self.assertEqual([2], [job['gateway_id'] for job in jobs])


if __name__ == '__main__':
    unittest.main()
