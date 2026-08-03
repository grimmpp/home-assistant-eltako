"""Bus positions are detected passively from the traffic of the gateway."""
import asyncio
import unittest
from unittest import TestCase

from tests.mocks import *
from tests.test_enocean_logger import HassDataMock, get_general_settings

from custom_components.eltako import bus_members
from custom_components.eltako.bus_members import BusMemberRegistry, describe_model
from custom_components.eltako.const import *
from custom_components.eltako.enocean_logger import EnOceanTelegramLogger

from eltakobus.message import EltakoDiscoveryReply, EltakoPoll, EltakoWrapped4BS
from eltakobus.util import AddressExpression

from homeassistant.const import CONF_DEVICES, CONF_ID, CONF_NAME


def discovery_reply(bus_address: int, model=b'\x04\x01\x72\x00', size=4, memory=0x72, is_fam=False):
    return EltakoDiscoveryReply(reported_address=bus_address, reported_size=size,
                                memory_size=memory, model=model, is_fam=is_fam)


class TestModelDescription(TestCase):

    def test_size_disambiguates_the_model(self):
        """04-01 is used by FSR14_1x and FSR14_4x - the size decides."""
        self.assertEqual(describe_model(b'\x04\x01\x72\x00', 4)[0], 'FSR14_4x')
        self.assertEqual(describe_model(b'\x04\x01\x72\x00', 1)[0], 'FSR14_1x')

    def test_unique_models(self):
        self.assertEqual(describe_model(b'\x07\xff\x00\x00', 1)[0], 'FAM14')
        self.assertEqual(describe_model(b'\x04\x06\x00\x00', 2)[0], 'FSB14')

    def test_unknown_model(self):
        self.assertEqual(describe_model(b'\xAB\xCD', 2), (None, None))
        self.assertEqual(describe_model(None, 1), (None, None))

    def test_candidates_are_reported(self):
        _, candidates = describe_model(b'\x04\x01\x72\x00', 4)
        self.assertIn('FSR14_1x', candidates)


class TestRegistry(TestCase):

    def setUp(self):
        self.registry = BusMemberRegistry()
        self.gateway = GatewayMock(dev_id=1)

    def test_polling_reveals_a_position(self):
        self.registry.note_polled(self.gateway, 5)
        self.registry.note_polled(self.gateway, 5)

        members = self.registry.get_members()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]['bus_address'], 5)
        self.assertEqual(members[0]['polled_count'], 2)
        self.assertEqual(members[0]['answer_count'], 0)
        self.assertEqual(members[0]['local_address'], '00-00-00-05')

    def test_answer_marks_the_position_as_alive(self):
        self.registry.note_polled(self.gateway, 8)
        self.registry.note_answer(self.gateway, 8, 'FF-A2-24-08')

        member = self.registry.get_members()[0]
        self.assertEqual(member['answer_count'], 1)
        self.assertEqual(member['external_address'], 'FF-A2-24-08')
        self.assertIsNotNone(member['last_seen'])

    def test_discovery_reply_identifies_the_device(self):
        self.registry.note_discovery_reply(self.gateway, discovery_reply(1))

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 1)
        self.assertEqual(member['device_class'], 'FSR14_4x')
        self.assertEqual(member['model'], '04-01-72-00')
        self.assertEqual(member['size'], 4)
        self.assertEqual(member['memory_size'], 0x72)

    def test_fam14_is_marked(self):
        self.registry.note_discovery_reply(self.gateway, discovery_reply(255, model=b'\x07\xff\x00\x00',
                                                                        size=1, is_fam=True))

        member = self.registry.get_members()[0]
        self.assertEqual(member['device_class'], 'FAM14')
        self.assertTrue(member['is_fam'])

    def test_members_are_sorted_and_separated_per_gateway(self):
        self.registry.note_polled(GatewayMock(dev_id=1), 3)
        self.registry.note_polled(GatewayMock(dev_id=0), 9)
        self.registry.note_polled(GatewayMock(dev_id=1), 1)

        members = self.registry.get_members()
        self.assertEqual([(m['gateway_id'], m['bus_address']) for m in members], [(0, 9), (1, 1), (1, 3)])

    def test_discovery_reply_without_address_is_ignored(self):
        class Broken:
            reported_address = None
        self.registry.note_discovery_reply(self.gateway, Broken())

        self.assertEqual(self.registry.get_members(), [])

    def test_clear(self):
        self.registry.note_polled(self.gateway, 1)
        self.registry.clear()
        self.assertEqual(self.registry.get_members(), [])


