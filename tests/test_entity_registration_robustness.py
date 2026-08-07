"""Tests for problems which showed up on a real installation.

* a failing state restoration must not prevent an entity from being added
* entity ids must be valid and must use the domain of their platform
* devices which are configured for more than one gateway must be reported
"""
import copy
import unittest
from unittest import IsolatedAsyncioTestCase, TestCase

from tests.mocks import *

from custom_components.eltako.config import config_helpers
from custom_components.eltako.const import *
from custom_components.eltako.cover import EltakoCover
from custom_components.eltako.core.entity import EltakoEntity
from custom_components.eltako.select import RepeaterMode

from eltakobus.eep import G5_3F_7F, H5_3F_7F
from eltakobus.util import AddressExpression
from homeassistant.const import Platform, STATE_OPEN


class TestObjectIdSanitizing(TestCase):

    def test_trailing_and_repeated_underscores_are_removed(self):
        self.assertEqual(config_helpers.sanitize_object_id('eltako_gw_0_'), 'eltako_gw_0')
        self.assertEqual(config_helpers.sanitize_object_id('_eltako__gw___0_'), 'eltako_gw_0')
        self.assertEqual(config_helpers.sanitize_object_id('eltako_ff_aa_80_01'), 'eltako_ff_aa_80_01')

    def test_empty_id_falls_back_to_domain(self):
        self.assertEqual(config_helpers.sanitize_object_id('___'), DOMAIN)

    def test_gateway_entity_gets_a_valid_entity_id(self):
        """The repeater mode of a gateway has no description key -> unique id ends with '_'."""
        entity = RepeaterMode(Platform.SELECT, GatewayMock(dev_id=0))

        self.assertEqual(entity.unique_id, 'eltako_gw_0_')       # identity must stay unchanged
        self.assertEqual(entity.entity_id, 'select.eltako_gw_0')  # but the entity id is valid
        self.assertFalse(entity.entity_id.endswith('_'))


class TestClimatePriorityPlatform(TestCase):
    """The priority selection is configured in the climate section but is a select entity."""

    def test_entity_id_uses_the_select_domain(self):
        from custom_components.eltako.select import ClimatePriority
        from eltakobus.eep import A5_10_06

        entity = ClimatePriority(Platform.SELECT, GatewayMock(), AddressExpression.parse('00-00-00-08'),
                                 "FAE14SSR - 8", A5_10_06)

        self.assertTrue(entity.entity_id.startswith('select.'))
        self.assertFalse(entity.entity_id.startswith('climate.'))


class TestCoverStateRestoration(TestCase):

    def create_cover(self) -> EltakoCover:
        return EltakoCover(Platform.COVER, GatewayMock(), AddressExpression.parse('00-00-00-06'),
                           "FSB14 - 6", G5_3F_7F, AddressExpression.parse('00-00-B0-06'), H5_3F_7F,
                           'shutter', 24, 25, None)

    def test_restoring_without_position_attributes_does_not_raise(self):
        """This aborted the registration of the cover entities on a real installation.

        Reported in https://github.com/grimmpp/home-assistant-eltako/pull/141:
        KeyError: 'current_position' in load_value_initially().
        """
        cover = self.create_cover()

        # state of a cover which was unavailable before the restart -> no attributes at all
        cover.load_value_initially(LatestStateMock('unknown', {}))

        self.assertIsNone(cover.current_cover_position)

    def test_restoring_state_unavailable_is_logged_as_debug(self):
        """'unavailable' is a normal state after a restart and must not warn."""
        cover = self.create_cover()

        with self.assertLogs(LOGGER, level='DEBUG') as logs:
            cover.load_value_initially(LatestStateMock('unavailable', {}))

        self.assertIsNone(cover.current_cover_position)
        self.assertFalse([m for m in logs.output if m.startswith('WARNING')])

    def test_restoring_unexpected_state_warns_but_does_not_raise(self):
        cover = self.create_cover()

        with self.assertLogs(LOGGER, level='WARNING') as logs:
            cover.load_value_initially(LatestStateMock('bla', {}))

        self.assertIn("Cannot restore unexpected state 'bla'", logs.output[0])
        self.assertIsNone(cover.current_cover_position)
        self.assertIsNone(cover.is_closed)   # undefined state

    def test_restoring_state_open_without_attributes(self):
        cover = self.create_cover()

        cover.load_value_initially(LatestStateMock(STATE_OPEN, {}))

        self.assertEqual(cover.current_cover_position, 100)
        self.assertFalse(cover.is_closed)

    def test_restoring_position_from_attributes(self):
        cover = self.create_cover()

        cover.load_value_initially(LatestStateMock('open', {'current_position': 42, 'current_tilt_position': 7}))

        self.assertEqual(cover.current_cover_position, 100)   # state 'open' wins over the attribute

    def test_restoring_partially_available_attributes(self):
        cover = self.create_cover()

        cover.load_value_initially(LatestStateMock('opening', {'current_position': 42}))

        self.assertEqual(cover.current_cover_position, 42)
        self.assertIsNone(cover.current_cover_tilt_position)
        self.assertTrue(cover.is_opening)


