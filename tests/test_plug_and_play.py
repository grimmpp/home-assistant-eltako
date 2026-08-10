"""Plug & play: which gateways and devices are detected and added automatically.

The active probing of the serial ports needs hardware and is therefore not tested here -
everything which *decides* what happens with a detection result is a pure function and is
covered completely.
"""
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase, mock

import voluptuous as vol

from tests.test_enocean_logger import HassDataMock

from custom_components.eltako.tools import plug_and_play
from custom_components.eltako.const import (CONF_BASE_ID, CONF_DEVICE_TYPE, CONF_EEP, CONF_GATEWAY,
                                            CONF_GATEWAY_ADDRESS, CONF_GATEWAY_DESCRIPTION,
                                            CONF_GATEWAY_PORT, CONF_PLUG_AND_PLAY,
                                            CONF_PLUG_AND_PLAY_INTERVAL, CONF_SENDER, CONF_SERIAL_PATH,
                                            CONF_UI_DEVICES, DATA_BUS_MEMBERS, DATA_ELTAKO,
                                            GatewayDeviceType, SETTING_GROUPS)

from homeassistant.const import CONF_DEVICES, CONF_ID, CONF_NAME


def member(**kwargs) -> dict:
    """One bus position as bus_members.get_members() delivers it."""
    entry = {
        'gateway_id': 1, 'bus_address': 1, 'device_class': None, 'model_candidates': None,
        'channel_count': 1, 'parent_bus_address': None, 'is_fam': False,
        'suggested_platform': None, 'suggested_eep': None, 'suggested_sender_eep': None,
        'taught_in': [],
    }
    entry.update(kwargs)
    return entry


def configured(*addresses, gateway_id: int = 1) -> dict:
    """Result of device_config.get_configured_addresses() for a few addresses."""
    upper = {str(address).upper() for address in addresses}
    return {'by_gateway': {gateway_id: set(upper)}, 'all': set(upper)}


NOTHING_CONFIGURED = {'by_gateway': {}, 'all': set()}

# a relay with four channels, identified beyond doubt
FSR14_4X = member(bus_address=2, device_class='FSR14_4x', channel_count=4,
                  suggested_platform='light', suggested_eep='M5-38-08',
                  suggested_sender_eep='A5-38-08')


class TestAddresses(TestCase):

    def test_local_address(self):
        self.assertEqual(plug_and_play.local_address(1), '00-00-00-01')
        self.assertEqual(plug_and_play.local_address(255), '00-00-00-FF')

    def test_sender_ids_follow_the_convention_of_the_device_manager(self):
        """00-00-B0-00 plus the bus position - the same as config_import uses."""
        self.assertEqual(plug_and_play.local_sender_id(1), '00-00-B0-01')
        self.assertEqual(plug_and_play.local_sender_id(0x10), '00-00-B0-10')
        self.assertEqual(plug_and_play.local_sender_id(255), '00-00-B0-FF')

    def test_addresses_are_valid_for_the_schema(self):
        """Everything which is generated has to pass the validation of the device config."""
        from custom_components.eltako.config import device_config

        device_config.validate_device('light', {
            CONF_ID: plug_and_play.local_address(4), CONF_EEP: 'M5-38-08',
            CONF_SENDER: {CONF_ID: plug_and_play.local_sender_id(4), CONF_EEP: 'A5-38-08'}})


class TestPortsToProbe(TestCase):

    SCAN = {'ports': [
        {'device': '/dev/ttyUSB0', 'free': True},
        {'device': '/dev/ttyUSB1', 'free': False},       # used by a running gateway
        {'device': '/dev/ttyUSB2', 'free': True},
    ]}

    def test_only_free_ports_are_probed(self):
        ports = plug_and_play.ports_to_probe(self.SCAN, set())

        self.assertEqual([port['device'] for port in ports], ['/dev/ttyUSB0', '/dev/ttyUSB2'])

    def test_configured_ports_are_never_opened(self):
        """A gateway which is configured but not set up must not be disturbed either."""
        ports = plug_and_play.ports_to_probe(self.SCAN, {'/dev/ttyUSB2'})

        self.assertEqual([port['device'] for port in ports], ['/dev/ttyUSB0'])

    def test_a_stick_of_another_integration_is_left_alone(self):
        """A known descriptor which fits no Eltako gateway belongs to somebody else."""
        scan = {'ports': [
            {'device': '/dev/ttyUSB0', 'free': True, 'manufacturer': 'Nabu Casa',
             'product': 'SkyConnect', 'suggested_device_types': []},
            {'device': '/dev/ttyUSB1', 'free': True, 'manufacturer': 'FTDI',
             'product': 'FT232R USB UART', 'suggested_device_types': ['fgw14usb', 'fam14']},
        ]}

        ports = plug_and_play.ports_to_probe(scan, set())

        self.assertEqual([port['device'] for port in ports], ['/dev/ttyUSB1'])

    def test_a_port_without_descriptor_is_probed(self):
        """Inside a container only the device nodes are passed through - no usb descriptor."""
        scan = {'ports': [{'device': '/dev/ttyUSB0', 'free': True,
                           'suggested_device_types': []}]}

        self.assertEqual(len(plug_and_play.ports_to_probe(scan, set())), 1)

    def test_empty_scan(self):
        self.assertEqual(plug_and_play.ports_to_probe({}, set()), [])


