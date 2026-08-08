"""Only one operation at a time may talk on the RS485 bus of a gateway.

A bus scan, a teach-in and the base id request of a FAM14 lock the bus and switch the receive
callback off. A switch command which goes onto the wire in between disturbs the answers of the
devices - the scan then reports devices as missing which are there. These tests pin that such a
command waits instead, and that a second operation on the same gateway is refused.
"""
import asyncio
from unittest import TestCase, mock

from eltakobus.message import ESP2Message, RPSMessage

from tests.mocks import GatewayMock
from custom_components.eltako.core import gateway as gateway_module
from custom_components.eltako.core.gateway import BusBusyError, BUS_DEFER_SECONDS


def _telegram() -> ESP2Message:
    return RPSMessage(address=b'\xff\xaa\x80\x01', status=0x30, data=b'\x50', outgoing=True)


class TestExclusiveBusAccess(TestCase):

    def setUp(self):
        self.gateway = GatewayMock()
        self.gateway.hass.create_task = mock.Mock()
        self.gateway.hass.add_job = mock.Mock()
        self.gateway._record_telegram = mock.Mock()
        self.gateway._bus.send = mock.Mock()

    def test_bus_is_free_at_the_beginning(self):
        self.assertFalse(self.gateway.is_bus_busy)
        self.assertIsNone(self.gateway.bus_busy_reason)

    def test_second_operation_is_refused(self):
        self.assertTrue(self.gateway.try_acquire_bus("bus scan"))
        self.assertTrue(self.gateway.is_bus_busy)
        self.assertEqual(self.gateway.bus_busy_reason, "bus scan")

        # a second operation does not wait but is told that it cannot run
        self.assertFalse(self.gateway.try_acquire_bus("teaching in the senders"))
        self.assertEqual(self.gateway.bus_busy_reason, "bus scan")

        self.gateway.release_bus()
        self.assertFalse(self.gateway.is_bus_busy)
        self.assertTrue(self.gateway.try_acquire_bus("teaching in the senders"))

    def test_the_old_flag_still_shows_the_state(self):
        # the web ui and the detection have always looked at this event
        self.gateway.try_acquire_bus("bus scan")
        self.assertTrue(self.gateway._reading_memory_of_devices_is_running.is_set())
        self.gateway.release_bus()
        self.assertFalse(self.gateway._reading_memory_of_devices_is_running.is_set())

    def test_release_without_acquire_does_nothing(self):
        self.gateway.release_bus()
        self.assertFalse(self.gateway.is_bus_busy)

    def test_context_manager_releases_after_an_error(self):
        with self.assertRaises(RuntimeError):
            with self.gateway.exclusive_bus_access("bus scan"):
                raise RuntimeError("the scan failed")
        self.assertFalse(self.gateway.is_bus_busy)

    def test_context_manager_refuses_a_parallel_operation(self):
        with self.gateway.exclusive_bus_access("bus scan"):
            with self.assertRaises(BusBusyError):
                with self.gateway.exclusive_bus_access("teaching in the senders"):
                    pass
            # the refused operation must not have taken the bus away from the running one
            self.assertEqual(self.gateway.bus_busy_reason, "bus scan")

    def test_command_waits_while_the_bus_is_busy(self):
        message = _telegram()
        with mock.patch.object(gateway_module, 'dispatcher_send') as dispatcher:
            self.gateway.try_acquire_bus("bus scan")
            self.gateway._callback_send_message_to_serial_bus(message)

            # nothing went onto the bus and nobody was told that it was sent
            self.gateway.hass.create_task.assert_not_called()
            dispatcher.assert_not_called()
            self.assertEqual(len(self.gateway._deferred_messages), 1)

            # ... and after the scan it is sent
            self.gateway.release_bus()
            self.gateway.hass.add_job.assert_called_once()
            callback, sent = self.gateway.hass.add_job.call_args[0]
            self.assertEqual(callback, self.gateway._callback_send_message_to_serial_bus)
            self.assertEqual(sent, message)
            self.assertEqual(len(self.gateway._deferred_messages), 0)

    def test_the_command_is_really_sent_afterwards(self):
        with mock.patch.object(gateway_module, 'dispatcher_send'):
            self.gateway.try_acquire_bus("bus scan")
            self.gateway._callback_send_message_to_serial_bus(_telegram())
            self.gateway.release_bus()
            # the deferred queue hands the message back to the same callback - now it sends
            callback, message = self.gateway.hass.add_job.call_args[0]
            callback(message)
            self.gateway.hass.create_task.assert_called_once()

    def test_an_old_command_is_dropped_instead_of_sent_late(self):
        with mock.patch.object(gateway_module, 'dispatcher_send'):
            self.gateway.try_acquire_bus("bus scan")
            self.gateway._callback_send_message_to_serial_bus(_telegram())

            # a scan takes minutes - a switch command which arrives that late is worse than none
            queued_at, message = self.gateway._deferred_messages[0]
            self.gateway._deferred_messages[0] = (queued_at - BUS_DEFER_SECONDS - 1, message)

            self.gateway.release_bus()
            self.gateway.hass.add_job.assert_not_called()

    def test_the_queue_does_not_grow_without_end(self):
        with mock.patch.object(gateway_module, 'dispatcher_send'):
            self.gateway.try_acquire_bus("bus scan")
            for _ in range(gateway_module.BUS_DEFERRED_LIMIT + 20):
                self.gateway._callback_send_message_to_serial_bus(_telegram())
            self.assertEqual(len(self.gateway._deferred_messages),
                             gateway_module.BUS_DEFERRED_LIMIT)

    def test_command_is_sent_normally_while_the_bus_is_free(self):
        with mock.patch.object(gateway_module, 'dispatcher_send'):
            self.gateway._callback_send_message_to_serial_bus(_telegram())
            self.gateway.hass.create_task.assert_called_once()
            self.assertEqual(len(self.gateway._deferred_messages), 0)


