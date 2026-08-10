"""Cancelling a bus operation - the way out when the bus does not answer anymore.

A bus scan reads every position and every memory row of an RS485 bus; that takes minutes and
holds the bus, so every command of Home Assistant is queued meanwhile. When such a scan hangs
- observed on a real installation: the serial write runs into a timeout and the scan thread
never reaches its own cleanup - the bus stays locked, nothing switches anymore, and from the
outside that is indistinguishable from a scan which is simply slow.

So the web ui can cancel: the running loop is asked to stop *and* the bus is released, whether
or not that loop can still be reached. These tests pin the three things this must not get
wrong:

* the flag really stops the scan loop between two bus requests,
* the bus is free afterwards and the queued commands go out,
* a cancelled operation which finishes minutes later does not release the bus of the operation
  which started in the meantime (the generation counter).
"""
import asyncio
from unittest import TestCase, mock

from eltakobus.message import ESP2Message, RPSMessage

from tests.mocks import GatewayMock
from custom_components.eltako.observation import bus_members


def _telegram() -> ESP2Message:
    return RPSMessage(address=b'\xff\xaa\x80\x01', status=0x30, data=b'\x50', outgoing=True)


class TestCancelReleasesTheBus(TestCase):

    def setUp(self):
        self.gateway = GatewayMock()
        self.gateway.hass.create_task = mock.Mock()
        self.gateway.hass.add_job = mock.Mock()
        self.gateway._record_telegram = mock.Mock()
        self.gateway._bus.send = mock.Mock()

    def test_a_running_operation_is_cancelled_and_the_bus_is_free(self):
        self.gateway.try_acquire_bus("bus scan")

        result = self.gateway.cancel_bus_operation()

        self.assertTrue(result['was_busy'])
        self.assertEqual("bus scan", result['reason'])
        self.assertTrue(result['released'])
        self.assertFalse(self.gateway.is_bus_busy)
        # ... and the next operation can really take it
        self.assertTrue(self.gateway.try_acquire_bus("teaching in the senders"))

    def test_the_flag_is_set_so_the_loop_can_stop_itself(self):
        self.gateway.try_acquire_bus("bus scan")
        self.assertFalse(self.gateway.is_bus_cancelled)

        self.gateway.cancel_bus_operation()

        self.assertTrue(self.gateway.is_bus_cancelled)

    def test_the_next_operation_does_not_inherit_the_cancel(self):
        """Otherwise the scan somebody starts right after a cancel stops immediately."""
        self.gateway.try_acquire_bus("bus scan")
        self.gateway.cancel_bus_operation()

        self.gateway.try_acquire_bus("bus scan")
        self.assertFalse(self.gateway.is_bus_cancelled)

    def test_cancelling_while_nothing_runs_is_allowed(self):
        """A hanging operation and an idle bus look the same from the web ui - so the button
        must work in both cases instead of being disabled exactly when it is needed."""
        result = self.gateway.cancel_bus_operation()

        self.assertFalse(result['was_busy'])
        self.assertFalse(result['released'])
        self.assertFalse(self.gateway.is_bus_busy)
        self.assertTrue(self.gateway.try_acquire_bus("bus scan"))

    def test_the_waiting_commands_go_out_after_the_cancel(self):
        self.gateway.try_acquire_bus("bus scan")
        self.gateway._callback_send_message_to_serial_bus(_telegram())
        self.assertEqual(1, len(self.gateway._deferred_messages))

        result = self.gateway.cancel_bus_operation()

        self.assertEqual(1, result['messages_waiting'])
        self.assertEqual(1, self.gateway.hass.add_job.call_count)
        self.assertEqual(0, len(self.gateway._deferred_messages))


class TestTheGenerationCounter(TestCase):
    """A cancelled operation must not release the bus of the next one.

    The thread of a hanging scan runs its `finally` whenever its serial call finally returns -
    that can be minutes after the cancel, and by then somebody has started a new scan. Without
    the generation the late release would silently unlock a bus which is being used.
    """

    def setUp(self):
        self.gateway = GatewayMock()
        self.gateway.hass.add_job = mock.Mock()

    def test_a_late_release_of_a_cancelled_operation_is_ignored(self):
        self.gateway.try_acquire_bus("bus scan")
        cancelled_generation = self.gateway.bus_generation
        self.gateway.cancel_bus_operation()

        # the new operation takes the bus...
        self.assertTrue(self.gateway.try_acquire_bus("teaching in the senders"))
        # ... and now the old scan thread finally ends
        self.gateway.release_bus(cancelled_generation)

        self.assertTrue(self.gateway.is_bus_busy)
        self.assertEqual("teaching in the senders", self.gateway.bus_busy_reason)

    def test_the_own_release_still_works(self):
        self.gateway.try_acquire_bus("bus scan")
        self.gateway.release_bus(self.gateway.bus_generation)

        self.assertFalse(self.gateway.is_bus_busy)

    def test_every_acquisition_gets_its_own_number(self):
        self.gateway.try_acquire_bus("bus scan")
        first = self.gateway.bus_generation
        self.gateway.release_bus()
        self.gateway.try_acquire_bus("bus scan")

        self.assertNotEqual(first, self.gateway.bus_generation)


