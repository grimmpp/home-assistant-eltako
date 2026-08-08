"""Bus positions are detected passively from the traffic of the gateway."""
import asyncio
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

from tests.mocks import GatewayMock
from tests.test_device_activity import StoreMock, iso_days_ago
from tests.test_enocean_logger import HassDataMock, get_general_settings

from custom_components.eltako.observation import bus_members
from custom_components.eltako.observation.bus_members import BusMemberRegistry, describe_model
from custom_components.eltako.const import (CONF_EEP, CONF_GATEWAY, CONF_LOG_ENOCEAN_TELEGRAMS, DATA_ELTAKO,
                                            DATA_TELEGRAM_LOGGER, TelegramDirection)
from custom_components.eltako.observation.enocean_logger import EnOceanTelegramLogger

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

    def test_an_exact_size_match_is_not_ambiguous(self):
        """FSR14_1x and FSR14_4x share their model bytes and differ in the size. With the
        size known the device is identified beyond doubt - reporting candidates anyway made
        plug & play hold back every FSR14_4x as 'please pick one'."""
        self.assertEqual(describe_model(b'\x04\x01\x72\x00', 4), ('FSR14_4x', None))
        self.assertEqual(describe_model(b'\x04\x01\x72\x00', 1), ('FSR14_1x', None))

    def test_every_library_class_is_recognized_beyond_doubt(self):
        """Audit over every discovery name of the eltakobus library.

        Every class which answers a discovery must be identified by (model, size) without a
        candidate list - a future library addition which shares model bytes *and* size with
        an existing class would otherwise silently push every affected device into 'needs a
        decision' (the FSR14_4x symptom)."""
        import inspect

        from eltakobus import device as eltako_devices

        for name, cls in inspect.getmembers(eltako_devices, inspect.isclass):
            for model in (getattr(cls, 'discovery_names', None) or []):
                size = getattr(cls, 'size', None)
                if size is None:
                    continue
                device_class, candidates = describe_model(bytes(model), size)
                self.assertEqual(device_class, name,
                                 msg=f"{name} (model {bytes(model).hex()}, size {size}) "
                                     f"resolves to {device_class!r}")
                self.assertIsNone(candidates,
                                  msg=f"{name} is still reported as ambiguous: {candidates}")

    def test_the_heating_actuators_are_disambiguated_by_size_too(self):
        """FHK14/F4HK14 are the only other pair sharing their model bytes (audit over every
        discovery name of the eltakobus library) - same bug, same fix as the FSR14."""
        self.assertEqual(describe_model(b'\x04\x18\x00\x00', 2), ('FHK14', None))
        self.assertEqual(describe_model(b'\x04\x18\x00\x00', 4), ('F4HK14', None))

    def test_without_the_size_the_candidates_are_reported(self):
        device_class, candidates = describe_model(b'\x04\x01\x72\x00', None)
        self.assertEqual(device_class, 'FSR14_1x')
        self.assertIn('FSR14_4x', candidates)

    def test_scan_progress_is_described_readably(self):
        from custom_components.eltako.observation.bus_members import describe_scan_progress

        # the shown count is the position being read (done + 1), so the line never starts
        # with a 'position 0/14' which reads like a stall
        self.assertEqual(describe_scan_progress({'positions_done': 0, 'positions_total': 14}),
                         'position 1/14')
        self.assertEqual(describe_scan_progress({'positions_done': 3, 'positions_total': 14,
                                                 'memory_rows_read': 23, 'memory_rows_total': 56}),
                         'position 4/14, memory 23/56')
        self.assertEqual(describe_scan_progress({'positions_done': 14, 'positions_total': 14}),
                         'position 14/14')


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