class TestCandidateDescription(TestCase):

    def test_fam14_is_created_automatically(self):
        candidate = plug_and_play.describe_candidate(
            '/dev/ttyUSB0', {'device_type': 'fam14', 'baud_rate': 57600})

        self.assertTrue(candidate['confident'])
        self.assertEqual(candidate['hw_type'], 'FAM14')
        self.assertEqual(candidate['description'], 'Bus Gateway')

    def test_fam_usb_and_esp3_are_created_automatically(self):
        for device_type in ['fam-usb', 'esp3-gateway', 'enocean-usb300']:
            candidate = plug_and_play.describe_candidate('/dev/ttyUSB0', {'device_type': device_type})
            self.assertTrue(candidate['confident'], msg=device_type)

    def test_fgw14usb_is_only_suggested(self):
        """The test for an FGW14-USB matches every port which does not echo - no proof."""
        candidate = plug_and_play.describe_candidate(
            '/dev/ttyUSB0', {'device_type': 'fgw14usb', 'baud_rate': 57600})

        self.assertFalse(candidate['confident'])
        self.assertIn('confirm', candidate['reason'])

    def test_a_usb300_is_not_called_mgw(self):
        """The probe only proves 'some ESP3 stick answered'; the usb descriptor names the
        model. Without refining it a USB300 is stored as 'esp3-gateway', which the catalog
        knows as the PioTek 'MGW (USB)' - a different manufacturer's product."""
        port = {'name': 'EnOcean GmbH EnOcean USB 300 DD FT5XDBOW',
                'suggested_device_types': ['enocean-usb300', 'esp3-gateway']}

        candidate = plug_and_play.describe_candidate(
            '/dev/ttyUSB3', {'device_type': 'esp3-gateway', 'baud_rate': 57600}, port)

        self.assertEqual('enocean-usb300', candidate['device_type'])
        self.assertEqual('USB300', candidate['hw_type'])
        self.assertTrue(candidate['confident'])

    def test_an_esp3_stick_without_a_known_model_stays_generic(self):
        """The honest answer for a stick this integration has no catalog entry for."""
        port = {'name': 'Silicon Labs CP2102', 'suggested_device_types': ['esp3-gateway']}

        candidate = plug_and_play.describe_candidate(
            '/dev/ttyUSB0', {'device_type': 'esp3-gateway', 'baud_rate': 57600}, port)

        self.assertEqual('esp3-gateway', candidate['device_type'])

    def test_a_probe_result_with_a_model_is_not_overruled(self):
        for device_type in ['fam14', 'fam-usb', 'enocean-usb300']:
            candidate = plug_and_play.describe_candidate(
                '/dev/ttyUSB0', {'device_type': device_type},
                {'suggested_device_types': ['enocean-usb300', 'esp3-gateway']})

            self.assertEqual(device_type, candidate['device_type'], msg=device_type)

    def test_a_port_without_any_descriptor_stays_generic(self):
        """Inside a container the device node is passed through, sysfs is not."""
        candidate = plug_and_play.describe_candidate(
            '/dev/ttyUSB0', {'device_type': 'esp3-gateway', 'baud_rate': 57600}, None)

        self.assertEqual('esp3-gateway', candidate['device_type'])


