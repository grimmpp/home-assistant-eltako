"""A bus scan which breaks off is continued where it stopped - and the senders it needs.

Reading a bus takes minutes, and it can end in the middle for reasons which have nothing to do
with the position being read: the serial connection dies, the port throws, the gateway stops
answering for a moment. Starting at position 1 again would read everything a second time, so
the positions which are done are remembered and the next attempt only visits the rest.

The second half of this file is about the addresses which are written into the actuators: the
ones of Home Assistant (teach-in) and the ones of *another* gateway - because an installation
is read and programmed with a FAM14 but usually operated with something else afterwards, and a
wireless gateway may only transmit senders out of its own base id range.
"""
import asyncio
from unittest import TestCase, mock

from tests.mocks import GatewayMock
from custom_components.eltako.observation import bus_members


class TestTheScanIsResumed(TestCase):

    def setUp(self):
        self.gateway = GatewayMock()
        self.visited = []

    def _bus(self, fail_at=None, fail_times=1):
        """A bus which answers nothing, and blows up at one position for the first attempts."""
        visited = self.visited
        failures = {'left': fail_times}

        async def exchange(request, expected=None, retries=0):
            position = getattr(request, 'address', None)
            visited.append(position)
            if position == fail_at and failures['left'] > 0:
                failures['left'] -= 1
                raise ConnectionResetError("the serial connection died")
            return None

        self.gateway._bus.exchange = exchange
        self.gateway._bus.callback_func = mock.Mock()
        self.gateway._bus.set_callback = mock.Mock()

    def _scan(self, positions, completed=None, attempt=1):
        with mock.patch('eltakobus.locking.lock_bus', mock.AsyncMock(return_value=None)), \
             mock.patch('eltakobus.locking.unlock_bus', mock.AsyncMock()):
            asyncio.run(bus_members._scan_bus(self.gateway, positions, completed, attempt))

    def test_the_scan_reports_which_positions_are_done(self):
        self._bus()
        self.gateway.try_acquire_bus("bus scan")
        completed = set()

        self._scan([1, 2, 3], completed)

        self.assertEqual({1, 2, 3}, completed)

    def test_a_second_attempt_only_visits_what_is_left(self):
        """That is the whole point: 30 positions which were read must not be read again."""
        self._bus()
        self.gateway.try_acquire_bus("bus scan")
        completed = {1, 2, 3, 4}

        self._scan([5, 6], completed)

        self.assertEqual([5, 6], self.visited)
        self.assertEqual({1, 2, 3, 4, 5, 6}, completed)

    def test_a_cancelled_scan_keeps_what_it_had(self):
        self._bus()
        self.gateway.try_acquire_bus("bus scan")
        completed = set()

        async def cancel_after_two(request, expected=None, retries=0):
            self.visited.append(request.address)
            if len(self.visited) >= 2:
                self.gateway.cancel_bus_operation()
            return None

        self.gateway._bus.exchange = cancel_after_two
        self._scan([1, 2, 3, 4, 5], completed)

        self.assertLessEqual(len(completed), 2)
        self.assertNotIn(5, completed)

    def test_the_progress_says_which_attempt_it_is(self):
        """The counters of a second attempt start low again - without the attempt number that
        reads like the scan started over."""
        line = bus_members.describe_scan_progress(
            {'positions_total': 14, 'positions_done': 3, 'attempt': 2, 'attempts': 3})

        self.assertIn('position 4/14', line)
        self.assertIn('attempt 2/3', line)

    def test_a_first_attempt_says_nothing_about_attempts(self):
        line = bus_members.describe_scan_progress(
            {'positions_total': 14, 'positions_done': 3, 'attempt': 1, 'attempts': 3})

        self.assertNotIn('attempt', line)


class TestTheSenderAddressOfAnotherGateway(TestCase):
    """base id of the gateway + the last byte of the actuator address - the rule of the
    EnOcean Device Manager, and the reason an installation can be moved from the FAM14 to a
    wireless gateway at all."""

    def test_the_last_byte_of_the_actuator_lands_in_the_base_id_range(self):
        self.assertEqual('FF-C0-02-04',
                         bus_members.sender_id_for_gateway('FF-C0-02-00', '00-00-00-04'))
        self.assertEqual('FF-C0-02-1A',
                         bus_members.sender_id_for_gateway('FF-C0-02-00', '00-00-00-1A'))

    def test_a_base_id_which_does_not_start_at_zero_is_counted_from(self):
        self.assertEqual('FF-C0-02-14',
                         bus_members.sender_id_for_gateway('FF-C0-02-10', '00-00-00-04'))

    def test_a_wireless_device_has_no_address_on_this_bus(self):
        self.assertIsNone(bus_members.sender_id_for_gateway('FF-C0-02-00', 'FE-DC-BA-98'))

    def test_without_a_base_id_there_is_nothing_to_hand_out(self):
        self.assertIsNone(bus_members.sender_id_for_gateway('', '00-00-00-04'))
        self.assertIsNone(bus_members.sender_id_for_gateway(None, '00-00-00-04'))

    def test_outside_the_range_of_a_base_id_it_refuses(self):
        """A base id covers 128 addresses - beyond that the gateway would not transmit."""
        self.assertIsNone(bus_members.sender_id_for_gateway('FF-C0-02-70', '00-00-00-20'))