class TestConfiguredDeviceMapping(TestCase):

    def test_configured_devices_are_matched_to_their_position(self):
        hass = HassDataMock(config={CONF_GATEWAY: [{
            CONF_ID: 1,
            CONF_DEVICES: {'light': [{CONF_ID: '00-00-00-08', CONF_EEP: 'M5-38-08', CONF_NAME: 'FSR14 - 8'}],
                           'binary_sensor': [{CONF_ID: 'FF-BB-0A-1B', CONF_EEP: 'F6-02-01'}]},
        }]})
        registry = BusMemberRegistry()
        registry.note_polled(GatewayMock(dev_id=1), 8)
        registry.note_polled(GatewayMock(dev_id=1), 9)

        members = {m['bus_address']: m for m in registry.get_members(hass)}

        self.assertTrue(members[8]['configured'])
        self.assertEqual(members[8]['configured_name'], 'FSR14 - 8')
        self.assertEqual(members[8]['configured_platform'], 'light')
        self.assertFalse(members[9]['configured'])


class TestLoggerFeedsTheRegistry(TestCase):
    """Polling must not be dropped before the bus information is collected."""

    def setUp(self):
        self.gateway = GatewayMock(dev_id=1, base_id=AddressExpression.parse('FF-A2-24-00'))
        self.hass = HassDataMock()
        self.gateway.hass = self.hass
        self.registry = bus_members.setup_registry(self.hass)
        self.logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True}))
        self.logger.refresh_device_map()

    def test_filtered_polling_still_reveals_the_position(self):
        self.assertFalse(self.logger.include_polling)

        self.logger.record_message(self.gateway, EltakoPoll(4), TelegramDirection.INCOMING.value)

        # not recorded ...
        self.assertEqual(self.logger.get_recent_telegrams(), [])
        # ... but the bus position is known
        members = self.registry.get_members()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]['bus_address'], 4)
        self.assertEqual(members[0]['polled_count'], 1)

    def test_discovery_reply_is_collected(self):
        self.logger.record_message(self.gateway, discovery_reply(6), TelegramDirection.INCOMING.value)

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 6)
        self.assertEqual(member['device_class'], 'FSR14_4x')

    def test_status_answer_of_a_bus_device_is_collected(self):
        self.logger.record_message(self.gateway, EltakoWrapped4BS(address=b'\x00\x00\x00\x0A', status=0x00,
                                                                 data=b'\x01\x02\x03\x04'),
                                   TelegramDirection.INCOMING.value)

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 0x0A)
        self.assertEqual(member['answer_count'], 1)
        self.assertEqual(member['external_address'], 'FF-A2-24-0A')

    def test_wireless_telegrams_do_not_create_bus_members(self):
        from eltakobus.message import RPSMessage

        self.logger.record_message(self.gateway, RPSMessage(address=b'\x81\x04\xE5\x54', status=0x30,
                                                            data=b'\x10'), TelegramDirection.INCOMING.value)

        self.assertEqual(self.registry.get_members(), [])


if __name__ == '__main__':
    unittest.main()


