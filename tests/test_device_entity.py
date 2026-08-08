import unittest
from tests.mocks import GatewayMock
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.core.entity import EltakoEntity
from eltakobus import AddressExpression, F6_02_01

from custom_components.eltako.config import config_helpers
from homeassistant import core

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestEntityProperties(unittest.TestCase):


    def test_entity_properties(self):
        pl = Platform.BINARY_SENSOR
        gw = GatewayMock()
        address = AddressExpression.parse('FE-34-21-01')
        name = "Switch"

        ee = EltakoEntity(pl, gw, address, name, F6_02_01)

        self.assertEqual(ee.dev_name, config_helpers.get_device_name(name, address, gw.general_settings))

        self.assertEqual(len(ee.listen_to_addresses),1)
        self.assertEqual(ee.listen_to_addresses[0], b'\xfe4!\x01')

        self.assertEqual(ee.dev_name, 'Switch')
        self.assertEqual(ee.unique_id, 'eltako_fe_34_21_01')
        self.assertEqual(ee.entity_id, 'binary_sensor.eltako_fe_34_21_01')

        self.assertTrue( core.valid_domain(ee._attr_ha_platform) )
        self.assertTrue( core.valid_entity_id(ee.entity_id ) )
        self.assertTrue( core.validate_state(ee.state))

    def test_entity_id_of_a_gateway_level_entity_is_valid(self):
        """Gateway entities use 00-00-00-00 as device id and may have no description key, so the
        unique id ends with '_'. Home Assistant rejects that as entity id ('sets an invalid
        entity ID: select.eltako_gw_10_'), only the entity id is sanitized - the unique id is the
        identity in the entity registry and must not change."""
        gw = GatewayMock(dev_id=10)
        ee = EltakoEntity(Platform.SELECT, gw, AddressExpression.parse('00-00-00-00'), "Repeater_Mode")

        self.assertTrue(ee.unique_id.endswith('_'))
        self.assertTrue(core.valid_entity_id(ee.entity_id), ee.entity_id)
        self.assertEqual(ee.entity_id, 'select.eltako_gw_10')

    def test_entity_area_default(self):
        """When no area is provided, suggested_area in DeviceInfo is None."""
        gw = GatewayMock()
        address = AddressExpression.parse('FE-34-21-01')

        ee = EltakoEntity(Platform.BINARY_SENSOR, gw, address, "Switch", F6_02_01)

        self.assertIsNone(ee._attr_dev_area)
        self.assertIsNone(ee.device_info["suggested_area"])

    def test_entity_area_set(self):
        """When an area is provided, it is exposed via device_info.suggested_area."""
        gw = GatewayMock()
        address = AddressExpression.parse('FE-34-21-01')

        ee = EltakoEntity(Platform.BINARY_SENSOR, gw, address, "Switch", F6_02_01, dev_area="Living Room")

        self.assertEqual(ee._attr_dev_area, "Living Room")
        self.assertEqual(ee.device_info["suggested_area"], "Living Room")