class TestGatewayFeedsTheRegistry(TestCase):
    """The gateway feeds the registry for every telegram - also with recording disabled.

    Recording telegrams is off by default. The channel layout of multi channel devices only
    comes from the discovery replies, so tying the collection to the telegram logger would
    leave the hierarchy of the web ui flat on a default installation.
    """

    def setUp(self):
        self.gateway = GatewayMock(dev_id=1, base_id=AddressExpression.parse('FF-A2-24-00'))
        self.hass = HassDataMock()
        self.gateway.hass = self.hass
        self.registry = bus_members.setup_registry(self.hass)

    def _receive(self, msg):
        self.gateway._record_telegram(msg, TelegramDirection.INCOMING)

    def test_no_telegram_logger_is_active(self):
        """Precondition of this whole class: recording is disabled."""
        from custom_components.eltako.observation.enocean_logger import get_telegram_logger

        self.assertIsNone(get_telegram_logger(self.hass))

    def test_polling_reveals_the_position(self):
        self._receive(EltakoPoll(4))

        members = self.registry.get_members()
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]['bus_address'], 4)
        self.assertEqual(members[0]['polled_count'], 1)

    def test_discovery_reply_is_collected(self):
        self._receive(discovery_reply(6))

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 6)
        self.assertEqual(member['device_class'], 'FSR14_4x')
        self.assertEqual(member['size'], 4)

    def test_status_answer_of_a_bus_device_is_collected(self):
        self._receive(EltakoWrapped4BS(address=b'\x00\x00\x00\x0A', status=0x00, data=b'\x01\x02\x03\x04'))

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 0x0A)
        self.assertEqual(member['answer_count'], 1)
        self.assertEqual(member['external_address'], 'FF-A2-24-0A')

    def test_wireless_telegrams_do_not_create_bus_members(self):
        from eltakobus.message import RPSMessage

        self._receive(RPSMessage(address=b'\x81\x04\xE5\x54', status=0x30, data=b'\x10'))

        self.assertEqual(self.registry.get_members(), [])

    def test_channels_are_grouped_without_telegram_logging(self):
        """The regression this class exists for: an FSR14-4x arrives as one device."""
        self._receive(discovery_reply(1))                   # FSR14_4x on positions 1-4
        for position in (2, 3, 4):
            self._receive(EltakoPoll(position))

        members = {m['bus_address']: m for m in self.registry.get_members()}

        self.assertEqual(members[1]['channel_count'], 4)
        self.assertIsNone(members[1]['parent_bus_address'])
        for position in (2, 3, 4):
            self.assertEqual(members[position]['parent_bus_address'], 1, msg=position)

    def test_telegrams_are_counted_once_when_recording_is_enabled(self):
        """The logger must not feed the registry a second time."""
        logger = EnOceanTelegramLogger(self.hass, get_general_settings(**{
            CONF_LOG_ENOCEAN_TELEGRAMS: True}))
        logger.refresh_device_map()
        self.hass.data[DATA_ELTAKO][DATA_TELEGRAM_LOGGER] = logger

        self._receive(EltakoPoll(7))

        member = self.registry.get_members()[0]
        self.assertEqual(member['bus_address'], 7)
        self.assertEqual(member['polled_count'], 1)


