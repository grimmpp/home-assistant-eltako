import unittest
import os
from mocks import *
from unittest import mock, IsolatedAsyncioTestCase, TestCase
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.cover import EltakoCover
from custom_components.eltako.device import EltakoEntity
from eltakobus import *

from custom_components.eltako import config_helpers
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
        self.assertEqual(ee.unique_id, 'eltako_gw123_fe_34_21_01')
        self.assertEqual(ee.entity_id, 'binary_sensor.eltako_gw123_fe_34_21_01')

        self.assertTrue( core.valid_domain(ee._attr_ha_platform) )
        self.assertTrue( core.valid_entity_id(ee.entity_id) )
        self.assertTrue( core.validate_state(ee.state))