class TestOnePositionDoesNotEndTheScan(TestCase):
    """A position which does not answer costs that position - not the rest of the bus.

    Seen on a real FAM14: the serial reader logged `ParseError: No preamble found for ...`
    (a frame arrived without its preamble, the reader had lost sync on the stream) and the
    scan died with `eltakobus.error.TimeoutError` at that position. Everything behind it
    stayed unread.

    The trap is the name: `eltakobus.error.TimeoutError` inherits from `Exception`, not from
    the builtin `TimeoutError`, so `except TimeoutError` does not catch it - and the library
    raises it whenever the gateway answers with an EltakoTimeout telegram, which is the normal
    reply for a position where nobody is.
    """

    def setUp(self):
        self.gateway = GatewayMock()
        self.visited = []

    def _bus_which_fails_at(self, failing_position, error):
        gateway = self.gateway
        visited = self.visited

        async def exchange(request, expected=None, retries=0):
            position = getattr(request, 'address', None)
            visited.append(position)
            if position == failing_position:
                raise error
            return None         # nothing at this position - the loop moves on

        gateway._bus.exchange = exchange
        gateway._bus.callback_func = mock.Mock()
        gateway._bus.set_callback = mock.Mock()

    def _run(self, positions):
        with mock.patch('eltakobus.locking.lock_bus', mock.AsyncMock(return_value=None)), \
             mock.patch('eltakobus.locking.unlock_bus', mock.AsyncMock()):
            asyncio.run(bus_members._scan_bus(self.gateway, positions))

    def test_the_timeout_of_the_library_only_skips_that_position(self):
        from eltakobus.error import TimeoutError as BusTimeoutError

        # the class the library raises is *not* the builtin one - that is the whole point
        self.assertFalse(issubclass(BusTimeoutError, TimeoutError))

        self._bus_which_fails_at(3, BusTimeoutError())
        self.gateway.try_acquire_bus("bus scan")
        self._run([1, 2, 3, 4, 5])

        self.assertEqual([1, 2, 3, 4, 5], self.visited)

    def test_the_builtin_timeout_still_only_skips_that_position(self):
        self._bus_which_fails_at(2, TimeoutError())
        self.gateway.try_acquire_bus("bus scan")
        self._run([1, 2, 3])

        self.assertEqual([1, 2, 3], self.visited)

    def test_any_other_error_of_one_position_is_survived_too(self):
        """A damaged answer can surface as anything - a parse error, a wrong type. The scan
        says which position it lost and reads the rest."""
        self._bus_which_fails_at(2, ValueError("no preamble found"))
        self.gateway.try_acquire_bus("bus scan")
        self._run([1, 2, 3, 4])

        self.assertEqual([1, 2, 3, 4], self.visited)


class TestTheScanLoopStops(TestCase):
    """The paced scan of bus_members checks the flag between two bus requests."""

    def setUp(self):
        self.gateway = GatewayMock()
        self.exchanges = 0

    def _bus_with_counter(self):
        """A bus whose exchange() counts calls and cancels after the second one."""
        gateway = self.gateway

        async def exchange(request, expected=None, retries=0):
            self.exchanges += 1
            if self.exchanges >= 2:
                gateway.cancel_bus_operation()
            return None         # 'no answer at this position' - the loop moves on

        gateway._bus.exchange = exchange
        gateway._bus.callback_func = mock.Mock()
        gateway._bus.set_callback = mock.Mock()

    def test_the_scan_stops_instead_of_visiting_every_position(self):
        self._bus_with_counter()
        self.gateway.try_acquire_bus("bus scan")

        # the scan imports eltakobus.locking itself, so the module functions are patched
        with mock.patch('eltakobus.locking.lock_bus', mock.AsyncMock(return_value=None)), \
             mock.patch('eltakobus.locking.unlock_bus', mock.AsyncMock()):
            asyncio.run(bus_members._scan_bus(self.gateway, list(range(1, 40))))

        # without the cancel this would be 39 exchanges - one per position
        self.assertLess(self.exchanges, 5, msg=f"{self.exchanges} exchanges after a cancel")

    def test_the_progress_entry_is_removed_afterwards(self):
        """The entry of SCAN_PROGRESS is the 'a scan runs' signal of the whole ui."""
        self._bus_with_counter()
        self.gateway.try_acquire_bus("bus scan")

        with mock.patch('eltakobus.locking.lock_bus', mock.AsyncMock(return_value=None)), \
             mock.patch('eltakobus.locking.unlock_bus', mock.AsyncMock()):
            asyncio.run(bus_members._scan_bus(self.gateway, [1, 2, 3]))

        self.assertIsNone(bus_members.get_scan_progress(self.gateway.dev_id))