class TestEoManMapping(TestCase):
    """The eo_man mapping table enriches identified bus devices."""

    def test_known_hw_types(self):
        from custom_components.eltako.bus_members import describe_hw_type

        fsr = describe_hw_type('FSR14_4x')
        self.assertEqual(fsr['description'], 'Relay (4 channels)')
        self.assertEqual(fsr['eep'], 'M5-38-08')
        self.assertEqual(fsr['pct14_function_group'], 2)
        self.assertEqual(fsr['pct14_key_function'], 51)

        fsb = describe_hw_type('FSB14')
        self.assertEqual(fsb['platform'], 'cover')
        self.assertEqual(fsb['sender_eep'], 'H5-3F-7F')

    def test_unknown_hw_type(self):
        from custom_components.eltako.bus_members import describe_hw_type

        self.assertEqual(describe_hw_type('DOES_NOT_EXIST'), {})
        self.assertEqual(describe_hw_type(None), {})

    def test_every_discoverable_bus_device_has_an_entry(self):
        """Every device class the library can detect should be described - otherwise the
        table shows a bare class name without explanation."""
        from custom_components.eltako.bus_members import HW_TYPE_INFO, MODEL_MAP

        known = set(HW_TYPE_INFO)
        discoverable = {name for names in MODEL_MAP['by_model'].values() for name in names}

        missing = sorted(discoverable - known)
        self.assertEqual(missing, [], msg=f"hw types without description: {missing}")

    def test_members_carry_the_mapping_info(self):
        registry = BusMemberRegistry()
        registry.note_discovery_reply(GatewayMock(dev_id=1), discovery_reply(4))

        member = registry.get_members()[0]

        self.assertEqual(member['description'], 'Relay (4 channels)')
        self.assertEqual(member['suggested_eep'], 'M5-38-08')
        self.assertEqual(member['pct14_function_group'], 2)
        self.assertIn('ha_device_id', member)       # None without a registry, but present

    def test_two_buses_are_kept_apart(self):
        """Installations with more than one FAM14: same position on two buses."""
        registry = BusMemberRegistry()
        registry.note_discovery_reply(GatewayMock(dev_id=1), discovery_reply(4))
        registry.note_discovery_reply(GatewayMock(dev_id=2), discovery_reply(4, model=b'\x04\x06\x00\x00',
                                                                            size=2))

        members = registry.get_members()

        self.assertEqual(len(members), 2)
        by_gateway = {m['gateway_id']: m for m in members}
        self.assertEqual(by_gateway[1]['device_class'], 'FSR14_4x')
        self.assertEqual(by_gateway[2]['device_class'], 'FSB14')


class TestChannelHierarchy(TestCase):
    """Follow-up positions of a multi-channel device belong to the physical device."""

    def test_channels_are_attributed_to_their_parent(self):
        registry = BusMemberRegistry()
        gateway = GatewayMock(dev_id=1)
        registry.note_discovery_reply(gateway, discovery_reply(1))        # FSR14_4x, size 4
        for position in (2, 3, 4, 5):
            registry.note_polled(gateway, position)
        registry.note_discovery_reply(gateway, discovery_reply(5, model=b'\x04\x05\x00\x00', size=1))

        members = {m['bus_address']: m for m in registry.get_members()}

        self.assertEqual(members[1]['channel_count'], 4)
        self.assertIsNone(members[1]['parent_bus_address'])
        for position in (2, 3, 4):
            self.assertEqual(members[position]['parent_bus_address'], 1, msg=position)
        self.assertIsNone(members[5]['parent_bus_address'])       # own device (FUD14)

    def test_position_outside_the_range_is_standalone(self):
        registry = BusMemberRegistry()
        gateway = GatewayMock(dev_id=1)
        registry.note_discovery_reply(gateway, discovery_reply(1, size=2))
        registry.note_polled(gateway, 9)

        members = {m['bus_address']: m for m in registry.get_members()}

        self.assertIsNone(members[9]['parent_bus_address'])

    def test_parents_do_not_leak_across_gateways(self):
        registry = BusMemberRegistry()
        registry.note_discovery_reply(GatewayMock(dev_id=1), discovery_reply(1))    # size 4
        registry.note_polled(GatewayMock(dev_id=2), 2)

        members = {(m['gateway_id'], m['bus_address']): m for m in registry.get_members()}

        self.assertIsNone(members[(2, 2)]['parent_bus_address'])


class MemoryResponseMock:
    def __init__(self, row, value):
        self.row = row
        self.value = value


