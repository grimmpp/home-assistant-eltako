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

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoEntity.send_message = mock.Mock(return_value=None)

class TestCover(unittest.TestCase):


    def test_entity_properties(self):  
        pl = Platform.BINARY_SENSOR
        gw = GatewayMock()
        address = AddressExpression.parse('FE-34-21-01')
        name = "Switch"

        ee = EltakoEntity(pl, gw, address, name, F6_02_01)

        self.assertEquals(ee.dev_name, config_helpers.get_device_name(name, address, gw.general_settings))
        
        self.assertEquals(len(ee.listen_to_addresses),1)
        self.assertEquals(ee.listen_to_addresses[0], b'\xfe4!\x01')

        self.assertEquals(ee.dev_name, 'Switch')
        self.assertEquals(ee.unique_id, 'eltako_gw123_FE-34-21-01')
        self.assertEquals(ee.entity_id, 'binary_sensor.eltako_gw123_FE-34-21-01')

    def test_load_initial_values(self):
        pl = Platform.BINARY_SENSOR
        gw = GatewayMock()
        address = AddressExpression.parse('FE-34-21-01')
        name = "Switch"

        ee = EltakoEntity(pl, gw, address, name, F6_02_01)
        ee._attr_is_on = None

        ee.load_value_initially(LatestStateMock("true", {}))

        # self.assertTrue(ee._attr_is_on)