class TestMdnsDiscovery(TestCase):
    """LAN gateways which announce themselves via mDNS are found without any probing."""

    SMARTCONN = {'name': 'SmartConn-1a2b._bsc-sc-socket._tcp.local.',
                 'service_type': '_bsc-sc-socket._tcp.local.', 'address': '192.168.1.50',
                 'port': 5100, 'hostname': 'smartconn-1a2b.local'}
    EUL = {'name': 'EUL-Gateway._tcm515._tcp.local.', 'service_type': '_tcm515._tcp.local.',
           'address': '192.168.1.51', 'port': 5001, 'hostname': 'eul.local'}
    OWN_BRIDGE = {'name': 'Virtual-Network-Gateway-Adapter._bsc-sc-socket._tcp.local.',
                  'service_type': '_bsc-sc-socket._tcp.local.', 'address': '192.168.1.10',
                  'port': 12345, 'hostname': 'homeassistant.local'}
    FOREIGN = {'name': 'Some-Printer._bsc-sc-socket._tcp.local.',
               'service_type': '_bsc-sc-socket._tcp.local.', 'address': '192.168.1.99',
               'port': 9100, 'hostname': 'printer.local'}

    def test_the_service_name_names_the_gateway_type(self):
        self.assertEqual(plug_and_play.gateway_type_of_mdns_name(self.SMARTCONN['name']), 'lan')
        self.assertEqual(plug_and_play.gateway_type_of_mdns_name(self.EUL['name']), 'eul_lan')
        self.assertEqual(plug_and_play.gateway_type_of_mdns_name(self.OWN_BRIDGE['name']),
                         'lan-gw-esp2')
        self.assertIsNone(plug_and_play.gateway_type_of_mdns_name(self.FOREIGN['name']))
        self.assertIsNone(plug_and_play.gateway_type_of_mdns_name(None))

    def test_an_announced_gateway_is_created(self):
        """A service which states its own type and name is a positive identification."""
        candidate = plug_and_play.describe_mdns_candidate(self.SMARTCONN)

        self.assertTrue(candidate['confident'])
        self.assertEqual(candidate['connection'], 'lan')
        self.assertEqual(candidate['device_type'], 'lan')
        self.assertEqual(candidate['address'], '192.168.1.50')
        self.assertEqual(candidate['port'], 5100)
        self.assertIn('mDNS', candidate['reason'])

    def test_the_own_bridge_is_never_created_automatically(self):
        """virtual_network_gateway.py publishes it - Home Assistant would connect to itself."""
        candidate = plug_and_play.describe_mdns_candidate(self.OWN_BRIDGE)

        self.assertFalse(candidate['confident'])
        self.assertIn('loop', candidate['reason'])

    def test_a_foreign_service_is_ignored(self):
        self.assertIsNone(plug_and_play.describe_mdns_candidate(self.FOREIGN))

    def test_configured_gateways_are_skipped(self):
        candidates = plug_and_play.mdns_candidates(
            [self.SMARTCONN, self.EUL], {'192.168.1.50:5100'})

        self.assertEqual([c['address'] for c in candidates], ['192.168.1.51'])

    def test_a_gateway_configured_by_host_name_is_skipped_too(self):
        candidates = plug_and_play.mdns_candidates([self.SMARTCONN], {'smartconn-1a2b.local'})

        self.assertEqual(candidates, [])

    def test_the_same_endpoint_is_only_offered_once(self):
        candidates = plug_and_play.mdns_candidates(
            [self.SMARTCONN, dict(self.SMARTCONN, name='SmartConn-copy._bsc-sc-socket._tcp.local.')],
            set())

        self.assertEqual(len(candidates), 1)

    def test_configured_endpoints_come_from_the_configuration(self):
        hass = HassDataMock(config={CONF_GATEWAY: [
            {CONF_ID: 1, CONF_DEVICE_TYPE: 'mgw-lan', CONF_GATEWAY_ADDRESS: '192.168.1.50',
             CONF_GATEWAY_PORT: 5100},
            {CONF_ID: 2, CONF_DEVICE_TYPE: 'fam14', CONF_SERIAL_PATH: '/dev/ttyUSB0'},
        ]})

        endpoints = plug_and_play.configured_lan_endpoints(hass)

        self.assertIn('192.168.1.50', endpoints)
        self.assertIn('192.168.1.50:5100', endpoints)
        self.assertEqual(len(endpoints), 2)

    def test_no_services_at_all(self):
        self.assertEqual(plug_and_play.mdns_candidates([], set()), [])
        self.assertEqual(plug_and_play.mdns_candidates(None, set()), [])

    def test_the_browsed_service_types_match_the_device_manager(self):
        self.assertIn('_bsc-sc-socket._tcp.local.', plug_and_play.MDNS_SERVICE_TYPES)
        self.assertIn('_tcm515._tcp.local.', plug_and_play.MDNS_SERVICE_TYPES)

    def test_a_lan_candidate_becomes_a_valid_gateway_configuration(self):
        from custom_components.eltako.config import gateway_config

        candidate = plug_and_play.describe_mdns_candidate(self.SMARTCONN)
        validated = gateway_config.validate_gateway(plug_and_play.build_gateway(candidate, 7))

        self.assertEqual(validated[CONF_ID], 7)
        self.assertEqual(validated[CONF_GATEWAY_ADDRESS], '192.168.1.50')
        self.assertEqual(validated[CONF_GATEWAY_PORT], 5100)
        self.assertNotIn(CONF_SERIAL_PATH, validated)

    def test_a_serial_candidate_becomes_a_valid_gateway_configuration(self):
        from custom_components.eltako.config import gateway_config

        candidate = plug_and_play.describe_candidate('/dev/ttyUSB0', {'device_type': 'fam14'})
        validated = gateway_config.validate_gateway(plug_and_play.build_gateway(candidate, 3))

        self.assertEqual(validated[CONF_SERIAL_PATH], '/dev/ttyUSB0')
        self.assertEqual(validated[CONF_BASE_ID], '00-00-00-00')
        self.assertNotIn(CONF_GATEWAY_ADDRESS, validated)


