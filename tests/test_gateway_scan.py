"""Scan for serial ports which could host a gateway."""
import os
import tempfile
import unittest
from unittest import TestCase

from custom_components.eltako.tools import gateway_scan


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


class PortInfoMock:
    def __init__(self, device, manufacturer=None, product=None, description=None,
                 serial_number=None, interface=None):
        self.device = device
        self.manufacturer = manufacturer
        self.product = product
        self.description = description
        self.serial_number = serial_number
        self.interface = interface


class TestPyserialFallback(TestCase):
    """macOS (/dev/cu.*) and windows (COMx) have no /dev/ttyUSB* and no sysfs - there the
    ports come from pyserial. Relevant for the standalone runtime on a developer machine."""

    def scan_with(self, ports):
        original = gateway_scan._pyserial_ports
        gateway_scan._pyserial_ports = lambda: ports
        try:
            return gateway_scan.scan_serial_ports()
        finally:
            gateway_scan._pyserial_ports = original

    def test_macos_port_is_found_and_gets_a_suggestion(self):
        ports = self.scan_with([{
            'device': '/dev/cu.usbserial-AQ028YCS',
            'manufacturer': 'FTDI', 'product': 'FT232R USB UART',
            'serial_number': 'AQ028YCS', 'interface_name': None,
        }])

        port = next(p for p in ports if p['device'] == '/dev/cu.usbserial-AQ028YCS')
        self.assertEqual(port['manufacturer'], 'FTDI')
        self.assertIn('FTDI', port['name'])
        # the FT232R descriptor suggests the Eltako gateways - also without sysfs
        self.assertTrue(port['suggested_device_types'], msg=port)

    def test_windows_com_port(self):
        ports = self.scan_with([{
            'device': 'COM3', 'manufacturer': 'Silicon Labs', 'product': 'CP2102 USB to UART',
            'serial_number': None, 'interface_name': None,
        }])

        port = next(p for p in ports if p['device'] == 'COM3')
        self.assertIn('esp3', " ".join(port['suggested_device_types']).lower())

    def test_pyserial_enumeration_returns_port_objects(self):
        """_pyserial_ports maps the pyserial objects into plain dicts."""
        from serial.tools import list_ports

        original = list_ports.comports
        list_ports.comports = lambda: [PortInfoMock('COM7', manufacturer='FTDI',
                                                    description='FT232R USB UART')]
        try:
            ports = gateway_scan._pyserial_ports()
        finally:
            list_ports.comports = original

        self.assertEqual(ports, [{'device': 'COM7', 'manufacturer': 'FTDI',
                                  'product': 'FT232R USB UART', 'serial_number': None,
                                  'interface_name': None}])

    def test_pyserial_placeholder_is_not_a_descriptor(self):
        """'n/a' is what pyserial writes when it knows nothing - it must not become a
        descriptor. A port which *has* a descriptor but suggests no gateway is skipped by the
        probe, so taking the placeholder at face value excludes exactly the ports which the
        container exception of `ports_to_probe` is meant to cover: inside a container sysfs
        carries no usb information, yet pyserial still lists every /dev/ttyUSB* with 'n/a'."""
        from serial.tools import list_ports

        original = list_ports.comports
        list_ports.comports = lambda: [PortInfoMock('/dev/ttyUSB0', description='n/a')]
        try:
            ports = gateway_scan._pyserial_ports()
        finally:
            list_ports.comports = original

        self.assertEqual(ports, [{'device': '/dev/ttyUSB0', 'manufacturer': None,
                                  'product': None, 'serial_number': None,
                                  'interface_name': None}])

    def test_port_without_usb_information_keeps_its_device_name(self):
        """Without a descriptor the name stays the device name, not the 'n/a' placeholder."""
        ports = self.scan_with([{'device': '/dev/ttyUSB0', 'manufacturer': None,
                                 'product': None, 'serial_number': None, 'interface_name': None}])

        port = next(p for p in ports if p['device'] == '/dev/ttyUSB0')
        self.assertEqual(port['name'], 'ttyUSB0')
        self.assertIsNone(port.get('product'))


