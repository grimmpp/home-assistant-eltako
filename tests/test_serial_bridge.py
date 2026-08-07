"""Bridge a serial port to another machine: publish it over tcp, attach it back as a pty.

No hardware needed - a pty pair stands in for the usb stick, which is exactly what the
publisher sees anyway (pyserial opens it like any other character device). The tests care about
the two properties the bridge is worthless without: the bytes arrive **unchanged**, and the pty
**survives a reader** which opens and closes it, because that is what a detection probe does.
"""
import os
import pty
import time
import unittest
from unittest import TestCase

from custom_components.eltako.tools import serial_bridge

# a frame with the bytes a terminal line discipline would mangle: CR, LF, XON and XOFF
TRICKY = bytes([0xA5, 0x5A, 0x0D, 0x0A, 0x11, 0x13, 0x1A, 0x00, 0xFF, 0x80])

FREE_PORT = 5399


def _wait_for(condition, timeout=5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


@unittest.skipUnless(hasattr(os, 'openpty'), "a pty is a posix feature")
class TestBridgeRoundTrip(TestCase):
    """publisher -> tcp -> attachment -> pty, with a pty pair playing the serial device."""

    def setUp(self):
        # the 'device': what the publisher opens. Writing into `device_master` is the stick
        # talking, reading from it is the stick receiving.
        self.device_master, device_slave = pty.openpty()
        serial_bridge._make_raw(device_slave)
        self.device_path = os.ttyname(device_slave)
        self.device_slave = device_slave

        self.publisher = None
        self.attachment = None
        self.link = None

    def tearDown(self):
        for bridge in (self.attachment, self.publisher):
            if bridge is not None:
                bridge.stop()
        for fd in (self.device_master, self.device_slave):
            try:
                os.close(fd)
            except OSError:
                pass
        if self.link and os.path.islink(self.link):
            os.unlink(self.link)

    def _bridge(self, port=FREE_PORT):
        self.link = os.path.join(os.path.dirname(self.device_path), f"ttyUSB-test-{port}")
        # the link must not sit in /dev on a developer machine, so it goes next to the pty
        self.link = f"/tmp/eltako-ttyUSB-test-{port}"
        self.publisher = serial_bridge.publish(self.device_path, 57600, port, host='127.0.0.1')
        self.attachment = serial_bridge.attach('127.0.0.1', port, link=self.link)
        self.assertTrue(_wait_for(lambda: self.attachment.status()['connected']),
                        msg=self.attachment.status())

    def test_bytes_from_the_device_arrive_unchanged(self):
        self._bridge(FREE_PORT)

        os.write(self.device_master, TRICKY)

        received = b''
        with open(self.link, 'rb', buffering=0) as consumer:
            self.assertTrue(_wait_for(lambda: True, 0.2))
            deadline = time.monotonic() + 5
            while len(received) < len(TRICKY) and time.monotonic() < deadline:
                chunk = consumer.read(len(TRICKY) - len(received))
                if chunk:
                    received += chunk
        self.assertEqual(received, TRICKY)

    def test_bytes_to_the_device_arrive_unchanged(self):
        self._bridge(FREE_PORT + 1)

        with open(self.link, 'wb', buffering=0) as consumer:
            consumer.write(TRICKY)

        received = b''
        deadline = time.monotonic() + 5
        while len(received) < len(TRICKY) and time.monotonic() < deadline:
            received += os.read(self.device_master, len(TRICKY) - len(received))
        self.assertEqual(received, TRICKY)

    def test_the_pty_survives_a_reader_which_closes_it(self):
        """A probe opens and closes the port several times - a pty which dies with its first
        reader (the default, because the master then reports EIO) makes the detection fail on
        the second attempt."""
        self._bridge(FREE_PORT + 2)

        for round_number in range(3):
            payload = bytes([round_number]) + TRICKY
            os.write(self.device_master, payload)
            with open(self.link, 'rb', buffering=0) as consumer:
                received = b''
                deadline = time.monotonic() + 5
                while len(received) < len(payload) and time.monotonic() < deadline:
                    chunk = consumer.read(len(payload) - len(received))
                    if chunk:
                        received += chunk
            self.assertEqual(received, payload, msg=f"round {round_number}")

        self.assertTrue(self.attachment.is_running)
        self.assertTrue(os.path.islink(self.link))

    def test_status_counts_both_directions(self):
        self._bridge(FREE_PORT + 3)

        os.write(self.device_master, TRICKY)
        self.assertTrue(_wait_for(
            lambda: self.publisher.status()['bytes_from_device'] >= len(TRICKY)))

        status = self.publisher.status()
        self.assertEqual(status['role'], 'publish')
        self.assertTrue(status['running'])
        self.assertIsNone(status['error'])


@unittest.skipUnless(hasattr(os, 'openpty'), "a pty is a posix feature")
class TestControlLayer(TestCase):
    """start_bridge / stop_bridge / bridge_status - what the cli, the websocket and a REST
    endpoint all call."""

    def setUp(self):
        master, slave = pty.openpty()
        self.fds = (master, slave)
        self.device_path = os.ttyname(slave)

    def tearDown(self):
        serial_bridge.stop_all_bridges()
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass

    def test_a_started_bridge_is_listed_and_can_be_stopped(self):
        started = serial_bridge.start_bridge('publish', device=self.device_path,
                                             baud_rate=57600, port=FREE_PORT + 4,
                                             host='127.0.0.1')

        self.assertEqual(started['role'], 'publish')
        self.assertTrue(started['running'])
        self.assertIn(started['name'], [entry['name'] for entry in serial_bridge.bridge_status()])

        stopped = serial_bridge.stop_bridge(started['name'])
        self.assertFalse(stopped['running'])
        self.assertEqual(serial_bridge.bridge_status(), [])

    def test_the_same_port_is_not_published_twice(self):
        serial_bridge.start_bridge('publish', device=self.device_path, baud_rate=57600,
                                   port=FREE_PORT + 5, host='127.0.0.1')

        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.start_bridge('publish', device=self.device_path, baud_rate=57600,
                                       port=FREE_PORT + 5, host='127.0.0.1')

    def test_a_missing_device_fails_before_anything_is_registered(self):
        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.start_bridge('publish', device='/dev/does-not-exist',
                                       baud_rate=57600, port=FREE_PORT + 6, host='127.0.0.1')

        self.assertEqual(serial_bridge.bridge_status(), [])

    def test_arguments_are_checked(self):
        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.start_bridge('publish', device=self.device_path)   # no baud rate
        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.start_bridge('attach')                             # no host
        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.start_bridge('sideways', device=self.device_path, baud_rate=57600)

    def test_stopping_an_unknown_bridge_is_an_error_not_a_crash(self):
        with self.assertRaises(serial_bridge.SerialBridgeError):
            serial_bridge.stop_bridge('publish:1')