class TestBusCandidates(TestCase):

    def test_identified_position_is_taken_over(self):
        result = plug_and_play.derive_bus_candidates(
            [member(bus_address=5, device_class='FUD14', suggested_platform='light',
                    suggested_eep='A5-38-08', suggested_sender_eep='A5-38-08')],
            NOTHING_CONFIGURED)

        self.assertEqual(result['skipped'], [])
        self.assertEqual(len(result['candidates']), 1)
        candidate = result['candidates'][0]
        self.assertEqual(candidate['platform'], 'light')
        self.assertEqual(candidate['source'], 'bus_position')
        self.assertEqual(candidate['device'][CONF_ID], '00-00-00-05')
        self.assertEqual(candidate['device'][CONF_EEP], 'A5-38-08')
        self.assertEqual(candidate['device'][CONF_SENDER][CONF_ID], '00-00-B0-05')

    def test_every_channel_becomes_its_own_device(self):
        result = plug_and_play.derive_bus_candidates([FSR14_4X], NOTHING_CONFIGURED)

        self.assertEqual([c['device'][CONF_ID] for c in result['candidates']],
                         ['00-00-00-02', '00-00-00-03', '00-00-00-04', '00-00-00-05'])
        self.assertEqual([c['device'][CONF_SENDER][CONF_ID] for c in result['candidates']],
                         ['00-00-B0-02', '00-00-B0-03', '00-00-B0-04', '00-00-B0-05'])
        self.assertEqual([c['device'][CONF_NAME] for c in result['candidates']],
                         ['FSR14_4x ch1', 'FSR14_4x ch2', 'FSR14_4x ch3', 'FSR14_4x ch4'])

    def test_single_channel_device_keeps_its_model_as_name(self):
        result = plug_and_play.derive_bus_candidates(
            [member(device_class='FUD14', suggested_platform='light', suggested_eep='A5-38-08',
                    suggested_sender_eep='A5-38-08')], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'][0]['device'][CONF_NAME], 'FUD14')

    def test_configured_channels_are_skipped(self):
        result = plug_and_play.derive_bus_candidates(
            [FSR14_4X], configured('00-00-00-02', '00-00-00-04'))

        self.assertEqual([c['device'][CONF_ID] for c in result['candidates']],
                         ['00-00-00-03', '00-00-00-05'])

    def test_addresses_of_another_gateway_do_not_hide_a_device(self):
        """Every bus has its own position 1 - the addresses are grouped per gateway."""
        result = plug_and_play.derive_bus_candidates(
            [member(gateway_id=2, device_class='FUD14', suggested_platform='light',
                    suggested_eep='A5-38-08', suggested_sender_eep='A5-38-08')],
            configured('00-00-00-01', gateway_id=1))

        self.assertEqual(len(result['candidates']), 1)

    def test_position_without_a_model_is_reported_not_added(self):
        result = plug_and_play.derive_bus_candidates([member(bus_address=7)], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['skipped'][0]['address'], '00-00-00-07')
        self.assertIn('unknown', result['skipped'][0]['reason'])

    def test_ambiguous_model_is_reported_not_added(self):
        """A model which several device classes share is not unique - the user decides."""
        result = plug_and_play.derive_bus_candidates(
            [member(device_class='FSR14_1x', model_candidates='FSR14_1x, FSR14_2x',
                    suggested_platform='light', suggested_eep='M5-38-08',
                    suggested_sender_eep='A5-38-08')], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertIn('several device classes', result['skipped'][0]['reason'])

    def test_model_without_a_template_is_reported(self):
        result = plug_and_play.derive_bus_candidates(
            [member(device_class='FSU14')], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertIn('no template', result['skipped'][0]['reason'])

    def test_actuator_without_a_sender_eep_is_not_added(self):
        result = plug_and_play.derive_bus_candidates(
            [member(device_class='FSB14', suggested_platform='cover', suggested_eep='G5-3F-7F')],
            NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertIn('sender EEP', result['skipped'][0]['reason'])

    def test_sensor_needs_no_sender(self):
        result = plug_and_play.derive_bus_candidates(
            [member(device_class='FWZ14_65A', suggested_platform='sensor', suggested_eep='A5-12-01')],
            NOTHING_CONFIGURED)

        self.assertNotIn(CONF_SENDER, result['candidates'][0]['device'])

    def test_gateway_modules_are_not_added_as_device(self):
        members = [member(bus_address=1, is_fam=True, device_class='FAM14'),
                   member(bus_address=2, device_class='FGW14_USB')]

        result = plug_and_play.derive_bus_candidates(members, NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['skipped'], [])

    def test_channel_positions_of_a_device_are_not_visited_twice(self):
        """The follow-up positions of a multi channel device carry parent_bus_address."""
        members = [FSR14_4X,
                   member(bus_address=3, parent_bus_address=2),
                   member(bus_address=4, parent_bus_address=2),
                   member(bus_address=5, parent_bus_address=2)]

        result = plug_and_play.derive_bus_candidates(members, NOTHING_CONFIGURED)

        self.assertEqual(len(result['candidates']), 4)
        self.assertEqual(result['skipped'], [])


class TestMemoryCandidates(TestCase):

    BUTTON = {'sensor_id': 'FF-AA-80-01', 'role': 'button', 'suggested_eep': 'F6-02-01',
              'suggested_platform': 'binary_sensor', 'suggested_name': 'Button',
              'key_function_name': 'PUSH_BUTTON', 'channel': 1}
    HA_SENDER = {'sensor_id': '00-00-B0-02', 'role': 'ha_sender', 'key_function_name': 'FROM_CONTROLLER'}
    UNKNOWN = {'sensor_id': 'FF-AA-80-09', 'role': 'unknown', 'key_function_name': 'SOMETHING'}

    def test_sensor_of_a_device_memory_is_taken_over(self):
        result = plug_and_play.derive_memory_candidates(
            [member(device_class='FSR14_4x', taught_in=[self.BUTTON])], NOTHING_CONFIGURED)

        self.assertEqual(len(result['candidates']), 1)
        candidate = result['candidates'][0]
        self.assertEqual(candidate['platform'], 'binary_sensor')
        self.assertEqual(candidate['source'], 'device_memory')
        self.assertEqual(candidate['device'][CONF_ID], 'FF-AA-80-01')
        self.assertEqual(candidate['device'][CONF_NAME], 'Button')

    def test_senders_of_home_assistant_are_no_devices(self):
        result = plug_and_play.derive_memory_candidates(
            [member(taught_in=[self.HA_SENDER])], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['skipped'], [])

    def test_sensor_without_an_eep_is_reported(self):
        result = plug_and_play.derive_memory_candidates(
            [member(taught_in=[self.UNKNOWN])], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertIn('does not name', result['skipped'][0]['reason'])

    def test_a_sensor_taught_into_several_devices_is_added_once(self):
        members = [member(bus_address=2, taught_in=[self.BUTTON]),
                   member(bus_address=3, taught_in=[dict(self.BUTTON, channel=2)])]

        result = plug_and_play.derive_memory_candidates(members, NOTHING_CONFIGURED)

        self.assertEqual(len(result['candidates']), 1)

    def test_configured_sensor_is_skipped(self):
        result = plug_and_play.derive_memory_candidates(
            [member(taught_in=[self.BUTTON])], configured('ff-aa-80-01'))

        self.assertEqual(result['candidates'], [])


class TestTelegramCandidates(TestCase):

    def unknown(self, address='FF-BB-01-02', confidence='confirmed', platform='sensor',
                eep='A5-04-02', gateway_ids=None) -> dict:
        return {'address': address, 'gateway_ids': gateway_ids if gateway_ids is not None else [1],
                'suggested': {'eep': eep, 'platform': platform, 'confidence': confidence,
                              'hw_type': 'FLGTF'}}

    def test_teach_in_telegram_is_unique_enough(self):
        result = plug_and_play.derive_telegram_candidates([self.unknown()], NOTHING_CONFIGURED)

        self.assertEqual(len(result['candidates']), 1)
        candidate = result['candidates'][0]
        self.assertEqual(candidate['gateway_id'], 1)
        self.assertEqual(candidate['platform'], 'sensor')
        self.assertEqual(candidate['source'], 'teach_in_telegram')
        self.assertEqual(candidate['device'][CONF_EEP], 'A5-04-02')
        self.assertEqual(candidate['device'][CONF_NAME], 'FLGTF')

    def test_a_guessed_eep_is_never_added(self):
        for confidence in ['likely', 'possible', None]:
            result = plug_and_play.derive_telegram_candidates(
                [self.unknown(confidence=confidence)], NOTHING_CONFIGURED)

            self.assertEqual(result['candidates'], [], msg=confidence)
            self.assertIn('guess', result['skipped'][0]['reason'])

    def test_actuators_are_not_added_automatically(self):
        """They need a sender address which has to be taught into the device."""
        result = plug_and_play.derive_telegram_candidates(
            [self.unknown(platform='light', eep='M5-38-08')], NOTHING_CONFIGURED)

        self.assertEqual(result['candidates'], [])
        self.assertIn('sender address', result['skipped'][0]['reason'])

    def test_configured_address_is_ignored(self):
        result = plug_and_play.derive_telegram_candidates(
            [self.unknown()], configured('FF-BB-01-02'))

        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['skipped'], [])

    def test_empty_statistics(self):
        self.assertEqual(plug_and_play.derive_telegram_candidates(None, NOTHING_CONFIGURED),
                         {'candidates': [], 'skipped': []})


class TestMerge(TestCase):

    def test_the_most_reliable_source_wins_per_address(self):
        """The bus position knows the model, the memory only the key function."""
        bus = plug_and_play.derive_bus_candidates(
            [member(device_class='FUD14', suggested_platform='light', suggested_eep='A5-38-08',
                    suggested_sender_eep='A5-38-08')], NOTHING_CONFIGURED)
        memory = {'candidates': [{'gateway_id': 1, 'platform': 'binary_sensor',
                                  'source': 'device_memory',
                                  'device': {CONF_ID: '00-00-00-01', CONF_EEP: 'F6-02-01'}}],
                  'skipped': []}

        merged = plug_and_play.merge_candidates(bus, memory)

        self.assertEqual(len(merged['candidates']), 1)
        self.assertEqual(merged['candidates'][0]['source'], 'bus_position')

    def test_the_same_address_on_two_buses_stays_two_devices(self):
        first = plug_and_play.derive_bus_candidates(
            [member(gateway_id=1, device_class='FUD14', suggested_platform='light',
                    suggested_eep='A5-38-08', suggested_sender_eep='A5-38-08')], NOTHING_CONFIGURED)
        second = plug_and_play.derive_bus_candidates(
            [member(gateway_id=2, device_class='FUD14', suggested_platform='light',
                    suggested_eep='A5-38-08', suggested_sender_eep='A5-38-08')], NOTHING_CONFIGURED)

        merged = plug_and_play.merge_candidates(first, second)

        self.assertEqual(len(merged['candidates']), 2)

    def test_skipped_entries_of_all_sources_are_collected(self):
        merged = plug_and_play.merge_candidates(
            {'candidates': [], 'skipped': [{'address': 'a'}]},
            {'candidates': [], 'skipped': [{'address': 'b'}]})

        self.assertEqual([entry['address'] for entry in merged['skipped']], ['a', 'b'])


class TestSettings(TestCase):

    ONCE_A_DAY = 24 * 60

    def test_disabled_by_default(self):
        from custom_components.eltako.config.config_helpers import DEFAULT_GENERAL_SETTINGS

        self.assertFalse(plug_and_play.is_enabled(DEFAULT_GENERAL_SETTINGS))

    def test_it_runs_once_a_day_by_default(self):
        """Probing the ports and reading a bus is not free, and a gateway is plugged in rarely."""
        from custom_components.eltako.config.config_helpers import DEFAULT_GENERAL_SETTINGS
        from custom_components.eltako.config.schema import GeneralSettings

        self.assertEqual(plug_and_play.get_interval(DEFAULT_GENERAL_SETTINGS), self.ONCE_A_DAY)
        # the yaml default must not drift apart from it
        self.assertEqual(GeneralSettings.ENTITY_SCHEMA({})[CONF_PLUG_AND_PLAY_INTERVAL],
                         self.ONCE_A_DAY)

    def test_the_setting_is_part_of_the_schema(self):
        from custom_components.eltako.config.schema import GeneralSettings

        validated = GeneralSettings.ENTITY_SCHEMA({CONF_PLUG_AND_PLAY: True,
                                                   CONF_PLUG_AND_PLAY_INTERVAL: 5})

        self.assertTrue(validated[CONF_PLUG_AND_PLAY])
        self.assertEqual(validated[CONF_PLUG_AND_PLAY_INTERVAL], 5)

    def test_a_weekly_interval_is_still_allowed(self):
        from custom_components.eltako.config.schema import GeneralSettings

        validated = GeneralSettings.ENTITY_SCHEMA({CONF_PLUG_AND_PLAY_INTERVAL: 7 * self.ONCE_A_DAY})

        self.assertEqual(validated[CONF_PLUG_AND_PLAY_INTERVAL], 10080)

    def test_the_web_ui_offers_the_setting(self):
        """The checkbox of the configuration and the button of the overview page are one switch."""
        from custom_components.eltako.config import general_settings

        names = [descriptor['name'] for descriptor in general_settings.SETTING_DESCRIPTORS]
        self.assertIn(CONF_PLUG_AND_PLAY, names)
        self.assertIn(CONF_PLUG_AND_PLAY_INTERVAL, names)

        groups = [group_id for group_id, _label, _help in SETTING_GROUPS]
        for descriptor in general_settings.SETTING_DESCRIPTORS:
            self.assertIn(descriptor['group'], groups)

    def test_the_setting_can_be_validated_like_any_other(self):
        from custom_components.eltako.config import general_settings

        self.assertTrue(general_settings.validate_setting(CONF_PLUG_AND_PLAY, True))
        with self.assertRaises(vol.Invalid):
            general_settings.validate_setting(CONF_PLUG_AND_PLAY_INTERVAL, 100000)

    def test_interval_is_robust_against_nonsense(self):
        self.assertEqual(plug_and_play.get_interval({CONF_PLUG_AND_PLAY_INTERVAL: None}), 0)
        self.assertEqual(plug_and_play.get_interval({CONF_PLUG_AND_PLAY_INTERVAL: 'x'}), 0)
        self.assertEqual(plug_and_play.get_interval({}), 0)


class TrackerMock:
    """Replacement for homeassistant.helpers.event.async_track_time_interval."""

    def __init__(self):
        self.intervals = []
        self.cancelled = 0

    def __call__(self, hass, action, interval, *args, **kwargs):
        self.intervals.append(interval)
        return self._cancel

    def _cancel(self):
        self.cancelled += 1


class TestPeriodicDetection(TestCase):

    def setUp(self):
        import homeassistant.helpers.event as event_helper

        self.tracker = TrackerMock()
        self.original = getattr(event_helper, 'async_track_time_interval', None)
        event_helper.async_track_time_interval = self.tracker
        self.hass = HassDataMock()

    def tearDown(self):
        import homeassistant.helpers.event as event_helper

        if self.original is not None:
            event_helper.async_track_time_interval = self.original

    def test_nothing_is_scheduled_while_it_is_off(self):
        result = plug_and_play.apply_settings(self.hass, {CONF_PLUG_AND_PLAY: False})

        self.assertFalse(result['periodic'])
        self.assertEqual(self.tracker.intervals, [])

    def test_interval_zero_means_manual_only(self):
        result = plug_and_play.apply_settings(
            self.hass, {CONF_PLUG_AND_PLAY: True, CONF_PLUG_AND_PLAY_INTERVAL: 0})

        self.assertTrue(result['enabled'])
        self.assertFalse(result['periodic'])
        self.assertEqual(self.tracker.intervals, [])

    def test_enabling_schedules_the_check(self):
        result = plug_and_play.apply_settings(
            self.hass, {CONF_PLUG_AND_PLAY: True, CONF_PLUG_AND_PLAY_INTERVAL: 7})

        self.assertTrue(result['periodic'])
        self.assertEqual(self.tracker.intervals[0].total_seconds(), 7 * 60)

    def test_applying_again_replaces_the_timer(self):
        plug_and_play.apply_settings(self.hass, {CONF_PLUG_AND_PLAY: True,
                                                CONF_PLUG_AND_PLAY_INTERVAL: 7})
        plug_and_play.apply_settings(self.hass, {CONF_PLUG_AND_PLAY: True,
                                                CONF_PLUG_AND_PLAY_INTERVAL: 3})

        self.assertEqual(self.tracker.cancelled, 1)
        self.assertEqual([interval.total_seconds() for interval in self.tracker.intervals],
                         [7 * 60, 3 * 60])

    def test_switching_it_off_cancels_the_timer(self):
        plug_and_play.apply_settings(self.hass, {CONF_PLUG_AND_PLAY: True,
                                                CONF_PLUG_AND_PLAY_INTERVAL: 7})
        plug_and_play.apply_settings(self.hass, {CONF_PLUG_AND_PLAY: False})

        self.assertEqual(self.tracker.cancelled, 1)
        self.assertIsNone(plug_and_play.get_state(self.hass)['unsubscribe'])


class TestDetectGateways(IsolatedAsyncioTestCase):
    """`async_detect_gateways` - the read-only stage 1, and that its two sources overlap."""

    class Hass:
        def __init__(self):
            self.data = {}

        async def async_add_executor_job(self, func, *args):
            return func(*args)

    async def test_serial_probe_and_mdns_browse_run_in_parallel(self):
        """The mDNS browse has a fixed window of several seconds - it must hide inside the
        time the serial probe takes anyway, not come on top of it. Each source waits for the
        other one to have started: sequential execution deadlocks and fails the timeout."""
        import asyncio
        from unittest import mock

        from custom_components.eltako.tools import gateway_scan

        probe_started, mdns_started = asyncio.Event(), asyncio.Event()

        async def probe(hass, ports):
            probe_started.set()
            await asyncio.wait_for(mdns_started.wait(), timeout=1)
            return {'/dev/ttyUSB0': {'device_type': 'fam14', 'baud_rate': 57600}}

        async def mdns(hass):
            mdns_started.set()
            await asyncio.wait_for(probe_started.wait(), timeout=1)
            return []

        with mock.patch.object(gateway_scan, 'scan',
                               return_value={'ports': [{'device': '/dev/ttyUSB0', 'free': True}]}), \
             mock.patch.object(plug_and_play, 'async_probe_ports', probe), \
             mock.patch.object(plug_and_play, 'async_discover_mdns_gateways', mdns):
            result = await plug_and_play.async_detect_gateways(self.Hass())

        self.assertEqual(result['ports_probed'], 1)
        self.assertEqual(result['mdns_found'], 0)
        self.assertEqual(len(result['gateways_detected']), 1)
        self.assertEqual(result['gateways_detected'][0]['device_type'], 'fam14')

    async def test_mdns_can_be_switched_off(self):
        """The CLI `detect --port` asks for exactly one stick - browsing the network then
        only costs time."""
        from unittest import mock

        from custom_components.eltako.tools import gateway_scan

        async def must_not_run(hass):
            raise AssertionError("mDNS was browsed although include_mdns is False")

        with mock.patch.object(gateway_scan, 'scan', return_value={'ports': []}), \
             mock.patch.object(plug_and_play, 'async_discover_mdns_gateways', must_not_run):
            result = await plug_and_play.async_detect_gateways(self.Hass(), include_mdns=False)

        self.assertEqual(result['gateways_detected'], [])
        self.assertEqual(result['mdns_found'], 0)


class TestState(IsolatedAsyncioTestCase):

    async def test_status_of_a_fresh_installation(self):
        hass = HassDataMock()

        status = plug_and_play.get_status(hass)

        self.assertFalse(status['enabled'])
        self.assertFalse(status['running'])
        self.assertIsNone(status['last_run'])
        self.assertIsNone(status['last_report'])
        self.assertEqual(status['setting'], CONF_PLUG_AND_PLAY)

    async def test_a_run_which_is_already_running_is_not_started_twice(self):
        """Reading a bus takes minutes - a second run must not interfere with it."""
        hass = HassDataMock()
        plug_and_play.get_state(hass)['running'] = True

        result = await plug_and_play.async_run(hass)

        self.assertEqual(result['skipped'], 'already_running')


class TestAutomaticBusScan(IsolatedAsyncioTestCase):
    """A bus gateway which Home Assistant sees for the first time reads its bus on its own.

    Without it the simple view shows an empty page next to a connected FAM14: a bus gateway
    only reveals its actuators and the senders taught into them once the device memories were
    read. The scan locks the bus for minutes, so it must happen exactly once - the checks that
    make sure of that are what is tested here, not the scan itself.
    """

    class GatewayStub:
        def __init__(self, dev_id=1, dev_type=None, is_simulated=False):
            self.dev_id = dev_id
            self.dev_type = dev_type or GatewayDeviceType.GatewayEltakoFAM14
            self.is_simulated = is_simulated

    def _hass(self, members: list = None) -> HassDataMock:
        """A hass with a bus member registry, as the integration sets it up."""
        from custom_components.eltako.observation.bus_members import BusMemberRegistry

        hass = HassDataMock()
        registry = BusMemberRegistry(hass)
        registry._store = None                          # nothing is persisted in the test
        for entry in members or []:
            position = registry._entry(entry['gateway_id'], entry['bus_address'])
            position['scanned_at'] = entry.get('scanned_at')
        hass.data.setdefault(DATA_ELTAKO, {})[DATA_BUS_MEMBERS] = registry
        return hass, registry

    def _patched_run(self):
        """Replaces async_run and records how it was called."""
        calls = []

        async def fake_run(hass, **kwargs):
            calls.append(kwargs)
            return {'buses_read': [{'gateway_id': 1, 'finished': True}]}

        return calls, mock.patch.object(plug_and_play, 'async_run', fake_run)

    def _connected(self, yes: bool = True):
        async def wait(hass, gateway_id):
            return yes
        return mock.patch.object(plug_and_play, '_async_wait_for_gateway', wait)

    async def test_a_new_bus_gateway_reads_its_bus(self):
        hass, registry = self._hass()
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub())

        # the ports are deliberately not probed: the gateway is already there and a probe
        # would create gateways nobody asked for
        self.assertEqual(calls, [{'detect_gateways': False}])
        self.assertTrue(registry.was_auto_scanned(1))

    async def test_the_scan_is_not_repeated_after_a_restart(self):
        """The attempt is remembered, so a bus which did not answer is not locked again."""
        hass, registry = self._hass()
        registry.mark_auto_scanned(1)
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub())

        self.assertEqual(calls, [])

    async def test_a_bus_which_was_already_read_is_left_alone(self):
        hass, registry = self._hass([{'gateway_id': 1, 'bus_address': 1,
                                      'scanned_at': '2026-01-01T00:00:00+00:00'}])
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub())

        self.assertEqual(calls, [])
        # and it is not looked at again on the next start either
        self.assertTrue(registry.was_auto_scanned(1))

    async def test_a_transceiver_has_no_bus(self):
        hass, registry = self._hass()
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(
                hass, self.GatewayStub(dev_type=GatewayDeviceType.EnOceanUSB300))

        self.assertEqual(calls, [])
        self.assertFalse(registry.was_auto_scanned(1))

    async def test_a_simulated_bus_has_no_memory_to_read(self):
        hass, _registry = self._hass()
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub(is_simulated=True))

        self.assertEqual(calls, [])

    async def test_a_running_detection_reads_the_bus_itself(self):
        hass, registry = self._hass()
        plug_and_play.get_state(hass)['running'] = True
        calls, patched = self._patched_run()

        with patched, self._connected():
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub())

        self.assertEqual(calls, [])
        # not marked: that run may be refused before it reaches the bus
        self.assertFalse(registry.was_auto_scanned(1))

    async def test_a_gateway_which_does_not_connect_is_tried_again_later(self):
        """Nothing was locked, so there is no reason to give up on it for good."""
        hass, registry = self._hass()
        calls, patched = self._patched_run()

        with patched, self._connected(False):
            await plug_and_play.async_auto_scan_bus(hass, self.GatewayStub())

        self.assertEqual(calls, [])
        self.assertFalse(registry.was_auto_scanned(1))