class TestDeviceTypeSuggestion(TestCase):

    def test_ftdi_suggests_the_eltako_gateways(self):
        types, hint = gateway_scan._describe_descriptor("FTDI FT232R USB UART AQ028YCS")

        self.assertIn('fgw14usb', types)
        self.assertIn('fam14', types)
        self.assertTrue(hint)

    def test_enocean_programmer_suggests_fam_usb_first(self):
        """This is the descriptor of a real Eltako FAM-USB ('EnOcean Programmer V3.2', two
        ports). ESP3 sticks use it too, so both are suggested - but the FAM-USB first: it is
        the Eltako device and needs 9600 baud instead of 57600."""
        types, hint = gateway_scan._describe_descriptor("EnOcean GmbH EnOcean_Programmer V3.2")

        self.assertEqual(types[0], 'fam-usb')
        self.assertIn('enocean-usb300', types)
        self.assertIn('TWO ports', hint)
        self.assertIn('9600', hint)

    def test_usb300_with_spaces_in_its_product_name(self):
        """The descriptor of a real USB300 as it appears on a raspberry pi. It writes its
        product with spaces ('EnOcean USB 300 DD'), so the fragment 'USB300' does not match -
        the port used to be skipped as 'no known gateway' before the probe ever saw it."""
        types, hint = gateway_scan._describe_descriptor(
            "usb-EnOcean_GmbH_EnOcean_USB_300_DD_FT5XDBOW-if00-port0 "
            "EnOcean USB 300 DD EnOcean GmbH")

        self.assertEqual(types[0], 'enocean-usb300')
        self.assertIn('esp3-gateway', types)
        self.assertTrue(hint)

    def test_an_unknown_enocean_product_is_suggested_as_esp3(self):
        """EnOcean only builds ESP3 sticks, so their manufacturer alone is enough to send the
        port to the probe - which then asks for the base id and settles the type."""
        types, _ = gateway_scan._describe_descriptor("EnOcean GmbH EnOcean USB 400J DA")

        self.assertEqual(types[0], 'esp3-gateway')

    def test_the_manufacturer_beats_the_ftdi_chip(self):
        """An EnOcean stick which also reports its ftdi chip is an ESP3 stick, not an Eltako
        gateway - otherwise the probe would start with the wrong baud rate."""
        types, _ = gateway_scan._describe_descriptor("EnOcean GmbH FT232R USB UART FT5XDBOW")

        self.assertEqual(types[0], 'esp3-gateway')

    def test_a_foreign_stick_is_still_unknown(self):
        """The suggestion decides whether a port is opened at all - a zigbee stick belongs to
        another integration and must not be probed."""
        types, _ = gateway_scan._describe_descriptor("ITead Sonoff Zigbee 3.0 USB Dongle Plus")

        self.assertEqual([], types)

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

    def test_the_chip_id_decides_before_the_usb_serial_number(self):
        """The usb serial number belongs to the adapter, the chip id to the EnOcean hardware."""
        ports = [{'device': '/dev/ttyUSB4', 'free': True, 'serial_number': 'ANOTHER-ADAPTER',
                  'chip_id': '01-93-8B-2C', 'suggested_device_types': ['esp3-gateway'],
                  'name': 'EnOcean USB 500'}]

        path, reason = gateway_scan.choose_port(
            ports, '/dev/ttyUSB0', {'chip_id': '01-93-8B-2C', 'usb_serial': 'GONE'}, 'esp3-gateway')

        self.assertEqual(path, '/dev/ttyUSB4')
        self.assertIn('01-93-8B-2C', reason)

    def test_the_interface_tells_the_two_ports_of_one_stick_apart(self):
        """if00 and if01 of a two port stick report the same usb serial number - only one of
        them carries the telegrams."""
        ports = [{'device': '/dev/ttyUSB2', 'free': True, 'serial_number': 'FT7YTP3Y',
                  'interface': 'if00', 'suggested_device_types': ['fam-usb'], 'name': 'if00'},
                 {'device': '/dev/ttyUSB3', 'free': True, 'serial_number': 'FT7YTP3Y',
                  'interface': 'if01', 'suggested_device_types': ['fam-usb'], 'name': 'if01'}]

        path, _ = gateway_scan.choose_port(
            ports, '/dev/ttyUSB0', {'usb_serial': 'FT7YTP3Y', 'interface': 'if01'}, 'fam-usb')

        self.assertEqual(path, '/dev/ttyUSB3')

    def test_two_sticks_with_the_same_id_are_not_guessed(self):
        ports = [{'device': '/dev/ttyUSB2', 'free': True, 'chip_id': '01-93-8B-2C',
                  'suggested_device_types': ['esp3-gateway'], 'name': 'one'},
                 {'device': '/dev/ttyUSB3', 'free': True, 'chip_id': '01-93-8B-2C',
                  'suggested_device_types': ['esp3-gateway'], 'name': 'clone'}]

        path, reason = gateway_scan.choose_port(ports, '/dev/ttyUSB0',
                                                {'chip_id': '01-93-8B-2C'}, 'esp3-gateway')

        self.assertEqual(path, '/dev/ttyUSB0')
        self.assertIsNone(reason)