class TestRepeaterModeDuringExclusiveAccess(TestCase):

    def setUp(self):
        self.gateway = GatewayMock()
        self.gateway.hass.create_task = mock.Mock()
        self.gateway._bus.send_repeater_mode_request = mock.Mock()
        self.gateway._bus.send_repeater_mode = mock.Mock()

    def test_the_request_is_skipped(self):
        self.gateway.try_acquire_bus("bus scan")
        self.gateway.request_repeater_mode()
        self.gateway.hass.create_task.assert_not_called()

        self.gateway.release_bus()
        self.gateway.request_repeater_mode()
        self.gateway.hass.create_task.assert_called_once()

    def test_setting_the_mode_is_refused(self):
        self.gateway.try_acquire_bus("bus scan")
        with self.assertRaises(BusBusyError):
            self.gateway.set_repeater_mode(1)
        self.gateway.hass.create_task.assert_not_called()


class TestOperationsRespectABusyBus(TestCase):

    def setUp(self):
        self.gateway = GatewayMock()
        self.gateway.hass.create_task = mock.Mock()

    def test_a_second_bus_scan_is_not_started(self):
        from custom_components.eltako.observation import bus_members

        self.gateway.try_acquire_bus("bus scan")
        with mock.patch('threading.Thread') as thread:
            started = bus_members.start_bus_scan_thread(self.gateway.hass, self.gateway,
                                                        list(range(1, 5)))
        self.assertFalse(started)
        thread.assert_not_called()

    def test_a_scan_starts_and_takes_the_bus_when_it_is_free(self):
        from custom_components.eltako.observation import bus_members

        with mock.patch('threading.Thread') as thread:
            started = bus_members.start_bus_scan_thread(self.gateway.hass, self.gateway,
                                                        list(range(1, 5)))
        self.assertTrue(started)
        thread.return_value.start.assert_called_once()
        # the bus belongs to the scan from now on - the thread gives it back when it is done
        self.assertTrue(self.gateway.is_bus_busy)
        self.assertEqual(self.gateway.bus_busy_reason, "bus scan")

    def test_a_device_test_is_refused(self):
        from custom_components.eltako.tools import device_tests

        with mock.patch.object(device_tests, '_find_gateway', return_value=self.gateway):
            self.gateway.try_acquire_bus("bus scan")
            with self.assertRaises(ValueError) as error:
                device_tests._check_bus_is_free(self.gateway.hass, {'gateway': 123})
            self.assertIn("bus scan", str(error.exception))

            # without an exclusive operation the test may run
            self.gateway.release_bus()
            device_tests._check_bus_is_free(self.gateway.hass, {'gateway': 123})

    def test_the_read_memory_button_says_why_it_does_nothing(self):
        from homeassistant.exceptions import HomeAssistantError
        from custom_components.eltako.button import GatewayReadAllDevicesButton

        button = mock.Mock(spec=GatewayReadAllDevicesButton)
        button.gateway = self.gateway
        self.gateway.try_acquire_bus("bus scan")
        with self.assertRaises(HomeAssistantError):
            asyncio.run(GatewayReadAllDevicesButton.async_press(button))

    def test_reading_the_device_memories_is_skipped(self):
        self.gateway.try_acquire_bus("bus scan")
        with mock.patch.object(gateway_module, 'request_memory_of_all_devices') as request:
            asyncio.run(self.gateway.read_memory_of_all_bus_members())
        request.assert_not_called()