class TestConfiguredAddresses(IsolatedAsyncioTestCase):
    """The detection must never add a device or a sender id which already exists."""

    class Entry:
        def __init__(self, options=None):
            self.options = options or {}
            self.entry_id = 'entry'
            self.title = 'gw'
            self.data = {CONF_GATEWAY_DESCRIPTION: 'FAM14 - fam14 (Id: 1)'}

    class Hass(HassDataMock):
        def __init__(self, entries):
            super().__init__(config={CONF_GATEWAY: [{
                CONF_ID: 1, CONF_DEVICE_TYPE: 'fam14', CONF_NAME: 'FAM14',
                CONF_DEVICES: {'light': [{CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08',
                                          CONF_SENDER: {CONF_ID: '00-00-B0-01',
                                                        CONF_EEP: 'A5-38-08'}}]}}]})
            self._entries = entries
            self.config_entries = self

        def async_entries(self, domain):
            return self._entries

        def async_update_entry(self, entry, options=None, **kwargs):
            entry.options = options

    async def test_yaml_devices_senders_and_ui_devices_are_all_known(self):
        from custom_components.eltako.config import device_config

        entry = self.Entry({CONF_UI_DEVICES: {'sensor': [
            {CONF_ID: 'FF-AA-80-05', CONF_EEP: 'A5-04-02'}]}})
        hass = self.Hass([entry])

        addresses = device_config.get_configured_addresses(hass)

        self.assertIn('00-00-00-01', addresses['all'])       # from configuration.yaml
        self.assertIn('00-00-B0-01', addresses['all'])       # its sender id
        self.assertIn('FF-AA-80-05', addresses['all'])       # created in the web ui
        self.assertIn('00-00-00-01', addresses['by_gateway'][1])

    async def test_a_detected_device_does_not_shadow_a_configured_one(self):
        from custom_components.eltako.config import device_config

        hass = self.Hass([self.Entry()])
        addresses = device_config.get_configured_addresses(hass)

        result = plug_and_play.derive_bus_candidates(
            [member(bus_address=1, device_class='FUD14', suggested_platform='light',
                    suggested_eep='A5-38-08', suggested_sender_eep='A5-38-08')], addresses)

        self.assertEqual(result['candidates'], [])


if __name__ == '__main__':
    unittest.main()
