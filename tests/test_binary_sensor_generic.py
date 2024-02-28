import unittest
from mocks import *
from unittest import mock
from homeassistant.helpers.entity import Entity
from homeassistant.const import Platform
from custom_components.eltako.binary_sensor import EltakoBinarySensor
from custom_components.eltako.config_helpers import *
from eltakobus import *
from eltakobus.eep import *

# mock update of Home Assistant
Entity.schedule_update_ha_state = mock.Mock(return_value=None)
# EltakoBinarySensor.hass.bus.fire is mocked by class HassMock


class TestBinarySensor(unittest.TestCase):

    
    def create_binary_sensor(self, eep_string:str="F6-02-01", device_class = "none", invert_signal:bool=False) -> EltakoBinarySensor:
        gateway = GatewayMock(dev_id=123)
        dev_id = AddressExpression.parse("00-00-00-01")
        dev_name = "device name"
        
        dev_eep = EEP.find(eep_string)

        bs = EltakoBinarySensor(Platform.BINARY_SENSOR, gateway, dev_id, dev_name, dev_eep, device_class, invert_signal)
        bs.hass = HassMock()
        self.assertEqual(bs._attr_is_on, None)     

        return bs


    def test_initial_loading_on(self):
        bs = self.create_binary_sensor()
        bs._attr_is_on = None

        bs.load_value_initially(LatestStateMock('on'))
        self.assertTrue(bs._attr_is_on)
        self.assertTrue(bs.is_on)
        self.assertEqual(bs.state, 'on')

    def test_initial_loading_off(self):
        bs = self.create_binary_sensor()
        bs._attr_is_on = None

        bs.load_value_initially(LatestStateMock('off'))
        self.assertFalse(bs._attr_is_on)
        self.assertFalse(bs.is_on)
        self.assertEqual(bs.state, 'off')

    def test_initial_loading_None(self):
        bs = self.create_binary_sensor()
        bs._attr_is_on = True

        bs.load_value_initially(LatestStateMock('bla'))
        self.assertIsNone(bs._attr_is_on)
        self.assertIsNone(bs.is_on)
        self.assertIsNone(bs.state)