class TestSwappedSticks(TestCase):
    """Two sticks which are plugged in the other way round keep their gateways.

    The configured port exists in this case - it just carries the wrong stick, which is why
    the port alone cannot be trusted and the identity has to decide.
    """

    def setUp(self):
        import tempfile

        self.first = tempfile.NamedTemporaryFile()      # 'was ttyUSB0'
        self.second = tempfile.NamedTemporaryFile()     # 'was ttyUSB1'
        self.addCleanup(self.first.close)
        self.addCleanup(self.second.close)

        self.ports = [
            {'device': self.first.name, 'free': True, 'serial_number': 'STICK-B',
             'chip_id': '11-22-33-44', 'suggested_device_types': ['esp3-gateway'], 'name': 'B'},
            {'device': self.second.name, 'free': True, 'serial_number': 'STICK-A',
             'chip_id': 'AA-BB-CC-DD', 'suggested_device_types': ['esp3-gateway'], 'name': 'A'},
        ]

    def test_the_gateway_follows_its_own_chip_id(self):
        path, reason = gateway_scan.choose_port(self.ports, self.first.name,
                                                {'chip_id': 'AA-BB-CC-DD'}, 'esp3-gateway')

        self.assertEqual(path, self.second.name)
        self.assertIn('AA-BB-CC-DD', reason)
        self.assertIn('does not have to be changed', reason)

    def test_the_usb_serial_number_does_the_same(self):
        path, reason = gateway_scan.choose_port(self.ports, self.first.name,
                                                {'usb_serial': 'STICK-A'}, 'esp3-gateway')

        self.assertEqual(path, self.second.name)
        self.assertIn('STICK-A', reason)

    def test_a_stick_which_is_nowhere_leaves_the_port_alone_but_says_so(self):
        """Taking a random other port would be worse than staying - but this explains a
        gateway which receives nothing."""
        path, reason = gateway_scan.choose_port(self.ports, self.first.name,
                                                {'chip_id': 'DE-AD-BE-EF'}, 'esp3-gateway')

        self.assertEqual(path, self.first.name)
        self.assertIn('another stick', reason)

    def test_a_port_whose_stick_is_ours_is_never_touched(self):
        path, reason = gateway_scan.choose_port(self.ports, self.first.name,
                                                {'chip_id': '11-22-33-44'}, 'esp3-gateway')

        self.assertEqual(path, self.first.name)
        self.assertIsNone(reason)

    def test_a_partner_which_already_runs_on_the_port_is_not_stolen(self):
        """Order of setup: if the other gateway got there first, its port stays its own."""
        self.ports[1]['free'] = False

        path, reason = gateway_scan.choose_port(self.ports, self.first.name,
                                                {'chip_id': 'AA-BB-CC-DD'}, 'esp3-gateway')

        self.assertEqual(path, self.first.name)
        self.assertIn('was not found', reason)

    def test_without_a_known_identity_nothing_is_moved(self):
        """The first start of an installation which never read an id: the port is the truth."""
        path, reason = gateway_scan.choose_port(self.ports, self.first.name, None, 'esp3-gateway')

        self.assertEqual(path, self.first.name)
        self.assertIsNone(reason)