class TestMemoryImage(TestCase):
    """The memory image of a scan must survive the periodic re-enumeration of the FAM14."""

    def setUp(self):
        self.registry = BusMemberRegistry()
        self.gateway = GatewayMock(dev_id=5)

    def _scan_position_one(self, memory=127):
        self.registry.note_discovery_reply(self.gateway, discovery_reply(1, memory=memory))
        for line in range(memory):
            value = bytes.fromhex('fedbb640') + bytes((5, 3, 1, 0)) if line == 12 else bytes(8)
            self.registry.note_memory_response(self.gateway, MemoryResponseMock(line, value))

    def test_taught_in_sensors_are_extracted(self):
        self._scan_position_one()
        asyncio.run(self.registry.async_parse_taught_in())

        member = self.registry.get_members()[0]
        self.assertEqual(len(member['taught_in']), 1)
        self.assertEqual(member['taught_in'][0]['sensor_id'], 'FE-DB-B6-40')
        self.assertEqual(member['taught_in'][0]['channel'], 1)

    def test_re_enumeration_keeps_the_memory_image(self):
        """The FAM14 re-enumerates the bus all the time - that must not wipe the scan result."""
        self._scan_position_one()
        self.registry.note_discovery_reply(self.gateway, discovery_reply(1, memory=127))    # routine enumeration

        asyncio.run(self.registry.async_parse_taught_in())

        member = self.registry.get_members()[0]
        self.assertEqual(member['memory_rows_read'], 127)
        self.assertEqual(len(member['taught_in']), 1)

    def test_changed_device_resets_the_memory_image(self):
        self._scan_position_one()
        self.registry.note_discovery_reply(self.gateway, discovery_reply(1, model=b'\x04\x06\x00\x00',
                                                                         size=2, memory=8))

        member = self.registry.get_members()[0]
        self.assertEqual(member['memory_rows_read'], 0)
        self.assertNotIn('taught_in', member)


class TestTaughtInClassification(TestCase):
    """The kind of a taught-in sensor and its EEP are derived from the key function (eo_man rules)."""

    classify = staticmethod(BusMemberRegistry.classify_taught_in_sensor)

    def test_eep_is_read_from_the_key_function_name(self):
        result = self.classify('FF-E2-81-81', 'TEMPERATURE_CONTROLLER_ACCORDING_EEP_A5_10_06_FTR55D')
        self.assertEqual(result['role'], 'sensor')
        self.assertEqual(result['suggested_eep'], 'A5-10-06')
        self.assertEqual(result['suggested_platform'], 'sensor')
        self.assertEqual(result['suggested_name'], 'Temperature Controller')

    def test_wireless_push_button(self):
        result = self.classify('FE-DB-B6-40', 'DIRECTION_PUSH_BUTTON_TOP_ON')
        self.assertEqual(result['role'], 'button')
        self.assertEqual(result['suggested_eep'], 'F6-02-01')
        self.assertEqual(result['suggested_platform'], 'binary_sensor')

    def test_fts14em_input(self):
        result = self.classify('00-00-10-0A', 'UNIVERSAL_PUSH_BUTTON')
        self.assertEqual(result['role'], 'fts14em')
        self.assertEqual(result['suggested_eep'], 'F6-02-01')

    def test_ha_senders_are_recognized(self):
        self.assertEqual(self.classify('00-00-B0-05', 'DIMMING_VALUE_FROM_CONTROLLER')['role'], 'ha_sender')
        self.assertEqual(self.classify('FF-BC-C8-01', 'SWITCHING_STATE_FROM_CONTROLLER')['role'], 'ha_sender')
        self.assertEqual(self.classify('00-00-B1-01', 'UNIVERSAL_PUSH_BUTTON')['role'], 'ha_sender')

    def test_weather_station(self):
        result = self.classify('FF-AA-BB-CC', 'WEATHER_STATION')
        self.assertEqual(result['suggested_eep'], 'A5-04-02')

    def test_unknown(self):
        self.assertEqual(self.classify('FF-AA-BB-CC', 'NO_FUNCTION')['role'], 'unknown')

    def test_parsed_memory_carries_the_classification(self):
        registry = BusMemberRegistry()
        gateway = GatewayMock(dev_id=5)
        registry.note_discovery_reply(gateway, discovery_reply(1, memory=127))
        for line in range(127):
            value = bytes.fromhex('fedbb640') + bytes((5, 3, 1, 0)) if line == 12 else bytes(8)
            registry.note_memory_response(gateway, MemoryResponseMock(line, value))
        asyncio.run(registry.async_parse_taught_in())

        sensor = registry.get_members()[0]['taught_in'][0]
        self.assertEqual(sensor['role'], 'button')
        self.assertEqual(sensor['suggested_eep'], 'F6-02-01')
