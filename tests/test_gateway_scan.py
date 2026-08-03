"""Scan for serial ports which could host a gateway."""
import os
import tempfile
import unittest
from unittest import TestCase

from custom_components.eltako import gateway_scan


class TestSysfsReading(TestCase):
    """The usb descriptor is read through symlinks - '..' must be resolved by the kernel."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        # /sys/devices/usb1/1-1 (usb device) -> holds product/manufacturer/serial
        self.usb_device = os.path.join(self.root, 'devices', 'usb1', '1-1')
        self.interface = os.path.join(self.usb_device, '1-1:1.0')
        os.makedirs(self.interface)
        for name, value in [('product', 'FT232R USB UART'), ('manufacturer', 'FTDI'), ('serial', 'AQ028YCS')]:
            with open(os.path.join(self.usb_device, name), 'w') as handle:
                handle.write(value + "\n")
        with open(os.path.join(self.interface, 'interface'), 'w') as handle:
            handle.write("FT232R USB UART\n")

        # like on a raspberry: .../<usb device>/<interface>/<tty name> is the target of the
        # 'device' symlink, so the descriptor is two levels above it
        self.port_dir = os.path.join(self.interface, 'ttyUSB0')
        os.makedirs(self.port_dir)

        self.sysfs_base = os.path.join(self.root, 'class', 'tty')
        tty_dir = os.path.join(self.sysfs_base, 'ttyUSB0')
        os.makedirs(tty_dir)
        os.symlink(self.port_dir, os.path.join(tty_dir, 'device'))

    def read(self) -> dict:
        return gateway_scan._read_sysfs_info('/dev/ttyUSB0', sysfs_tty_dir=self.sysfs_base)

    def test_no_descriptor_outside_of_sysfs(self):
        self.assertEqual(gateway_scan._read_sysfs_info('/dev/does-not-exist',
                                                       sysfs_tty_dir=self.sysfs_base), {})

    def test_descriptor_is_read_through_the_symlink(self):
        info = self.read()

        self.assertEqual(info['product'], 'FT232R USB UART')
        self.assertEqual(info['manufacturer'], 'FTDI')
        self.assertEqual(info['serial_number'], 'AQ028YCS')

    def test_normpath_would_break_the_lookup(self):
        """Regression: normpath resolves '..' textually and leaves the symlink target."""
        base = os.path.join(self.sysfs_base, 'ttyUSB0', 'device')

        self.assertTrue(os.path.exists(os.path.join(base, '../../product')))
        self.assertFalse(os.path.exists(os.path.normpath(os.path.join(base, '../../product'))))


class TestDeviceTypeSuggestion(TestCase):

    def test_ftdi_suggests_the_eltako_gateways(self):
        types, hint = gateway_scan._describe_descriptor("FTDI FT232R USB UART AQ028YCS")

        self.assertIn('fgw14usb', types)
        self.assertIn('fam14', types)
        self.assertTrue(hint)

    def test_enocean_programmer_suggests_esp3(self):
        types, hint = gateway_scan._describe_descriptor("EnOcean GmbH EnOcean_Programmer V3.2")

        self.assertEqual(types[0], 'enocean-usb300')
        self.assertIn('two ports', hint)

    def test_unknown_device(self):
        self.assertEqual(gateway_scan._describe_descriptor("Some random adapter"), ([], ""))


if __name__ == '__main__':
    unittest.main()


class TestPortRelocation(TestCase):
    """A gateway follows its stick when the kernel renumbers the serial ports."""

    PORTS = [
        {'device': '/dev/ttyUSB1', 'free': False, 'serial_number': 'FT7YTP3Y',
         'suggested_device_types': ['enocean-usb300', 'fam-usb'], 'name': 'EnOcean Programmer'},
        {'device': '/dev/ttyUSB4', 'free': True, 'serial_number': 'AQ028YCS',
         'suggested_device_types': ['fgw14usb', 'fam14', 'fam-usb'], 'name': 'FTDI FT232R'},
    ]

    def test_existing_path_is_kept(self):
        import tempfile
        existing = tempfile.NamedTemporaryFile()

        path, reason = gateway_scan.choose_port(self.PORTS, existing.name, 'AQ028YCS', 'fam14')

        self.assertEqual(path, existing.name)
        self.assertIsNone(reason)

    def test_missing_path_is_relocated_by_usb_serial(self):
        path, reason = gateway_scan.choose_port(self.PORTS, '/dev/ttyUSB0', 'AQ028YCS', 'fam14')

        self.assertEqual(path, '/dev/ttyUSB4')
        self.assertIn('AQ028YCS', reason)

    def test_without_fingerprint_the_unique_type_match_wins(self):
        path, reason = gateway_scan.choose_port(self.PORTS, '/dev/ttyUSB0', None, 'fam14')

        self.assertEqual(path, '/dev/ttyUSB4')
        self.assertIn('fam14', reason)

    def test_ambiguous_candidates_are_not_guessed(self):
        ports = self.PORTS + [{'device': '/dev/ttyUSB5', 'free': True, 'serial_number': 'OTHER',
                               'suggested_device_types': ['fam14'], 'name': 'second FTDI'}]

        path, reason = gateway_scan.choose_port(ports, '/dev/ttyUSB0', None, 'fam14')

        self.assertEqual(path, '/dev/ttyUSB0')      # unchanged: two candidates, no guess
        self.assertIsNone(reason)

    def test_used_ports_are_never_taken(self):
        ports = [{'device': '/dev/ttyUSB1', 'free': False, 'serial_number': 'AQ028YCS',
                  'suggested_device_types': ['fam14'], 'name': 'taken'}]

        path, reason = gateway_scan.choose_port(ports, '/dev/ttyUSB0', 'AQ028YCS', 'fam14')

        self.assertEqual(path, '/dev/ttyUSB0')
        self.assertIsNone(reason)