class TestRememberedIdentity(TestCase):
    """What is stored for a gateway, and what happens when the hardware is replaced."""

    def test_the_first_version_of_the_store_held_a_plain_usb_serial(self):
        self.assertEqual(gateway_scan._normalize_identity('AQ028YCS'), {'usb_serial': 'AQ028YCS'})

    def test_an_id_which_the_port_did_not_report_is_kept(self):
        """The chip id is only read when it is needed - forgetting it would defeat its purpose."""
        identity = {'chip_id': 'AA-BB-CC-DD', 'usb_serial': 'STICK-A'}
        port = {'device': '/dev/ttyUSB1', 'serial_number': 'STICK-A'}

        merged = gateway_scan._merge_identity(identity, port, '/dev/ttyUSB1')

        self.assertEqual(merged['chip_id'], 'AA-BB-CC-DD')
        self.assertEqual(merged['device'], '/dev/ttyUSB1')

    def test_a_replaced_stick_does_not_inherit_the_ids_of_the_old_one(self):
        identity = {'chip_id': 'AA-BB-CC-DD', 'usb_serial': 'STICK-A'}
        port = {'device': '/dev/ttyUSB1', 'serial_number': 'BRAND-NEW'}

        merged = gateway_scan._merge_identity(identity, port, '/dev/ttyUSB1')

        self.assertNotIn('chip_id', merged)
        self.assertEqual(merged['usb_serial'], 'BRAND-NEW')

    def test_a_new_adapter_in_front_of_the_same_chip_keeps_the_gateway(self):
        """The chip id proves that it is the same EnOcean hardware, whatever the adapter says."""
        identity = {'chip_id': 'AA-BB-CC-DD', 'usb_serial': 'STICK-A'}
        port = {'device': '/dev/ttyUSB1', 'serial_number': 'OTHER', 'chip_id': 'AA-BB-CC-DD'}

        merged = gateway_scan._merge_identity(identity, port, '/dev/ttyUSB1')

        self.assertEqual(merged['chip_id'], 'AA-BB-CC-DD')
        self.assertEqual(merged['usb_serial'], 'OTHER')

    def test_the_ids_of_a_stick_are_keyed_by_its_usb_serial_and_interface(self):
        sticks = {}
        gateway_scan._remember_sticks(sticks, [
            {'device': '/dev/ttyUSB0', 'serial_number': 'FT7YTP3Y', 'interface': 'if01',
             'chip_id': '01-93-8B-2C', 'base_id': 'FF-9B-8C-00'},
            {'device': '/dev/ttyUSB9', 'chip_id': 'NO-KEY-FOR-THIS'},     # no usb serial number
        ])

        self.assertEqual(sticks, {'FT7YTP3Y/if01': {'chip_id': '01-93-8B-2C',
                                                    'base_id': 'FF-9B-8C-00',
                                                    'device': '/dev/ttyUSB0'}})

    def test_the_scan_shows_what_was_read_from_a_stick_before(self):
        """The passive scan cannot ask - it may only show remembered ids, marked as such."""
        port = {'device': '/dev/ttyUSB0', 'serial_number': 'FT7YTP3Y', 'interface': 'if01',
                'chip_id': None, 'base_id': None, 'ids_remembered': False}

        gateway_scan._apply_known_ids(port, None, {'FT7YTP3Y/if01': {'chip_id': '01-93-8B-2C'}}, {})

        self.assertEqual(port['chip_id'], '01-93-8B-2C')
        self.assertTrue(port['ids_remembered'])

    def test_the_base_id_of_a_running_gateway_is_current_and_not_remembered(self):
        port = {'device': '/dev/ttyUSB0', 'serial_number': 'FT7YTP3Y',
                'chip_id': None, 'base_id': None, 'ids_remembered': False}

        gateway_scan._apply_known_ids(port, {'id': 1, 'base_id': 'FF-9B-8C-00'}, {},
                                      {'1': {'chip_id': '01-93-8B-2C'}})

        self.assertEqual(port['base_id'], 'FF-9B-8C-00')
        # the port of a running gateway is not opened again, so its chip id can only be stored
        self.assertEqual(port['chip_id'], '01-93-8B-2C')
        self.assertTrue(port['ids_remembered'])