class TestDuplicateDeviceDetection(TestCase):

    CONFIG = {
        CONF_GATEWAY: [
            {
                CONF_ID: 0,
                CONF_DEVICES: {
                    'binary_sensor': [
                        {CONF_ID: 'FE-DB-B6-40', CONF_EEP: 'F6-02-01', CONF_NAME: 'Wall switch'},
                        {CONF_ID: 'FF-AA-11-22', CONF_EEP: 'F6-02-01'},
                    ],
                },
            },
            {
                CONF_ID: 1,
                CONF_DEVICES: {
                    'binary_sensor': [
                        {CONF_ID: 'fe-db-b6-40', CONF_EEP: 'F6-02-01', CONF_NAME: 'Button FE-DB-B6-40'},
                    ],
                    'light': [
                        {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08'},
                    ],
                },
            },
        ],
    }

    def test_duplicate_across_gateways_is_detected_and_removed(self):
        config = copy.deepcopy(self.CONFIG)

        duplicates = config_helpers.remove_duplicate_devices(config)

        self.assertEqual(list(duplicates.keys()), ['binary_sensor/FE-DB-B6-40'])
        self.assertEqual(duplicates['binary_sensor/FE-DB-B6-40'], ['gateway 0', 'gateway 1'])

        # the first declaration wins, the later one is dropped so that no entity with a
        # duplicated unique id is created
        gateway_0_ids = [d[CONF_ID] for d in config[CONF_GATEWAY][0][CONF_DEVICES]['binary_sensor']]
        gateway_1_ids = [d[CONF_ID] for d in config[CONF_GATEWAY][1][CONF_DEVICES]['binary_sensor']]
        self.assertIn('FE-DB-B6-40', gateway_0_ids)
        self.assertEqual(gateway_1_ids, [])
        # devices of other platforms are untouched
        self.assertEqual(len(config[CONF_GATEWAY][1][CONF_DEVICES]['light']), 1)

    def test_no_duplicates(self):
        config = copy.deepcopy({CONF_GATEWAY: [self.CONFIG[CONF_GATEWAY][0]]})

        self.assertEqual(config_helpers.remove_duplicate_devices(config), {})

    def test_same_address_on_different_platforms_is_no_duplicate(self):
        """A metering relay is both a switch and a sensor with the same address."""
        config = {CONF_GATEWAY: [{CONF_ID: 1, CONF_DEVICES: {
            'switch': [{CONF_ID: '00-00-00-0A', CONF_EEP: 'M5-38-08'}],
            'sensor': [{CONF_ID: '00-00-00-0A', CONF_EEP: 'A5-12-01'}],
        }}]}

        self.assertEqual(config_helpers.remove_duplicate_devices(config), {})

    def test_bus_device_on_two_gateways_is_kept(self):
        """Several gateways on one bus are a supported setup: the same bus device may be
        declared for both. Its unique id contains the gateway id, so every declaration
        becomes its own working entity - nothing collides, nothing is dropped."""
        config = {CONF_GATEWAY: [
            {CONF_ID: 1, CONF_DEVICES: {'light': [
                {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08'}]}},
            {CONF_ID: 2, CONF_DEVICES: {'light': [
                {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08'}]}},
        ]}

        self.assertEqual(config_helpers.remove_duplicate_devices(config), {})
        self.assertEqual(len(config[CONF_GATEWAY][0][CONF_DEVICES]['light']), 1)
        self.assertEqual(len(config[CONF_GATEWAY][1][CONF_DEVICES]['light']), 1)

    def test_bus_device_twice_on_the_same_gateway_is_removed(self):
        config = {CONF_GATEWAY: [{CONF_ID: 1, CONF_DEVICES: {'light': [
            {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08', CONF_NAME: 'first'},
            {CONF_ID: '00-00-00-01', CONF_EEP: 'M5-38-08', CONF_NAME: 'second'},
        ]}}]}

        duplicates = config_helpers.remove_duplicate_devices(config)

        self.assertEqual(list(duplicates.keys()), ['light/00-00-00-01@gw1'])
        remaining = config[CONF_GATEWAY][0][CONF_DEVICES]['light']
        self.assertEqual([d[CONF_NAME] for d in remaining], ['first'])

    def test_empty_config(self):
        self.assertEqual(config_helpers.remove_duplicate_devices({}), {})


if __name__ == '__main__':
    unittest.main()