class TestMemoryPersistence(IsolatedAsyncioTestCase):
    """The memory scan locks the bus for minutes, so its result survives a restart."""

    def _registry(self, stored: dict = None) -> BusMemberRegistry:
        registry = BusMemberRegistry(HassDataMock())
        registry._store = StoreMock(stored)
        return registry

    def _stored_fsr14(self, scanned_at: str = None, model: str = '04-01-72-00', memory_size: int = 2) -> dict:
        return {'devices': {'1:1': {
            'model': model,
            'device_class': 'FSR14_4x',
            'size': 4,
            'memory_size': memory_size,
            'taught_in': [{'sensor_id': 'FE-DB-B6-40', 'channel': 1, 'role': 'button'}],
            'memory': {'0': '00' * 8, '1': 'fedbb640' + '05030100'},
            'scanned_at': scanned_at or iso_days_ago(1),
        }}}

    async def _scan_position_one(self, registry, gateway, memory=127):
        """A discovery reply followed by all memory rows - like a real scan.

        Same shape as TestMemoryImage._scan_position_one: the taught-in sender sits in
        memory line 12, everything else is empty.
        """
        registry.note_discovery_reply(gateway, discovery_reply(1, memory=memory))
        for line in range(memory):
            value = bytes.fromhex('fedbb640') + bytes((5, 3, 1, 0)) if line == 12 else bytes(8)
            registry.note_memory_response(gateway, MemoryResponseMock(line, value))
        await registry.async_parse_taught_in()

    ### saving

    async def test_memory_image_and_taught_in_are_persisted(self):
        registry = self._registry()
        await self._scan_position_one(registry, GatewayMock(dev_id=1))

        saved = registry._store.saved
        self.assertIsNotNone(saved, msg="a completed scan must trigger a save")
        device = saved['devices']['1:1']
        self.assertEqual(device['model'], '04-01-72-00')
        self.assertEqual(device['device_class'], 'FSR14_4x')
        self.assertEqual(device['memory_size'], 127)
        self.assertEqual(len(device['memory']), 127)
        self.assertEqual(device['memory']['12'], 'fedbb64005030100')
        self.assertEqual([s['sensor_id'] for s in device['taught_in']], ['FE-DB-B6-40'])
        self.assertIsNotNone(device['scanned_at'])

    async def test_session_counters_are_not_persisted(self):
        """Polling and answer counts describe the current session, not the hardware."""
        registry = self._registry()
        gateway = GatewayMock(dev_id=1)
        registry.note_polled(gateway, 1)
        registry.note_answer(gateway, 1, 'FF-A2-24-01')
        await self._scan_position_one(registry, gateway)

        device = registry._store.saved['devices']['1:1']
        for key in ('polled_count', 'answer_count', 'last_seen', 'taught_in_dirty'):
            self.assertNotIn(key, device, msg=key)

    async def test_positions_without_a_memory_image_are_not_persisted(self):
        registry = self._registry()
        registry.note_polled(GatewayMock(dev_id=1), 9)
        registry.unload()

        self.assertEqual(registry._store.saved, {'devices': {}})

    ### loading

    async def test_memory_image_is_restored(self):
        registry = self._registry(self._stored_fsr14())
        await registry.async_load()

        member = registry.get_members()[0]
        self.assertEqual(member['bus_address'], 1)
        self.assertEqual(member['device_class'], 'FSR14_4x')
        self.assertEqual(member['channel_count'], 4)
        self.assertEqual([s['sensor_id'] for s in member['taught_in']], ['FE-DB-B6-40'])
        self.assertEqual(member['memory_rows_read'], 2)
        # restored, not seen on the bus in this session
        self.assertIsNone(member['last_seen'])
        self.assertEqual(member['answer_count'], 0)

    async def test_restored_image_survives_the_next_enumeration(self):
        """The regression this exists for: the FAM14 re-enumerates all the time."""
        registry = self._registry(self._stored_fsr14())
        await registry.async_load()

        registry.note_discovery_reply(GatewayMock(dev_id=1), discovery_reply(1, memory=2))

        member = registry.get_members()[0]
        self.assertEqual([s['sensor_id'] for s in member['taught_in']], ['FE-DB-B6-40'])
        self.assertEqual(member['memory_rows_read'], 2)
        self.assertEqual(len(registry._memory[(1, 1)]), 2)

    async def test_changed_device_discards_the_restored_image(self):
        """Someone swapped the actuator while home assistant was down."""
        registry = self._registry(self._stored_fsr14())
        await registry.async_load()

        registry.note_discovery_reply(GatewayMock(dev_id=1),
                                      discovery_reply(1, model=b'\x04\x06\x00\x00', size=2, memory=96))

        member = registry.get_members()[0]
        self.assertEqual(member['device_class'], 'FSB14')
        self.assertNotIn('taught_in', member)
        self.assertEqual(registry._memory[(1, 1)], {})

    async def test_outdated_image_is_dropped(self):
        registry = self._registry(self._stored_fsr14(scanned_at=iso_days_ago(400)))
        await registry.async_load()

        self.assertEqual(registry.get_members(), [])

    async def test_broken_store_does_not_prevent_the_setup(self):
        registry = self._registry()

        async def explode():
            raise RuntimeError("storage file is corrupt")
        registry._store.async_load = explode

        await registry.async_load()       # must not raise
        self.assertEqual(registry.get_members(), [])

    async def test_unparsable_rows_are_skipped(self):
        stored = self._stored_fsr14()
        stored['devices']['1:1']['memory'] = {'0': 'not-hex', 'x': '0000', '1': '00' * 8}
        registry = self._registry(stored)
        await registry.async_load()

        self.assertEqual(list(registry._memory[(1, 1)]), [1])

    async def test_clear_also_clears_the_store(self):
        registry = self._registry(self._stored_fsr14())
        await registry.async_load()
        registry.clear()

        self.assertEqual(registry.get_members(), [])
        self.assertEqual(registry._store.saved, {'devices': {}})

    async def test_without_hass_nothing_is_persisted(self):
        """The registry is usable standalone (e.g. in tests) without a store."""
        registry = BusMemberRegistry()
        self.assertIsNone(registry._store)

        await registry.async_load()       # must not raise
        registry.note_polled(GatewayMock(dev_id=1), 1)
        registry.clear()


if __name__ == '__main__':
    unittest.main()


class TestEoManMapping(TestCase):
    """The eo_man mapping table enriches identified bus devices."""

    def test_known_hw_types(self):
        from custom_components.eltako.observation.bus_members import describe_hw_type

        fsr = describe_hw_type('FSR14_4x')
        self.assertEqual(fsr['description'], 'Relay (4 channels)')
        self.assertEqual(fsr['eep'], 'M5-38-08')
        self.assertEqual(fsr['pct14_function_group'], 2)
        self.assertEqual(fsr['pct14_key_function'], 51)

        fsb = describe_hw_type('FSB14')
        self.assertEqual(fsb['platform'], 'cover')
        self.assertEqual(fsb['sender_eep'], 'H5-3F-7F')

    def test_unknown_hw_type(self):
        from custom_components.eltako.observation.bus_members import describe_hw_type

        self.assertEqual(describe_hw_type('DOES_NOT_EXIST'), {})
        self.assertEqual(describe_hw_type(None), {})

    def test_every_discoverable_bus_device_has_an_entry(self):
        """Every device class the library can detect should be described - otherwise the
        table shows a bare class name without explanation."""
        from custom_components.eltako.observation.bus_members import HW_TYPE_INFO, MODEL_MAP

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
